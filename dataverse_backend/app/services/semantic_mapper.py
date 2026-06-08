"""Dynamic semantic mapping for mart, retail, invoice, ecommerce, and ledger datasets."""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, Field, ValidationError, field_validator

from .llm_provider import LLMProvider


SUPPORTED_ROLES = {
    "order_date",
    "transaction_date",
    "invoice_date",
    "product",
    "product_category",
    "customer",
    "store",
    "region",
    "city",
    "country",
    "sales_revenue",
    "gross_sales",
    "net_sales",
    "amount",
    "unit_price",
    "quantity",
    "cost",
    "expense",
    "profit",
    "discount",
    "tax",
    "payment_method",
    "transaction_type",
    "order_id",
    "invoice_id",
    "customer_id",
    "generic_numeric",
    "generic_text",
    "ignore_identifier",
}

DATASET_TYPES = {
    "mart_sales",
    "retail_sales",
    "invoice_sales",
    "ecommerce_orders",
    "pos_transactions",
    "transaction_ledger",
    "inventory",
    "food_dataset",
    "customer_sales",
    "generic_tabular",
}

DATE_ROLES = {"order_date", "transaction_date", "invoice_date"}
SALE_VALUES = {"SALE", "SALES", "SELL", "SOLD", "INCOME", "REVENUE", "PAID"}
EXPENSE_VALUES = {"EXPENSE", "EXPENSES", "COST", "COSTS", "SPENDING"}
CREDIT_VALUES = {"UDHAAR", "CREDIT", "OUTSTANDING", "DEBT", "CUSTOMER DEBT"}
REFUND_VALUES = {"REFUND", "RETURN", "RETURNS"}


class MetricSpec(BaseModel):
    source_column: str | None = None
    filter: dict[str, Any] | None = None
    aggregation: Literal["sum", "count", "mean", "derived"] = "sum"
    expression: str | None = None


class SemanticMap(BaseModel):
    dataset_type: str = "generic_tabular"
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    column_roles: dict[str, str] = Field(default_factory=dict)
    metrics: dict[str, MetricSpec] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)

    @field_validator("dataset_type")
    @classmethod
    def valid_dataset_type(cls, value: str) -> str:
        return value if value in DATASET_TYPES else "generic_tabular"

    @field_validator("column_roles")
    @classmethod
    def valid_roles(cls, value: dict[str, str]) -> dict[str, str]:
        return {str(col): role if role in SUPPORTED_ROLES else "generic_text" for col, role in value.items()}


