"""SSE streaming endpoint for real-time query processing.

Provides server-sent events for streaming analysis progress and results.
Uses a pandas-based query processor that works without any LLM API keys.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.logger import logger
from ..state.session_state import SessionState
from ..state.persistent_session_state import session_manager
from ..db.base import get_session
from ..services.agent import DataAnalysisAgent


router = APIRouter()


@dataclass
class StreamEvent:
    step: str
    message: str
    data: Optional[Dict[str, Any]] = None


def _get_dataframe(session_id: str) -> Optional[pd.DataFrame]:
    """Get DataFrame from either in-memory state or persistent state."""
    simple = SessionState.get(session_id)
    df = simple.get_value("raw_dataframe")
    if df is not None:
        return df

    persistent = session_manager.get_session(session_id)
    df = persistent.get_value("raw_dataframe")
    return df


class SmartQueryProcessor:
    """Processes natural language queries against a pandas DataFrame.

    Works entirely offline - no LLM API keys required.
    Handles: aggregations, filtering, sorting, statistics, trends, comparisons.
    """

    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        self.categorical_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
        self.datetime_cols = df.select_dtypes(include=['datetime64']).columns.tolist()
        # Try to detect date columns stored as strings
        for col in self.categorical_cols[:]:
            try:
                parsed = pd.to_datetime(df[col], errors='coerce')
                if parsed.notna().sum() > len(df) * 0.5:
                    self.datetime_cols.append(col)
                    self.categorical_cols.remove(col)
            except Exception:
                pass

    def process(self, query: str) -> Dict[str, Any]:
        """Process a natural language query and return structured results."""
        query_lower = query.lower().strip()

        # Detect intent from query
        if self._is_top_query(query_lower):
            return self._handle_top_query(query_lower)
        elif self._is_trend_query(query_lower):
            return self._handle_trend_query(query_lower)
        elif self._is_comparison_query(query_lower):
            return self._handle_comparison_query(query_lower)
        elif self._is_statistics_query(query_lower):
            return self._handle_statistics_query(query_lower)
        elif self._is_correlation_query(query_lower):
            return self._handle_correlation_query(query_lower)
        elif self._is_missing_query(query_lower):
            return self._handle_missing_query(query_lower)
        elif self._is_distribution_query(query_lower):
            return self._handle_distribution_query(query_lower)
        else:
            return self._handle_general_query(query_lower)

    def _find_column(self, query: str, col_type: str = "any") -> Optional[str]:
        """Find the most likely column referenced in the query."""
        cols = self.df.columns.tolist()
        if col_type == "numeric":
            cols = self.numeric_cols
        elif col_type == "categorical":
            cols = self.categorical_cols

        query_lower = query.lower()
        # Direct name match
        for col in cols:
            if col.lower() in query_lower or col.lower().replace('_', ' ') in query_lower:
                return col

        # Fuzzy match - check if any word in the query matches part of a column name
        query_words = set(re.split(r'\W+', query_lower))
        best_col = None
        best_score = 0
        for col in cols:
            col_words = set(re.split(r'[_\s]+', col.lower()))
            overlap = len(query_words & col_words)
            if overlap > best_score:
                best_score = overlap
                best_col = col

        if best_score > 0:
            return best_col
        return None

    def _find_metric_column(self, query: str) -> Optional[str]:
        """Find the most relevant numeric/metric column for the query."""
        query_lower = query.lower()
        # Common metric keywords mapped to likely column patterns
        metric_hints = {
            'sale': ['sales', 'sale', 'total_sales', 'sales_amount', 'revenue'],
            'revenue': ['revenue', 'total_revenue', 'amount', 'sales'],
            'profit': ['profit', 'net_profit', 'gross_profit', 'margin'],
            'quantity': ['quantity', 'qty', 'units_sold', 'units', 'count'],
            'price': ['price', 'unit_price', 'cost', 'amount'],
            'rating': ['rating', 'score', 'review_score'],
            'count': ['count', 'quantity', 'units', 'number'],
        }

        for hint, patterns in metric_hints.items():
            if hint in query_lower:
                for pattern in patterns:
                    for col in self.numeric_cols:
                        if pattern in col.lower():
                            return col

        # Direct column name match
        col = self._find_column(query, "numeric")
        if col:
            return col

        # Default to first numeric column
        return self.numeric_cols[0] if self.numeric_cols else None

    def _find_group_column(self, query: str) -> Optional[str]:
        """Find the grouping/category column."""
        query_lower = query.lower()
        group_hints = {
            'product': ['product', 'product_name', 'item', 'sku', 'name'],
            'category': ['category', 'type', 'group', 'class'],
            'region': ['region', 'area', 'location', 'city', 'state', 'country'],
            'customer': ['customer', 'client', 'user', 'buyer'],
            'brand': ['brand', 'manufacturer', 'vendor'],
            'month': ['month', 'period'],
            'year': ['year'],
        }

        for hint, patterns in group_hints.items():
            if hint in query_lower:
                for pattern in patterns:
                    for col in self.categorical_cols:
                        if pattern in col.lower():
                            return col

        col = self._find_column(query, "categorical")
        if col:
            return col

        return self.categorical_cols[0] if self.categorical_cols else None

    # --- Intent Detection ---

    def _is_top_query(self, q: str) -> bool:
        return bool(re.search(r'\b(top|best|most|highest|largest|maximum|leading|popular)\b', q))

    def _is_trend_query(self, q: str) -> bool:
        return bool(re.search(r'\b(trend|over time|monthly|weekly|daily|growth|timeline|time series)\b', q))

    def _is_comparison_query(self, q: str) -> bool:
        return bool(re.search(r'\b(compare|vs|versus|difference|between)\b', q))

    def _is_statistics_query(self, q: str) -> bool:
        return bool(re.search(r'\b(average|mean|median|std|deviation|statistics|summary|describe|overview|profile)\b', q))

    def _is_correlation_query(self, q: str) -> bool:
        return bool(re.search(r'\b(correlation|correlat|relationship|related|affect|impact|influence)\b', q))

    def _is_missing_query(self, q: str) -> bool:
        return bool(re.search(r'\b(missing|null|nan|empty|incomplete|clean)\b', q))

    def _is_distribution_query(self, q: str) -> bool:
        return bool(re.search(r'\b(distribution|histogram|spread|range|outlier|skew)\b', q))

    # --- Query Handlers ---

    def _handle_top_query(self, query: str) -> Dict[str, Any]:
        """Handle 'top N' / 'most selling' queries."""
        # Extract N
        n_match = re.search(r'\b(\d+)\b', query)
        n = int(n_match.group(1)) if n_match else 10

        metric_col = self._find_metric_column(query)
        group_col = self._find_group_column(query)

        if not metric_col:
            return self._handle_general_query(query)

        if group_col and group_col != metric_col:
            result = (
                self.df.groupby(group_col)[metric_col]
                .sum()
                .sort_values(ascending=False)
                .head(n)
            )
            total = self.df[metric_col].sum()

            table_data = []
            for name, value in result.items():
                share = (value / total * 100) if total > 0 else 0
                table_data.append({
                    group_col: str(name),
                    f"total_{metric_col}": round(float(value), 2),
                    "share_pct": round(float(share), 1),
                })

            narrative = f"**Top {n} by {metric_col}:**\n\n"
            for i, (name, value) in enumerate(result.items(), 1):
                share = (value / total * 100) if total > 0 else 0
                narrative += f"{i}. **{name}** — {value:,.2f} ({share:.1f}% of total)\n"

            narrative += f"\n**Total {metric_col}:** {total:,.2f}"

            return {
                "narrative": narrative,
                "table": table_data,
                "chart": {
                    "type": "bar",
                    "x": [str(name) for name in result.index],
                    "y": [round(float(v), 2) for v in result.values],
                    "x_label": group_col,
                    "y_label": metric_col,
                    "title": f"Top {n} {group_col} by {metric_col}",
                },
            }
        else:
            # No good grouping column, just show top values
            top_rows = self.df.nlargest(n, metric_col)
            display_cols = [c for c in self.df.columns if c != metric_col][:3]
            display_cols = [metric_col] + display_cols

            narrative = f"**Top {n} rows by {metric_col}:**\n\n"
            narrative += top_rows[display_cols].to_markdown(index=False)

            return {"narrative": narrative, "table": top_rows[display_cols].to_dict('records')}

    def _handle_trend_query(self, query: str) -> Dict[str, Any]:
        """Handle time-series / trend queries."""
        metric_col = self._find_metric_column(query)
        date_col = self.datetime_cols[0] if self.datetime_cols else None

        if not metric_col:
            return self._handle_general_query(query)

        if date_col:
            df_sorted = self.df.copy()
            df_sorted[date_col] = pd.to_datetime(df_sorted[date_col], errors='coerce')
            df_sorted = df_sorted.dropna(subset=[date_col]).sort_values(date_col)

            # Group by month
            df_sorted['_period'] = df_sorted[date_col].dt.to_period('M')
            trend = df_sorted.groupby('_period')[metric_col].sum()

            narrative = f"**{metric_col} trend over time:**\n\n"
            for period, value in trend.items():
                narrative += f"- {period}: {value:,.2f}\n"

            if len(trend) >= 2:
                first_val = trend.iloc[0]
                last_val = trend.iloc[-1]
                change_pct = ((last_val - first_val) / first_val * 100) if first_val != 0 else 0
                direction = "increased" if change_pct > 0 else "decreased"
                narrative += f"\n**Overall:** {metric_col} {direction} by {abs(change_pct):.1f}% from {trend.index[0]} to {trend.index[-1]}."

            return {
                "narrative": narrative,
                "chart": {
                    "type": "line",
                    "x": [str(p) for p in trend.index],
                    "y": [round(float(v), 2) for v in trend.values],
                    "x_label": "Period",
                    "y_label": metric_col,
                    "title": f"{metric_col} Over Time",
                },
            }
        else:
            return {"narrative": f"No date/time column found to show trends. Available columns: {', '.join(self.df.columns.tolist())}"}

    def _handle_comparison_query(self, query: str) -> Dict[str, Any]:
        """Handle comparison queries."""
        metric_col = self._find_metric_column(query)
        group_col = self._find_group_column(query)

        if not metric_col or not group_col:
            return self._handle_general_query(query)

        comparison = self.df.groupby(group_col)[metric_col].agg(['sum', 'mean', 'count'])
        comparison = comparison.sort_values('sum', ascending=False).head(10)

        narrative = f"**Comparison of {group_col} by {metric_col}:**\n\n"
        narrative += "| {} | Total | Average | Count |\n|---|---|---|---|\n".format(group_col)
        for name, row in comparison.iterrows():
            narrative += f"| {name} | {row['sum']:,.2f} | {row['mean']:,.2f} | {int(row['count'])} |\n"

        return {
            "narrative": narrative,
            "chart": {
                "type": "bar",
                "x": [str(name) for name in comparison.index],
                "y": [round(float(v), 2) for v in comparison['sum']],
                "x_label": group_col,
                "y_label": f"Total {metric_col}",
                "title": f"{metric_col} by {group_col}",
            },
        }

    def _handle_statistics_query(self, query: str) -> Dict[str, Any]:
        """Handle statistics/summary queries."""
        narrative = f"**Dataset Overview:**\n\n"
        narrative += f"- **Rows:** {len(self.df):,}\n"
        narrative += f"- **Columns:** {len(self.df.columns)}\n"
        narrative += f"- **Numeric columns:** {', '.join(self.numeric_cols)}\n"
        narrative += f"- **Categorical columns:** {', '.join(self.categorical_cols[:10])}\n"

        if self.numeric_cols:
            narrative += f"\n**Key Statistics:**\n\n"
            stats = self.df[self.numeric_cols].describe().T
            for col in stats.index[:8]:
                row = stats.loc[col]
                narrative += f"- **{col}:** mean={row['mean']:,.2f}, min={row['min']:,.2f}, max={row['max']:,.2f}, std={row['std']:,.2f}\n"

        # Missing values
        missing = self.df.isnull().sum()
        missing_pct = (missing / len(self.df) * 100).round(1)
        has_missing = missing[missing > 0]
        if len(has_missing) > 0:
            narrative += f"\n**Missing Values:**\n"
            for col, count in has_missing.items():
                narrative += f"- {col}: {count} ({missing_pct[col]}%)\n"
        else:
            narrative += f"\n**No missing values detected.**"

        return {"narrative": narrative}

    def _handle_correlation_query(self, query: str) -> Dict[str, Any]:
        """Handle correlation queries."""
        if len(self.numeric_cols) < 2:
            return {"narrative": "Need at least 2 numeric columns to compute correlations."}

        corr = self.df[self.numeric_cols].corr()

        # Find top correlations (excluding self-correlation)
        pairs = []
        for i in range(len(corr.columns)):
            for j in range(i + 1, len(corr.columns)):
                pairs.append((corr.columns[i], corr.columns[j], corr.iloc[i, j]))

        pairs.sort(key=lambda x: abs(x[2]), reverse=True)

        narrative = "**Top Correlations:**\n\n"
        for col1, col2, val in pairs[:10]:
            strength = "strong" if abs(val) > 0.7 else "moderate" if abs(val) > 0.4 else "weak"
            direction = "positive" if val > 0 else "negative"
            narrative += f"- **{col1}** ↔ **{col2}**: {val:.3f} ({strength} {direction})\n"

        return {"narrative": narrative}

    def _handle_missing_query(self, query: str) -> Dict[str, Any]:
        """Handle missing value analysis."""
        missing = self.df.isnull().sum()
        missing_pct = (missing / len(self.df) * 100).round(1)
        total_missing = missing.sum()
        total_cells = self.df.size

        narrative = f"**Missing Value Analysis:**\n\n"
        narrative += f"- Total missing cells: {total_missing:,} out of {total_cells:,} ({total_missing/total_cells*100:.1f}%)\n\n"

        has_missing = missing[missing > 0].sort_values(ascending=False)
        if len(has_missing) > 0:
            narrative += "| Column | Missing | Percentage |\n|---|---|---|\n"
            for col, count in has_missing.items():
                narrative += f"| {col} | {count:,} | {missing_pct[col]}% |\n"

            narrative += f"\n**Recommendation:** "
            high_missing = has_missing[has_missing / len(self.df) > 0.5]
            if len(high_missing) > 0:
                narrative += f"Consider dropping columns with >50% missing: {', '.join(high_missing.index.tolist())}. "
            low_missing = has_missing[has_missing / len(self.df) <= 0.05]
            if len(low_missing) > 0:
                narrative += f"Columns with <5% missing can be imputed: {', '.join(low_missing.index.tolist())}."
        else:
            narrative += "**No missing values found! Your dataset is complete.**"

        return {"narrative": narrative}

    def _handle_distribution_query(self, query: str) -> Dict[str, Any]:
        """Handle distribution queries."""
        col = self._find_column(query, "numeric")
        if not col and self.numeric_cols:
            col = self.numeric_cols[0]

        if not col:
            return {"narrative": "No numeric columns found for distribution analysis."}

        series = self.df[col].dropna()
        stats = {
            "count": int(len(series)),
            "mean": float(series.mean()),
            "median": float(series.median()),
            "std": float(series.std()),
            "min": float(series.min()),
            "max": float(series.max()),
            "skew": float(series.skew()),
            "q25": float(series.quantile(0.25)),
            "q75": float(series.quantile(0.75)),
        }

        iqr = stats["q75"] - stats["q25"]
        outlier_low = stats["q25"] - 1.5 * iqr
        outlier_high = stats["q75"] + 1.5 * iqr
        n_outliers = int(((series < outlier_low) | (series > outlier_high)).sum())

        narrative = f"**Distribution of {col}:**\n\n"
        narrative += f"- Count: {stats['count']:,}\n"
        narrative += f"- Mean: {stats['mean']:,.2f}\n"
        narrative += f"- Median: {stats['median']:,.2f}\n"
        narrative += f"- Std Dev: {stats['std']:,.2f}\n"
        narrative += f"- Range: [{stats['min']:,.2f}, {stats['max']:,.2f}]\n"
        narrative += f"- IQR: [{stats['q25']:,.2f}, {stats['q75']:,.2f}]\n"
        narrative += f"- Skewness: {stats['skew']:.3f} ({'right-skewed' if stats['skew'] > 0.5 else 'left-skewed' if stats['skew'] < -0.5 else 'approximately symmetric'})\n"
        narrative += f"- Outliers: {n_outliers} ({n_outliers/stats['count']*100:.1f}%)\n"

        # Create histogram bins
        hist, bin_edges = np.histogram(series, bins=10)
        chart_data = {
            "type": "bar",
            "x": [f"{bin_edges[i]:.1f}-{bin_edges[i+1]:.1f}" for i in range(len(hist))],
            "y": [int(h) for h in hist],
            "x_label": col,
            "y_label": "Count",
            "title": f"Distribution of {col}",
        }

        return {"narrative": narrative, "chart": chart_data}

    def _handle_general_query(self, query: str) -> Dict[str, Any]:
        """Handle general queries by trying to understand what the user wants."""
        # Try to find relevant columns mentioned in the query
        metric_col = self._find_metric_column(query)
        group_col = self._find_group_column(query)

        if metric_col and group_col and group_col != metric_col:
            # Default to aggregation
            result = self.df.groupby(group_col)[metric_col].agg(['sum', 'mean', 'count'])
            result = result.sort_values('sum', ascending=False).head(10)

            narrative = f"**Analysis of {metric_col} by {group_col}:**\n\n"
            narrative += "| {} | Total | Average | Count |\n|---|---|---|---|\n".format(group_col)
            for name, row in result.iterrows():
                narrative += f"| {name} | {row['sum']:,.2f} | {row['mean']:,.2f} | {int(row['count'])} |\n"

            total = self.df[metric_col].sum()
            narrative += f"\n**Grand Total:** {total:,.2f}"

            return {
                "narrative": narrative,
                "chart": {
                    "type": "bar",
                    "x": [str(name) for name in result.index],
                    "y": [round(float(v), 2) for v in result['sum']],
                    "x_label": group_col,
                    "y_label": f"Total {metric_col}",
                    "title": f"{metric_col} by {group_col}",
                },
            }
        elif metric_col:
            # Just show stats for that column
            series = self.df[metric_col].dropna()
            narrative = f"**{metric_col} Summary:**\n\n"
            narrative += f"- Total: {series.sum():,.2f}\n"
            narrative += f"- Average: {series.mean():,.2f}\n"
            narrative += f"- Median: {series.median():,.2f}\n"
            narrative += f"- Min: {series.min():,.2f} | Max: {series.max():,.2f}\n"
            narrative += f"- Records: {len(series):,}\n"
            return {"narrative": narrative}
        else:
            # Give a dataset overview
            return self._handle_statistics_query(query)


class StreamProcessor:
    """Processes queries with streaming events using the SmartQueryProcessor."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.queue: asyncio.Queue = asyncio.Queue()

    async def send_event(self, step: str, message: str, data: Optional[Dict[str, Any]] = None):
        event = StreamEvent(step=step, message=message, data=data)
        await self.queue.put(event)

    async def process_query(self, query: str, db: Optional[AsyncSession] = None):
        """Process query using the safe dataframe analytics agent."""
        df = None
        try:
            await self.send_event("intent_parsed", "Understanding your question...")

            df = _get_dataframe(self.session_id)
            if df is None:
                await self.send_event("error", "No dataset found for this session. Please upload a dataset first.")
                return

            await self.send_event("analysis_running", "Running dataframe calculations...")

            state = SessionState.get(self.session_id)
            previous_result = state.get_value("last_analysis_result") if state else None
            filename = state.get_value("dataset_filename") if state else None
            result = await DataAnalysisAgent().answer_with_optional_llm(df, query, previous_result, filename=filename)
            if state:
                state.set("last_analysis_result", result)

            await self.send_event(
                "agent_active",
                f"Analytics agent selected: {result.get('dataset_type', 'generic')} / {result.get('intent', 'analysis')}",
            )
            await self.send_event("method", result.get("method", "Calculated using dataframe operations."))

            narrative = result.get("answer") or "Analysis complete."
            await self.send_event("narration", narrative)

            for table in result.get("tables", [])[:2]:
                await self.send_event("table_ready", table.get("title", "Table generated"), {"table": table})

            for chart in result.get("charts", [])[:2]:
                chart_spec = self._build_plotly_spec(chart)
                await self.send_event("visualization_ready", chart.get("title", "Chart generated"), {"chart_spec": chart_spec, "chart": chart})

            recommendations = result.get("recommendations") or []
            if recommendations:
                await self.send_event("recommendations", "Business recommendations", {"recommendations": recommendations})

            warnings = result.get("warnings") or []
            if warnings:
                await self.send_event("warning", warnings[0], {"warnings": warnings})

            suggestions = result.get("suggestions") or self._follow_up_suggestions(result.get("intent"), result.get("dataset_type"))
            await self.send_event("suggestions", "Follow-up ideas", {"suggestions": suggestions})

            await self.send_event("complete", "Analysis complete")

        except Exception as e:
            logger.exception(f"Stream processing failed: {e}")
            # Fallback to the basic SmartQueryProcessor
            try:
                processor = SmartQueryProcessor(df) if df is not None else None
                fallback = processor.process(query) if processor else {"narrative": "No dataset found."}
                await self.send_event("narration", fallback.get("narrative", "Analysis complete."))
                if "chart" in fallback:
                    chart_spec = self._build_plotly_spec(fallback["chart"])
                    await self.send_event("visualization_ready", "Chart generated", {"chart_spec": chart_spec})
                await self.send_event("complete", "Analysis complete")
            except Exception:
                await self.send_event("error", f"Processing failed: {str(e)}")

    def _follow_up_suggestions(self, intent: str | None, dataset_type: str | None = None) -> list[str]:
        if dataset_type:
            try:
                from ..services.recommendation_engine import follow_up_suggestions

                return follow_up_suggestions(dataset_type, {})
            except Exception:
                pass
        if intent == "trending_products":
            return ["Which products are declining?", "Show monthly revenue trend", "What should I stock more?"]
        if intent == "top_products":
            return ["Which products are trending?", "Break this down by category", "Show this as a chart"]
        if intent == "revenue_trend":
            return ["Which category performs best?", "Forecast next period", "Find outliers"]
        return ["What are the top products?", "Which products are trending?", "Give me business recommendations"]

    def _build_plotly_spec(self, chart: Dict[str, Any]) -> Dict[str, Any]:
        """Convert simple chart data to Plotly spec."""
        chart_type = chart.get("type", "bar")
        rows = chart.get("data") or []
        x_key = chart.get("x_key")
        y_key = chart.get("y_key")

        if rows and x_key:
            x_values = [row.get(x_key) for row in rows]
            y_values = [row.get(y_key) for row in rows] if y_key else []
        else:
            x_values = chart.get("x", [])
            y_values = chart.get("y", [])

        if chart_type == "bar":
            return {
                "data": [{
                    "type": "bar",
                    "x": x_values,
                    "y": y_values,
                    "marker": {"color": "#0D9488"},
                }],
                "layout": {
                    "title": chart.get("title", ""),
                    "xaxis": {"title": chart.get("x_label", "")},
                    "yaxis": {"title": chart.get("y_label", "")},
                    "paper_bgcolor": "transparent",
                    "plot_bgcolor": "transparent",
                    "margin": {"l": 50, "r": 20, "t": 40, "b": 60},
                },
            }
        elif chart_type == "line":
            return {
                "data": [{
                    "type": "scatter",
                    "mode": "lines+markers",
                    "x": x_values,
                    "y": y_values,
                    "line": {"color": "#0D9488"},
                    "marker": {"size": 6},
                }],
                "layout": {
                    "title": chart.get("title", ""),
                    "xaxis": {"title": chart.get("x_label", "")},
                    "yaxis": {"title": chart.get("y_label", "")},
                    "paper_bgcolor": "transparent",
                    "plot_bgcolor": "transparent",
                    "margin": {"l": 50, "r": 20, "t": 40, "b": 60},
                },
            }
        elif chart_type in {"pie", "donut"}:
            return {
                "data": [{
                    "type": "pie",
                    "labels": x_values,
                    "values": y_values,
                    "hole": 0.45 if chart_type == "donut" else 0,
                }],
                "layout": {
                    "title": chart.get("title", ""),
                    "paper_bgcolor": "transparent",
                    "plot_bgcolor": "transparent",
                    "margin": {"l": 20, "r": 20, "t": 40, "b": 20},
                },
            }
        return {"data": [], "layout": {"title": chart.get("title", "")}}


async def generate_events(session_id: str, query: str, db: Optional[AsyncSession] = None):
    """Generate SSE events for the stream."""
    processor = StreamProcessor(session_id)

    asyncio.create_task(processor.process_query(query, db))

    while True:
        try:
            event = await asyncio.wait_for(processor.queue.get(), timeout=30.0)
            data = {
                "step": event.step,
                "message": event.message
            }
            if event.data:
                data.update(event.data)

            yield f"data: {json.dumps(data)}\n\n"

            if event.step in ["complete", "error", "clarification_needed"]:
                break

        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'step': 'heartbeat', 'message': 'Processing...'})}\n\n"


@router.get("/query")
async def stream_query(
    session_id: str = Query(..., description="Session ID"),
    query: str = Query(..., description="User query"),
    db: Optional[AsyncSession] = Depends(get_session)
):
    """Stream query processing results via SSE."""
    df = _get_dataframe(session_id)
    if df is None:
        raise HTTPException(404, "Session not found or dataset not loaded")

    return StreamingResponse(
        generate_events(session_id, query, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        }
    )
