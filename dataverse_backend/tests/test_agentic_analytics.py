import pandas as pd
import pytest

from app.services.agent import DataAnalysisAgent
from app.services.analysis_planner import plan_analysis
from app.services.analytics_tools import AnalyticsTools
from app.services.dataset_classifier import classify_dataset
from app.services.data_profiler import profile_dataframe
from app.services.llm_provider import LLMProvider


def sample_sales_df():
    return pd.DataFrame(
        {
            "order_date": [
                "2026-01-05",
                "2026-01-12",
                "2026-02-02",
                "2026-02-09",
                "2026-03-03",
                "2026-03-15",
            ],
            "product_name": ["Alpha", "Beta", "Alpha", "Beta", "Alpha", "Beta"],
            "category": ["A", "B", "A", "B", "A", "B"],
            "region": ["North", "South", "North", "South", "North", "South"],
            "customer_id": ["c1", "c2", "c1", "c3", "c4", "c3"],
            "quantity": [10, 20, 20, 15, 70, 10],
            "revenue": [100, 300, 200, 250, 900, 120],
            "profit": [30, 90, 70, 80, 300, 20],
        }
    )


def sample_business_leads_df():
    return pd.DataFrame(
        {
            "row_num": [1, 2, 3, 4],
            "business_name": ["Gulf Alpha LLC", "Doha Build Co", "Riyadh Logistics", "Muscat Services"],
            "business_website": [None, "", None, ""],
            "business_number_of_employees_range": ["11-50", "51-200", "201-500", "1-10"],
            "business_yearly_revenue_range": ["$1M-$10M", "$10M-$50M", "$50M-$100M", "$100K-$500K"],
            "business_country_name": ["UAE", "Qatar", "Saudi Arabia", "Oman"],
            "business_region": ["Dubai", "Doha", "Riyadh", "Muscat"],
            "business_naics_description": ["Construction", "Construction", "Logistics", "Consulting"],
            "created_at": ["2026-04-01", "2026-04-01", "2026-04-01", "2026-04-01"],
            "business_id": ["b1", "b2", "b3", "b4"],
        }
    )


def sample_customer_df():
    return pd.DataFrame(
        {
            "customer_name": ["Alice", "Bob", "Cara", "Dan"],
            "email": ["a@example.com", "b@example.com", "c@example.com", "d@example.com"],
            "country": ["UAE", "UAE", "Qatar", "Oman"],
            "signup_date": ["2026-01-01", "2026-01-15", "2026-02-10", "2026-02-20"],
            "spend": [1200, 300, 950, 100],
            "segment": ["VIP", "Standard", "VIP", "Starter"],
        }
    )


def sample_finance_df():
    return pd.DataFrame(
        {
            "transaction_date": ["2026-01-01", "2026-01-15", "2026-02-01", "2026-02-20"],
            "account": ["Main", "Main", "Ops", "Ops"],
            "expense": [200, 0, 500, 150],
            "income": [1000, 800, 0, 0],
            "category": ["Software", "Services", "Payroll", "Software"],
        }
    )


def test_profile_dataframe_detects_business_columns_and_quality():
    profile = profile_dataframe(sample_sales_df())

    assert profile["row_count"] == 6
    assert profile["semantic_columns"]["date"] == "order_date"
    assert profile["semantic_columns"]["product"] == "product_name"
    assert profile["semantic_columns"]["revenue"] == "revenue"
    assert profile["semantic_columns"]["quantity"] == "quantity"
    assert profile["semantic_columns"]["category"] == "category"
    assert profile["semantic_columns"]["region"] == "region"
    assert profile["semantic_columns"]["customer"] == "customer_id"
    assert profile["quality"]["duplicate_rows"] == 0


def test_profile_dataframe_detects_business_leads_roles_without_product_or_customer():
    profile = profile_dataframe(sample_business_leads_df())

    assert profile["dataset_type"] == "business_leads"
    assert profile["semantic_columns"]["business_name"] == "business_name"
    assert profile["semantic_columns"]["website"] == "business_website"
    assert profile["semantic_columns"]["country"] == "business_country_name"
    assert profile["semantic_columns"]["industry"] == "business_naics_description"
    assert profile["semantic_columns"]["employee_range"] == "business_number_of_employees_range"
    assert profile["semantic_columns"]["revenue_range"] == "business_yearly_revenue_range"
    assert profile["semantic_columns"]["business_id"] == "business_id"
    assert profile["semantic_columns"].get("product") is None
    assert profile["semantic_columns"].get("customer") is None
    assert profile["column_roles"]["business_name"] == "business_name"
    assert profile["column_roles"]["business_id"] == "business_id"


def test_dataset_classifier_identifies_business_leads_schema():
    result = classify_dataset(sample_business_leads_df(), filename="gulf_no_website_businesses_20260401094655_core.csv")

    assert result["dataset_type"] == "business_leads"
    assert result["confidence"] >= 0.7
    assert "business_name" in result["signals"]
    assert "website" in result["signals"]


def test_trending_products_uses_recent_vs_previous_period_not_total_sales():
    result = AnalyticsTools(sample_sales_df()).trending_products(limit=3)

    rows = result["table"]["rows"]
    assert rows[0]["product_name"] == "Alpha"
    assert rows[0]["recent_revenue"] == 900
    assert rows[0]["previous_revenue"] == 200
    assert rows[0]["growth_pct"] == 350.0
    assert result["chart"]["type"] == "bar"


