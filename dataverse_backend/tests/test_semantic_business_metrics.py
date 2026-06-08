from __future__ import annotations

import pandas as pd

from app.services.business_metrics import answer_business_query, calculate_business_metrics
from app.services.analysis_pipeline import AnalysisPipeline
from app.services.query_planner import QueryPlanner
from app.services.semantic_mapper import SemanticMapper


def _mapped_metrics(df: pd.DataFrame, filename: str = "data.csv", query: str = "show revenue by month"):
    semantic_map = SemanticMapper().map_dataframe(df, filename=filename, query=query)
    business_metrics = calculate_business_metrics(df, semantic_map)
    query_plan = QueryPlanner().plan(query, semantic_map, {"row_count": len(df), "columns": list(df.columns)})
    query_answer = answer_business_query(query_plan, business_metrics)
    return semantic_map, business_metrics, query_plan, query_answer


def test_ai_khata_transaction_report_revenue_uses_sales_filter_only():
    df = pd.DataFrame(
        {
            "Date": ["2026-05-01", "2026-05-01", "2026-05-01", "2026-05-01"],
            "Time": ["11:43:40", "11:43:23", "11:43:10", "11:43:05"],
            "Category": ["UDHAAR", "EXPENSE", "SALES", "SALES"],
            "Item/Customer": ["Ali", "Rent", "General Entry", "burger"],
            "Amount (Rs)": [500, 500, 5000, 2000],
        }
    )

    semantic_map, metrics, query_plan, query_answer = _mapped_metrics(df, "ai_khata.csv")

    assert semantic_map["dataset_type"] == "transaction_ledger"
    assert semantic_map["column_roles"]["Category"] == "transaction_type"
    assert semantic_map["column_roles"]["Amount (Rs)"] == "amount"
    assert semantic_map["metrics"]["revenue"]["filter"]["column"] == "Category"
    assert metrics["total_revenue"] == 7000
    assert metrics["total_expenses"] == 500
    assert metrics["sales_transaction_count"] == 2
    assert metrics["revenue_by_month"] == [{"period": "2026-05", "revenue": 7000}]
    assert query_plan["intent"] == "revenue_trend"
    assert query_answer["tables"][0]["rows"] == [{"period": "2026-05", "revenue": 7000}]
    assert any("trend cannot be reliably detected" in item for item in metrics["data_limitations"])


def test_standard_mart_sales_uses_sales_column_for_revenue():
    df = pd.DataFrame(
        {
            "Date": ["2026-01-01", "2026-01-15", "2026-02-01"],
            "Product": ["Rice", "Oil", "Rice"],
            "Category": ["Grocery", "Grocery", "Grocery"],
            "Quantity": [2, 1, 3],
            "UnitPrice": [100, 500, 100],
            "Sales": [200, 500, 300],
        }
    )

    semantic_map, metrics, _query_plan, _query_answer = _mapped_metrics(df, "mart_sales.csv")

    assert semantic_map["dataset_type"] == "mart_sales"
    assert semantic_map["column_roles"]["Sales"] == "sales_revenue"
    assert metrics["total_revenue"] == 1000
    assert metrics["revenue_by_month"] == [{"period": "2026-01", "revenue": 700}, {"period": "2026-02", "revenue": 300}]
    assert {"product": "Rice", "revenue": 500} in metrics["top_products"]


def test_trending_product_report_uses_computed_product_charts():
    df = pd.DataFrame(
        {
            "Date": ["2026-01-01", "2026-01-15", "2026-02-01", "2026-02-12", "2026-03-01"],
            "Product": ["Rice", "Oil", "Rice", "Oil", "Rice"],
            "Category": ["Grocery", "Grocery", "Grocery", "Grocery", "Grocery"],
            "Quantity": [2, 1, 3, 4, 5],
            "Sales": [200, 500, 300, 800, 500],
            "Profit": [30, 75, 45, 120, 80],
        }
    )

    report = AnalysisPipeline().run_full_analysis(df, query="make a report of trending products in the form charts", run_predictions=False, run_xai=False)

    titles = [chart["title"] for chart in report["charts"]]
    assert "Top 10 Products by Revenue" in titles
    assert "Top 10 Products by Quantity" in titles
    assert "Monthly Revenue Trend for Top Products" in titles
    assert "Revenue Share" in titles
    assert report["product_analysis"]["top_products_by_revenue"][0] == {"product": "Oil", "revenue": 1300}
    assert report["business_summary"] == {}
    assert "sales Rs 0" not in report["executive_summary"]


def test_invoice_dataset_derives_revenue_from_quantity_times_price():
    df = pd.DataFrame(
        {
            "InvoiceDate": ["2026-03-01", "2026-03-02"],
            "InvoiceNo": ["INV-1", "INV-2"],
            "Item": ["Pen", "Notebook"],
            "Qty": [10, 3],
            "Price": [5, 50],
        }
    )

    semantic_map, metrics, _query_plan, _query_answer = _mapped_metrics(df, "invoices.csv")

    assert semantic_map["dataset_type"] == "invoice_sales"
    assert semantic_map["column_roles"]["InvoiceDate"] == "invoice_date"
    assert semantic_map["metrics"]["revenue"]["expression"] == "quantity * unit_price"
    assert metrics["total_revenue"] == 200
    assert metrics["revenue_by_month"] == [{"period": "2026-03", "revenue": 200}]


