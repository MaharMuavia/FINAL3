"""Sales/e-commerce analytics facade."""
from __future__ import annotations

import pandas as pd

from .analytics_tools import AnalyticsTools


class SalesTools(AnalyticsTools):
    """Keeps sales-specific methods separate from generic analytics routing."""

    def __init__(self, df: pd.DataFrame):
        super().__init__(df)