def test_trending_products_falls_back_when_date_column_missing():
    df = sample_sales_df().drop(columns=["order_date"])
    result = AnalyticsTools(df).trending_products(limit=2)

    assert result["warning"]
    assert result["intent"] == "top_products"
    assert result["table"]["rows"][0]["product_name"] == "Alpha"


def test_agent_answers_top_products_with_table_and_chart():
    result = DataAnalysisAgent().answer(sample_sales_df(), "Which products have the highest sales?")

    assert result["intent"] == "top_products"
    assert "Alpha" in result["answer"]
    assert result["tables"][0]["rows"][0]["product_name"] == "Alpha"
    assert result["charts"][0]["type"] == "bar"
    assert "Calculated" in result["method"]


def test_agent_business_leads_overview_is_not_data_quality_only():
    result = DataAnalysisAgent().answer(
        sample_business_leads_df(),
        "tell me about this data",
        filename="gulf_no_website_businesses_20260401094655_core.csv",
    )

    assert result["dataset_type"] == "business_leads"
    assert result["intent"] == "dataset_overview"
    assert "business leads" in result["answer"].lower()
    assert "4 business records" in result["answer"]
    assert "10 columns" in result["answer"]
    assert "website" in result["answer"].lower()
    assert result["profile"]["semantic_columns"]["business_name"] == "business_name"
    assert not any("product" in item.lower() for item in result["suggestions"])
    assert "Which countries have the most businesses?" in result["suggestions"]


def test_agent_business_recommendations_are_grounded_in_lead_data():
    result = DataAnalysisAgent().answer(
        sample_business_leads_df(),
        "give me business recommendations",
        filename="gulf_no_website_businesses_20260401094655_core.csv",
    )

    assert result["dataset_type"] == "business_leads"
    assert result["intent"] == "outreach_recommendations"
    assert "missing websites" in result["answer"].lower()
    assert "Construction" in result["answer"]
    assert result["tables"][0]["title"] == "Lead scoring"
    assert result["tables"][0]["rows"][0]["business_name"] == "Riyadh Logistics"
    assert not any("stock" in recommendation.lower() for recommendation in result["recommendations"])


def test_agent_rejects_sales_intent_for_business_leads_dataset():
    result = DataAnalysisAgent().answer(sample_business_leads_df(), "top products")

    assert result["intent"] == "unsupported_intent"
    assert "does not contain product sales data" in result["answer"]
    assert "top countries" in result["answer"].lower()
    assert not result.get("charts")


def test_analysis_planner_routes_vague_business_question_to_lead_strategy():
    profile = profile_dataframe(sample_business_leads_df())
    plan = plan_analysis(
        "what should I do with this list?",
        dataset_type="business_leads",
        semantic_columns=profile["semantic_columns"],
    )

    assert plan.answerable is True
    assert plan.intent == "outreach_recommendations"
    assert plan.tool_name == "business_leads.outreach_recommendations"
    assert plan.required_roles == ["website", "country", "industry"]


def test_agent_answers_top_customers_from_customer_dataset():
    result = DataAnalysisAgent().answer(sample_customer_df(), "who are my best customers?")

    assert result["dataset_type"] == "customer"
    assert result["intent"] == "top_customers"
    assert "Alice" in result["answer"]
    assert result["tables"][0]["rows"][0]["customer_name"] == "Alice"
    assert not any("product" in item.lower() for item in result["suggestions"])


def test_agent_answers_finance_expense_summary_from_actual_columns():
    result = DataAnalysisAgent().answer(sample_finance_df(), "expense summary by category")

    assert result["dataset_type"] == "finance"
    assert result["intent"] == "expense_summary"
    assert "Payroll" in result["answer"]
    assert result["tables"][0]["rows"][0]["category"] == "Payroll"
    assert result["tables"][0]["rows"][0]["total_expense"] == 500
    assert {"category": "Software", "total_expense": 350} in result["tables"][0]["rows"]


def test_agent_asks_clarification_when_sales_forecast_requested_from_business_leads():
    result = DataAnalysisAgent().answer(sample_business_leads_df(), "forecast next month revenue")

    assert result["intent"] == "clarification_needed"
    assert "business lead records" in result["answer"].lower()
    assert "date-stamped numeric revenue" in result["answer"].lower()


def test_single_column_dataset_gets_limited_generic_overview():
    df = pd.DataFrame({"AI Khata Report": [f"Entry {i}" for i in range(15)]})

    result = DataAnalysisAgent().answer(df, "tell me about this data")

    assert result["dataset_type"] == "generic"
    assert result["intent"] == "dataset_overview"
    assert "only one column and 15 rows" in result["answer"]
    assert "product/date/revenue" not in result["answer"].lower()
    assert result["suggestions"] == [
        "Summarize this dataset.",
        "Which columns have missing values?",
        "Show unique values by column.",
        "Find important patterns.",
    ]


@pytest.mark.asyncio
async def test_llm_provider_prefers_configured_provider_and_falls_back(monkeypatch):
    calls = []

    async def fake_openai(prompt):
        calls.append("openai")
        raise RuntimeError("openai unavailable")

    async def fake_gemini(prompt):
        calls.append("gemini")
        return "gemini narrative"

    provider = LLMProvider(
        provider="openai",
        openai_api_key="x",
        gemini_api_key="y",
        openai_generate=fake_openai,
        gemini_generate=fake_gemini,
    )

    assert await provider.generate("summarize") == "gemini narrative"
    assert calls == ["openai", "gemini"]