def normalize_name(value: str) -> str:
    return re.sub(r"_+", "_", "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value))).strip("_")


def safe_schema_profile(df: pd.DataFrame, filename: str | None = None) -> dict[str, Any]:
    columns = []
    for column in df.columns:
        series = df[column]
        samples = [str(value)[:120] for value in series.dropna().astype(str).drop_duplicates().head(5).tolist()]
        numeric = pd.to_numeric(series, errors="coerce")
        numeric_stats = None
        if numeric.notna().sum() >= max(2, int(series.notna().sum() * 0.6)):
            numeric_stats = {
                "min": _safe_number(numeric.min()),
                "max": _safe_number(numeric.max()),
                "mean": _safe_number(numeric.mean()),
                "sum": _safe_number(numeric.sum()),
            }
        date_hint = _date_parse_hint(series)
        columns.append(
            {
                "name": str(column),
                "dtype": str(series.dtype),
                "missing_count": int(series.isna().sum()),
                "unique_count": int(series.nunique(dropna=True)),
                "sample_values": samples,
                "numeric_stats": numeric_stats,
                "date_parse_hint": date_hint,
            }
        )
    return {
        "filename": filename,
        "row_count": int(len(df)),
        "column_count": int(len(df.columns)),
        "columns": columns,
    }


def _safe_number(value: Any) -> float | int | None:
    if pd.isna(value):
        return None
    value = float(value)
    return int(value) if value.is_integer() else round(value, 6)


def _date_parse_hint(series: pd.Series) -> dict[str, Any]:
    if pd.api.types.is_datetime64_any_dtype(series):
        parsed = series
    elif pd.api.types.is_numeric_dtype(series):
        return {"looks_like_date": False, "parseable_count": 0}
    else:
        sample = series.dropna().astype(str).head(50)
        if sample.empty or not sample.str.contains(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}", regex=True).any():
            return {"looks_like_date": False, "parseable_count": 0}
        parsed = pd.to_datetime(sample, errors="coerce")
    parseable = int(pd.Series(parsed).notna().sum())
    return {"looks_like_date": parseable >= 2, "parseable_count": parseable}


class SemanticMapper:
    """Infer business meaning using deterministic rules plus optional LLM validation."""

    def __init__(self, llm_provider: LLMProvider | None = None):
        self.llm_provider = llm_provider or LLMProvider()

    def map_dataframe(self, df: pd.DataFrame, filename: str | None = None, query: str | None = None) -> dict[str, Any]:
        heuristic = self._heuristic_map(df, filename=filename, query=query)
        if not self.llm_provider.is_configured():
            return heuristic.model_dump()
        try:
            asyncio.get_running_loop()
            return heuristic.model_dump()
        except RuntimeError:
            return asyncio.run(self.map_dataframe_async(df, filename=filename, query=query))

    async def map_dataframe_async(self, df: pd.DataFrame, filename: str | None = None, query: str | None = None) -> dict[str, Any]:
        heuristic = self._heuristic_map(df, filename=filename, query=query)
        if not self.llm_provider.is_configured():
            return heuristic.model_dump()
        llm_map = await self._llm_map(df, filename=filename, query=query)
        if llm_map is None:
            return heuristic.model_dump()
        return self._merge_maps(heuristic, llm_map).model_dump()

    def _heuristic_map(self, df: pd.DataFrame, filename: str | None = None, query: str | None = None) -> SemanticMap:
        roles: dict[str, str] = {}
        warnings: list[str] = []
        assumptions: list[str] = []
        for column in df.columns:
            roles[str(column)] = self._role_for_column(df, str(column))

        dataset_type, confidence = self._dataset_type(df, roles, filename)
        metrics = self._metrics_from_roles(df, roles)
        if "revenue" not in metrics:
            warnings.append("No direct revenue metric was detected.")
        if any(role == "amount" for role in roles.values()) and any(role == "transaction_type" for role in roles.values()):
            assumptions.append("Amount is interpreted by transaction_type filters; revenue is not the sum of every amount row.")
        return SemanticMap(
            dataset_type=dataset_type,
            confidence=confidence,
            column_roles=roles,
            metrics=metrics,
            warnings=warnings,
            assumptions=assumptions,
        )

    def _role_for_column(self, df: pd.DataFrame, column: str) -> str:
        name = normalize_name(column)
        series = df[column]
        unique_ratio = series.nunique(dropna=True) / max(1, len(series))
        if "invoice" in name and "date" in name:
            return "invoice_date"
        if "order" in name and "date" in name:
            return "order_date"
        if ("transaction" in name or name in {"date", "created_at", "posted_date"}) and "date" in name:
            return "transaction_date"
        if _date_parse_hint(series)["looks_like_date"]:
            return "transaction_date"
        if name in {"id", "uuid", "guid"} or name.endswith("_id") or name.startswith("id_"):
            if "product" in name or name == "sku":
                return "product"
            if "store" in name or "branch" in name or "shop" in name:
                return "store"
            if "customer" in name:
                return "customer_id"
            if "order" in name:
                return "order_id"
            if "invoice" in name:
                return "invoice_id"
            return "ignore_identifier"
        if unique_ratio >= 0.9 and not pd.api.types.is_numeric_dtype(series) and len(series) >= 10:
            return "ignore_identifier"
        if any(token in name for token in ["transaction_type", "txn_type", "payment_type"]) or (name in {"type", "category"} and _has_transaction_values(series)):
            return "transaction_type"
        if any(token in name for token in ["product", "item", "sku", "article", "food", "dish", "meal", "menu_item"]):
            return "product"
        if any(token in name for token in ["category", "department", "segment", "cuisine", "ingredient", "spice_level"]):
            return "product_category"
        if any(token in name for token in ["customer", "client", "buyer"]):
            return "customer"
        if any(token in name for token in ["store", "branch", "shop"]):
            return "store"
        if "region" in name:
            return "region"
        if "city" in name:
            return "city"
        if "country" in name:
            return "country"
        if any(token in name for token in ["gross_sales", "gross_amount"]):
            return "gross_sales"
        if any(token in name for token in ["net_sales", "net_amount", "net_total"]):
            return "net_sales"
        if any(token in name for token in ["sale", "sales", "revenue", "total_amount", "line_total"]):
            return "sales_revenue"
        if name in {"amount", "amount_rs", "transaction_amount"} or ("amount" in name and "range" not in name):
            return "amount"
        if any(token in name for token in ["qty", "quantity", "units"]):
            return "quantity"
        if any(token in name for token in ["unit_price", "price", "rate"]):
            return "unit_price"
        if any(token in name for token in ["expense", "cost"]):
            return "expense" if "expense" in name else "cost"
        if any(token in name for token in ["profit", "margin"]):
            return "profit"
        if "discount" in name:
            return "discount"
        if name == "tax" or "tax" in name:
            return "tax"
        if "payment" in name:
            return "payment_method"
        numeric_sample = pd.to_numeric(series.dropna(), errors="coerce")
        if pd.api.types.is_numeric_dtype(series) or (not numeric_sample.empty and numeric_sample.notna().mean() >= 0.7):
            return "generic_numeric"
        return "generic_text"

    def _dataset_type(self, df: pd.DataFrame, roles: dict[str, str], filename: str | None) -> tuple[str, float]:
        role_values = set(roles.values())
        filename_norm = normalize_name(filename or "")
        column_names = {normalize_name(column) for column in df.columns}
        retail_signals = {
            "order_id",
            "order_datetime",
            "store_id",
            "region",
            "city",
            "product_id",
            "category",
            "unit_price",
            "quantity",
            "total_sales",
            "profit",
        }
        retail_signal_count = len(retail_signals & column_names)
        if {"invoice_date", "invoice_id"} & role_values or "invoice" in filename_norm:
            return "invoice_sales", 0.88
        if "sku" in " ".join(normalize_name(column) for column in df.columns) or "ecommerce" in filename_norm:
            if {"order_date", "net_sales", "sales_revenue", "customer_id"} & role_values:
                return "ecommerce_orders", 0.86
        if "transaction_type" in role_values and "amount" in role_values:
            transaction_col = _first_by_role(roles).get("transaction_type")
            if transaction_col and transaction_col in df.columns and _has_ledger_values(df[transaction_col]):
                return "transaction_ledger", 0.92
            if "product" in role_values or "store" in role_values:
                return "pos_transactions", 0.9
            return "transaction_ledger", 0.88
        if "quantity" in role_values and "unit_price" in role_values and "product" in role_values:
            return "mart_sales", 0.84
        if retail_signal_count >= 7 and "sales_revenue" in role_values and "profit" in role_values:
            return "retail_sales", 0.9
        if "sales_revenue" in role_values and "product" in role_values:
            return "retail_sales", 0.82
        if "product" in role_values and any("stock" in normalize_name(column) or "inventory" in normalize_name(column) for column in df.columns):
            return "inventory", 0.82
        food_schema = " ".join(normalize_name(column) for column in df.columns)
        if any(token in food_schema for token in ["food", "dish", "meal", "menu", "ingredient", "cuisine", "spice", "calorie"]):
            return "food_dataset", 0.82
        if "customer" in role_values and ("sales_revenue" in role_values or "net_sales" in role_values) and retail_signal_count < 5:
            return "customer_sales", 0.78
        return "generic_tabular", 0.35

    def _metrics_from_roles(self, df: pd.DataFrame, roles: dict[str, str]) -> dict[str, MetricSpec]:
        metrics: dict[str, MetricSpec] = {}
        by_role = _first_by_role(roles)
        transaction_col = by_role.get("transaction_type")
        amount_col = by_role.get("amount")
        revenue_col = by_role.get("net_sales") or by_role.get("sales_revenue") or by_role.get("gross_sales")

        if amount_col and transaction_col:
            metrics["revenue"] = MetricSpec(source_column=amount_col, filter={"column": transaction_col, "include": sorted(SALE_VALUES), "subtract": sorted(REFUND_VALUES)}, aggregation="sum")
            metrics["expense"] = MetricSpec(source_column=amount_col, filter={"column": transaction_col, "include": sorted(EXPENSE_VALUES)}, aggregation="sum")
            metrics["credit_outstanding"] = MetricSpec(source_column=amount_col, filter={"column": transaction_col, "include": sorted(CREDIT_VALUES)}, aggregation="sum")
        elif revenue_col:
            metrics["revenue"] = MetricSpec(source_column=revenue_col, aggregation="sum")
        elif by_role.get("quantity") and by_role.get("unit_price"):
            metrics["revenue"] = MetricSpec(aggregation="derived", expression="quantity * unit_price")

        for metric, role in [
            ("quantity", "quantity"),
            ("cost", "cost"),
            ("expense", "expense"),
            ("profit", "profit"),
            ("discount", "discount"),
            ("tax", "tax"),
            ("date", next((role for role in ("order_date", "invoice_date", "transaction_date") if by_role.get(role)), "transaction_date")),
            ("product", "product"),
            ("category", "product_category"),
            ("customer", "customer"),
            ("store", "store"),
            ("region", "region"),
        ]:
            col = by_role.get(role)
            if col and metric not in metrics:
                metrics[metric] = MetricSpec(source_column=col, aggregation="sum" if metric in {"quantity", "cost", "expense", "profit", "discount", "tax"} else "derived")
        return metrics

    async def _llm_map(self, df: pd.DataFrame, filename: str | None, query: str | None) -> SemanticMap | None:
        prompt = (
            "You are a senior data analyst. Your task is to infer the business meaning of dataset columns from schema and sample values. "
            "Return strict JSON only. Do not calculate final numbers. Do not invent columns. Map each original column to a semantic role. "
            "Detect whether this is a mart/retail/sales/invoice/transaction/inventory dataset. If amount columns depend on transaction_type/category filters, define those filters clearly.\n\n"
            f"Allowed roles: {sorted(SUPPORTED_ROLES)}\n"
            f"Allowed dataset types: {sorted(DATASET_TYPES)}\n"
            f"Optional user query: {query or ''}\n"
            f"Schema profile JSON:\n{json.dumps(safe_schema_profile(df, filename), default=str)[:10000]}"
        )
        text = await self.llm_provider.generate(prompt, system_prompt="Return strict JSON only. Do not calculate final numbers.", json_mode=True)
        if not text:
            return None
        try:
            payload = _extract_json(text)
            return SemanticMap.model_validate(payload)
        except (ValueError, ValidationError, TypeError, json.JSONDecodeError):
            return None

    def _merge_maps(self, heuristic: SemanticMap, llm_map: SemanticMap) -> SemanticMap:
        roles = dict(heuristic.column_roles)
        for column, role in llm_map.column_roles.items():
            if column in roles and role in SUPPORTED_ROLES and roles[column] in {"generic_numeric", "generic_text", "ignore_identifier"}:
                roles[column] = role
        merged = self._heuristic_map(pd.DataFrame(columns=list(roles)), filename=None)
        metrics = dict(heuristic.metrics)
        metrics.update({key: value for key, value in llm_map.metrics.items() if value.source_column})
        return SemanticMap(
            dataset_type=llm_map.dataset_type if llm_map.confidence >= heuristic.confidence else heuristic.dataset_type,
            confidence=max(heuristic.confidence, llm_map.confidence),
            column_roles=roles,
            metrics=metrics,
            warnings=list(dict.fromkeys(heuristic.warnings + llm_map.warnings)),
            assumptions=list(dict.fromkeys(heuristic.assumptions + llm_map.assumptions + merged.assumptions)),
        )


def _has_transaction_values(series: pd.Series) -> bool:
    values = {str(value).strip().upper() for value in series.dropna().astype(str).unique()[:30]}
    return bool(values & (SALE_VALUES | EXPENSE_VALUES | CREDIT_VALUES | REFUND_VALUES))


def _has_ledger_values(series: pd.Series) -> bool:
    values = {str(value).strip().upper() for value in series.dropna().astype(str).unique()[:30]}
    return bool(values & (EXPENSE_VALUES | CREDIT_VALUES | REFUND_VALUES))


def _first_by_role(roles: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for column, role in roles.items():
        out.setdefault(role, column)
    return out


def _extract_json(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    return json.loads(cleaned)