def test_ecommerce_dataset_uses_net_amount_for_revenue():
    df = pd.DataFrame(
        {
            "order_date": ["2026-04-01", "2026-04-02"],
            "sku": ["SKU-1", "SKU-2"],
            "customer_id": ["C1", "C2"],
            "net_amount": [1200, 800],
            "discount": [100, 50],
            "region": ["North", "South"],
        }
    )

    semantic_map, metrics, _query_plan, _query_answer = _mapped_metrics(df, "ecommerce_orders.csv")

    assert semantic_map["dataset_type"] == "ecommerce_orders"
    assert semantic_map["column_roles"]["net_amount"] == "net_sales"
    assert metrics["total_revenue"] == 2000
    assert metrics["revenue_by_month"] == [{"period": "2026-04", "revenue": 2000}]


def test_generic_dataset_does_not_hallucinate_sales_metrics():
    df = pd.DataFrame(
        {
            "Name": ["Alpha", "Beta", "Gamma"],
            "Score": [10, 20, 30],
            "Notes": ["ok", "review", "ok"],
        }
    )

    semantic_map, metrics, query_plan, query_answer = _mapped_metrics(df, "generic.csv")

    assert semantic_map["dataset_type"] == "generic_tabular"
    assert "revenue" not in semantic_map["metrics"]
    assert metrics["total_revenue"] is None
    assert query_plan["intent"] == "revenue_trend"
    assert query_answer["tables"][0]["rows"] == []
    assert any("No revenue metric" in item or "Revenue metric unavailable" in item for item in metrics["data_limitations"])


def test_food_dataset_is_not_labeled_generic():
    df = pd.DataFrame(
        {
            "food_name": ["Pizza", "Burger", "Biryani"],
            "food_description": ["cheesy flatbread", "grilled sandwich", "rice dish"],
            "main_ingredient": ["Cheese", "Beef", "Rice"],
            "cuisine": ["Italian", "American", "Pakistani"],
            "spice_level": ["Low", "Medium", "High"],
            "calories": [570, 650, 720],
            "category": ["Fast Food", "Fast Food", "Rice"],
        }
    )

    semantic_map = SemanticMapper().map_dataframe(df, filename="food_dataset_extended.csv")
    profile = AnalysisPipeline().profile_dataset(df)

    assert semantic_map["dataset_type"] == "food_dataset"
    assert profile["dataset_type"] == "food_dataset"
    assert profile["column_roles"]["food_name"] == "product"


def test_food_catalog_report_uses_frequency_not_sales_language():
    rows = []
    categories = ["Breakfast", "Lunch", "Dinner", "Dessert"]
    ingredients = ["Egg", "Chicken", "Rice", "Chocolate"]
    cuisines = ["American", "Pakistani", "Italian"]
    spices = ["Low", "Medium", "High"]
    for index in range(60):
        rows.append(
            {
                "food_name": f"Food {index % 8}",
                "food_description": f"Description {index % 8}",
                "main_ingredient": ingredients[index % len(ingredients)],
                "cuisine": cuisines[index % len(cuisines)],
                "spice_level": spices[index % len(spices)],
                "calories": 200 + (index % 10) * 60,
                "category": categories[index % len(categories)],
            }
        )
    df = pd.DataFrame(rows)

    report = AnalysisPipeline().run_full_analysis(
        df,
        query="What is the most sold product?",
        target_column="category",
        task_type="classification",
        run_predictions=True,
        run_xai=True,
        use_llm=False,
        filename="food_dataset_extended (1).csv",
    )

    assert report["semantic_map"]["dataset_type"] == "food_dataset"
    assert report["query_answer"]["answer"].startswith("This dataset does not contain sales or quantity columns")
    assert any("most-sold product analysis" in warning for warning in report["warnings"])
    assert any(chart["title"] == "Most frequent food item" for chart in report["charts"])
    assert any(chart["title"] == "Distribution of calories" for chart in report["charts"])
    calories_chart = next(chart for chart in report["charts"] if chart["title"] == "Distribution of calories")
    assert calories_chart["x_key"] == "bin"
    assert all(row["bin"] and str(row["bin"]).lower() != "n/a" for row in calories_chart["data"])
    assert all(str(row[chart["x_key"]]).strip().lower() not in {"", "n/a", "nan", "none"} for chart in report["charts"] for row in chart["data"])
    assert not any(chart["title"] == "Model feature importance" and not chart.get("x_key") for chart in report["charts"])
    assert "most sold product" not in report["executive_summary"].lower()
    assert "Most frequent food item" in [table["title"] for table in report["product_analysis"]["tables"]]
    assert any("leakage" in warning.lower() or "Perfect accuracy may indicate" in warning for warning in report["warnings"])


