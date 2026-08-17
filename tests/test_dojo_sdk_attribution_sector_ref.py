from __future__ import annotations

from unittest.mock import Mock

import pandas as pd

from dojo.datasource.huggingface import HuggingFaceAttributionFactorDataSource
from dojo.types.models import AttributionFactorItem


def test_attribution_factor_item_exposes_online_sector_ref() -> None:
    item = AttributionFactorItem(sector_id=10, sector_ref="1/9/10")

    assert item.sector_id == 10
    assert item.sector_ref == "1/9/10"


def test_offline_attribution_factor_normalizes_legacy_sector_path() -> None:
    source = object.__new__(HuggingFaceAttributionFactorDataSource)
    source._df_cache = {}
    source.fetch_df = Mock(
        return_value=pd.DataFrame(
            [
                {"sector_id": 10, "sector_ref": "1/9/10"},
                {"sector_id": "1/18/19", "sector_ref": None},
                {"sector_id": 20, "sector_ref": None},
            ]
        )
    )

    frame = source._get_cached_attribution_factor_df("/api/qdata/v1/analysis/attribution_factor")

    assert frame["sector_ref"].tolist() == ["1/9/10", "1/18/19", None]
    assert frame["sector_id_list"].tolist() == [["1", "9", "10"], ["1", "18", "19"], []]
