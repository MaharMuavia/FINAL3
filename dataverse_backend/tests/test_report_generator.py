from __future__ import annotations

import asyncio

from dataverse_backend.app.services.report_generator import ReportGenerator


def test_report_generation_skips_zero_value_bar_charts():
    facts = {
        "filename": "zero_values.csv",
        "dataset_profile": {"row_count": 2, "column_count": 2},
        "business_metrics": {"transaction_count": 2},
        "data_quality": {"data_quality_score": 1.0},
        "key_insights": ["All chart values are currently zero."],
        "charts": [
            {
                "type": "bar",
                "title": "Zero values",
                "x_key": "label",
                "y_key": "value",
                "data": [
                    {"label": "A", "value": 0},
                    {"label": "B", "value": 0},
                ],
            }
        ],
    }

    generated = asyncio.run(ReportGenerator().generate(title="Zero Value Report", facts=facts))

    assert "Zero values" not in str(generated["html"])
    assert isinstance(generated["pdf"], bytes)
    assert len(generated["pdf"]) > 100