def test_retail_dataset_prefers_retail_sales_over_customer_sales():
    df = pd.DataFrame(
        {
            "order_id": ["ORD_1", "ORD_2", "ORD_3", "ORD_4"],
            "order_datetime": ["2026-01-01 10:00:00", "2026-01-02 10:00:00", "2026-01-03 10:00:00", "2026-01-04 10:00:00"],
            "store_id": ["STORE_1", "STORE_1", "STORE_2", "STORE_2"],
            "region": ["Punjab", "Punjab", "Sindh", "Sindh"],
            "city": ["Lahore", "Lahore", "Karachi", "Karachi"],
            "product_id": ["PROD_1", "PROD_2", "PROD_1", "PROD_3"],
            "category": ["Electronics", "Grocery", "Electronics", "Fashion"],
            "subcategory": ["Phones", "Staples", "Phones", "Shoes"],
            "unit_price": [200, 20, 200, 80],
            "quantity": [2, 5, 1, 3],
            "discount": [0, 1, 0, 2],
            "total_sales": [400, 99, 200, 238],
            "profit": [60, 15, 30, 35.7],
            "customer_id": ["C1", "C2", "C3", "C4"],
            "customer_type": ["Member", "Guest", "Member", "Guest"],
            "payment_method": ["Card", "Cash", "Card", "Cash"],
            "online_order": [True, False, True, False],
            "stockout_flag": [False, False, True, False],
            "weekday": ["Mon", "Tue", "Wed", "Thu"],
            "month": ["Jan", "Jan", "Jan", "Jan"],
        }
    )

    semantic_map = SemanticMapper().map_dataframe(df, filename="retail_mart_final.csv")

    assert semantic_map["dataset_type"] in {"retail_sales", "mart_sales"}
    assert semantic_map["dataset_type"] != "customer_sales"
    assert semantic_map["column_roles"]["product_id"] == "product"
    assert semantic_map["column_roles"]["store_id"] == "store"
    assert semantic_map["column_roles"]["order_datetime"] == "order_date"
    assert semantic_map["metrics"]["date"]["source_column"] == "order_datetime"


def test_predict_sales_uses_regression_target_not_category_classifier():
    rows = []
    for idx in range(60):
        quantity = 1 + (idx % 4)
        unit_price = 100 + (idx % 6) * 10
        rows.append(
            {
                "order_id": f"ORD_{idx:05d}",
                "order_datetime": f"2026-01-{(idx % 28) + 1:02d} 10:00:00",
                "store_id": f"STORE_{idx % 3}",
                "region": ["Punjab", "Sindh", "KPK"][idx % 3],
                "city": f"City_{idx % 4}",
                "product_id": f"PROD_{idx % 8}",
                "category": ["Electronics", "Grocery", "Fashion"][idx % 3],
                "subcategory": f"Sub_{idx % 5}",
                "unit_price": unit_price,
                "quantity": quantity,
                "discount": 0,
                "total_sales": quantity * unit_price,
                "profit": round(quantity * unit_price * 0.15, 2),
                "customer_id": f"CUST_{idx:05d}",
                "customer_type": "Member" if idx % 2 == 0 else "Guest",
                "payment_method": "Card",
                "online_order": idx % 2 == 0,
                "stockout_flag": False,
                "weekday": "Mon",
                "month": "Jan",
            }
        )
    df = pd.DataFrame(rows)

    report = AnalysisPipeline().run_full_analysis(df, query="predict sales", use_llm=False)

    assert report["query_plan"]["intent"] == "prediction"
    assert report["prediction"]["task_type"] == "regression"
    assert str(report["prediction"]["target_column"]).lower() == "total_sales"


def test_top_products_query_normalizes_product_id_keys_for_quantity_rankings():
    df = pd.DataFrame(
        {
            "order_id": ["ORD_1", "ORD_2", "ORD_3", "ORD_4"],
            "order_datetime": ["2026-01-01 10:00:00", "2026-01-02 10:00:00", "2026-01-03 10:00:00", "2026-01-04 10:00:00"],
            "product_id": ["PROD_6382", "PROD_1000", "PROD_6382", "PROD_2000"],
            "category": ["Electronics", "Grocery", "Electronics", "Fashion"],
            "region": ["Punjab", "Punjab", "Sindh", "Sindh"],
            "quantity": [4, 1, 3, 2],
            "total_sales": [400, 50, 360, 180],
            "profit": [60, 8, 54, 27],
        }
    )

    _semantic_map, metrics, query_plan, query_answer = _mapped_metrics(df, "retail_mart_final.csv", query="top products")

    assert query_plan["intent"] == "top_product"
    assert metrics["top_products_by_quantity"][0] == {"product": "PROD_6382", "quantity": 7}
    assert "Top product by quantity is PROD_6382 with 7 units." in query_answer["answer"]
