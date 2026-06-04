"""Question-answering tools for AI Khata/business transaction datasets."""
from __future__ import annotations

from typing import Any

import pandas as pd

from .ai_khata import (
    EXPENSE_LABEL,
    SALES_LABEL,
    UDHAAR_LABEL,
    ai_khata_columns,
    business_summary,
    grouped_items,
    monthly_sales_revenue,
    transaction_type_totals,
)
from .data_profiler import profile_dataframe


class AIKhataTools:
    def __init__(self, df: pd.DataFrame):
        self.df = df.copy()
        self.profile = profile_dataframe(self.df)
        self.summary = business_summary(self.df)
        self.columns = ai_khata_columns(self.df)

    def _base_result(self, intent: str, method: str) -> dict[str, Any]:
        return {
            "intent": intent,
            "dataset_type": self.profile.get("dataset_type", "business_transaction_dataset"),
            "answer": "",
            "method": method,
            "tables": [],
            "charts": [],
            "warnings": [],
            "recommendations": [],
            "profile": self.profile,
            "business_summary": self.summary,
        }

    def _table(self, columns: list[str], rows: list[dict[str, Any]], title: str) -> dict[str, Any]:
        return {"title": title, "columns": columns, "rows": rows}

    def _chart(self, chart_type: str, title: str, data: list[dict[str, Any]], x_key: str, y_key: str) -> dict[str, Any]:
        return {"type": chart_type, "title": title, "data": data, "x_key": x_key, "y_key": y_key}

    def _finish(self, result: dict[str, Any]) -> dict[str, Any]:
        if result.get("tables"):
            result["table"] = result["tables"][0]
        if result.get("charts"):
            result["chart"] = result["charts"][0]
        if result.get("warnings"):
            result["warning"] = result["warnings"][0]
        return result

    def dataset_overview(self) -> dict[str, Any]:
        result = self._base_result(
            "dataset_overview",
            "Parsed AI Khata report metadata, summary values, and transaction rows by Category.",
        )
        result["answer"] = (
            f"{self.summary.get('shop_name') or 'This shop'} has sales of Rs {self.summary.get('total_sales', 0):,}, "
            f"expenses of Rs {self.summary.get('total_expenses', 0):,}, udhaar outstanding of Rs "
            f"{self.summary.get('udhaar_outstanding', 0):,}, and net profit of Rs {self.summary.get('net_profit', 0):,}. "
            "Sales, expenses, and udhaar are calculated from separate transaction types, not by summing all Amount rows together."
        )
        rows = [{"metric": key, "value": value} for key, value in self.summary.items()]
        result["tables"].append(self._table(["metric", "value"], rows, "Business summary"))
        result["recommendations"].append("Use SALES rows for revenue, EXPENSE rows for costs, and UDHAAR rows for outstanding credit.")
        return self._finish(result)

    def revenue_trend(self, period: str = "M") -> dict[str, Any]:
        result = self._base_result(
            "revenue_trend",
            "Filtered Category == SALES, parsed Date, grouped by period, and summed Amount.",
        )
        rows = monthly_sales_revenue(self.df, period=period)
        result["tables"].append(self._table(["period", "sales_revenue"], rows, "Sales revenue by period"))
        result["charts"].append(self._chart("line", "Sales revenue by period", rows, "period", "sales_revenue"))
        if len(rows) == 1:
            result["answer"] = (
                f"Sales revenue is Rs {rows[0]['sales_revenue']:,} in {rows[0]['period']}. "
                "Only one period is available, so a trend cannot be reliably detected."
            )
            result["warnings"].append("Only one period is available, so a trend cannot be reliably detected.")
        elif len(rows) >= 2:
            first = rows[0]["sales_revenue"]
            last = rows[-1]["sales_revenue"]
            change_pct = ((last - first) / first * 100) if first else 0
            result["answer"] = f"Sales revenue moved from Rs {first:,.2f} to Rs {last:,.2f}, a {change_pct:.1f}% change."
        else:
            result["answer"] = "No SALES rows with valid dates and amounts were available for revenue by period."
            result["warnings"].append("No valid SALES rows found for revenue trend.")
        return self._finish(result)

    def sales_items(self, limit: int = 10) -> dict[str, Any]:
        result = self._base_result(
            "sales_items",
            "Filtered Category == SALES and grouped Item/Customer as product_or_item.",
        )
        rows = grouped_items(self.df, SALES_LABEL, "sales_revenue")[:limit]
        result["tables"].append(self._table([self.columns.get("item_customer") or "Item/Customer", "sales_revenue"], rows, "Sales items"))
        result["charts"].append(self._chart("bar", "Sales items", rows, self.columns.get("item_customer") or "Item/Customer", "sales_revenue"))
        if rows:
            leader = rows[0]
            item_col = self.columns.get("item_customer") or "Item/Customer"
            result["answer"] = f"{leader[item_col]} is the largest sales item at Rs {leader['sales_revenue']:,}."
        else:
            result["answer"] = "No SALES item rows were available."
        return self._finish(result)

    def expense_summary(self, limit: int = 10) -> dict[str, Any]:
        result = self._base_result(
            "expense_summary",
            "Filtered Category == EXPENSE and grouped Item/Customer as expense_description.",
        )
        rows = grouped_items(self.df, EXPENSE_LABEL, "total_expense")[:limit]
        result["tables"].append(self._table([self.columns.get("item_customer") or "Item/Customer", "total_expense"], rows, "Expense summary"))
        if rows:
            result["charts"].append(self._chart("bar", "Expense summary", rows, self.columns.get("item_customer") or "Item/Customer", "total_expense"))
        total = self.summary.get("total_expenses", 0)
        result["answer"] = f"Total expenses are Rs {total:,}. Expenses are calculated only from Category == EXPENSE rows."
        return self._finish(result)

    def udhaar_summary(self, limit: int = 10) -> dict[str, Any]:
        result = self._base_result(
            "udhaar_summary",
            "Filtered Category == UDHAAR and grouped Item/Customer as customer.",
        )
        rows = grouped_items(self.df, UDHAAR_LABEL, "udhaar_outstanding")[:limit]
        result["tables"].append(self._table([self.columns.get("item_customer") or "Item/Customer", "udhaar_outstanding"], rows, "Udhaar outstanding"))
        if rows:
            result["charts"].append(self._chart("bar", "Udhaar outstanding", rows, self.columns.get("item_customer") or "Item/Customer", "udhaar_outstanding"))
        total = self.summary.get("udhaar_outstanding", 0)
        result["answer"] = f"Udhaar outstanding is Rs {total:,}. This uses only Category == UDHAAR rows."
        return self._finish(result)

    def profit_summary(self) -> dict[str, Any]:
        result = self._base_result(
            "profit_summary",
            "Calculated net profit as SALES minus EXPENSE, using parsed report summary when available.",
        )
        rows = [
            {"metric": "sales", "amount": self.summary.get("total_sales", 0)},
            {"metric": "expenses", "amount": self.summary.get("total_expenses", 0)},
            {"metric": "net_profit", "amount": self.summary.get("net_profit", 0)},
        ]
        result["answer"] = (
            f"Net profit is Rs {self.summary.get('net_profit', 0):,} "
            f"({self.summary.get('profit_status', 'Profit')}). It is sales minus expenses; udhaar is not counted as sales revenue."
        )
        result["tables"].append(self._table(["metric", "amount"], rows, "Profit summary"))
        result["charts"].append(self._chart("bar", "Profit summary", rows, "metric", "amount"))
        return self._finish(result)

    def transaction_type_performance(self, limit: int = 10) -> dict[str, Any]:
        result = self._base_result(
            "transaction_type_performance",
            "Grouped Category as transaction type and separately analyzed SALES items.",
        )
        type_rows = transaction_type_totals(self.df)[:limit]
        sales_rows = grouped_items(self.df, SALES_LABEL, "sales_revenue")[:limit]
        result["tables"].append(self._table(["transaction_type", "amount"], type_rows, "Transaction type totals"))
        result["tables"].append(self._table([self.columns.get("item_customer") or "Item/Customer", "sales_revenue"], sales_rows, "Sales items"))
        result["charts"].append(self._chart("bar", "Transaction type totals", type_rows, "transaction_type", "amount"))
        leader = type_rows[0] if type_rows else None
        sales_sentence = ""
        if sales_rows:
            item_col = self.columns.get("item_customer") or "Item/Customer"
            sales_sentence = " For sales items, " + " and ".join(
                f"{row[item_col]} has Rs {row['sales_revenue']:,}" for row in sales_rows[:3]
            ) + "."
        if leader:
            result["answer"] = (
                f"{leader['transaction_type']} is the largest transaction type with Rs {leader['amount']:,}. "
                "Category is transaction type here, not product category."
                f"{sales_sentence} Real product category analysis is limited because there is no separate product category column."
            )
        else:
            result["answer"] = "No transaction categories were available to compare."
        result["warnings"].append("Category is transaction type, not product category.")
        return self._finish(result)
