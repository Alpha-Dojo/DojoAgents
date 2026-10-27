from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from dojo.datasource.huggingface import HuggingFaceAttributionFactorDataSource
from dojo.datasource.registry import resolve
from dojo.types.models import AttributionFactorItem
from dojo.types.snapshot import SnapshotFile, SnapshotRef


def test_attribution_factor_item_exposes_online_sector_ref() -> None:
    item = AttributionFactorItem(sector_id=10, sector_ref="1/9/10")

    assert item.sector_id == 10
    assert item.sector_ref == "1/9/10"


def test_offline_attribution_factor_normalizes_legacy_sector_path(tmp_path: Path) -> None:
    spec = resolve("/api/qdata/v1/analysis/attribution_factor")
    assert spec is not None
    parquet_path = tmp_path / spec.path_template
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.Table.from_pylist(
            [
                {"sector_id": "10", "sector_ref": "1/9/10"},
                {"sector_id": "1/18/19", "sector_ref": None},
                {"sector_id": "20", "sector_ref": None},
            ]
        ),
        parquet_path,
    )
    snapshot = SnapshotRef(
        backend="huggingface",
        repo_id=spec.repo_id,
        resolved_revision="test",
        snapshot_token="test-token",
        files=(
            SnapshotFile(
                relative_path=spec.path_template,
                local_path=parquet_path,
                size=parquet_path.stat().st_size,
            ),
        ),
    )
    source = object.__new__(HuggingFaceAttributionFactorDataSource)
    frame = source._build_attribution_canonical_lazy(snapshot, spec).collect().to_pandas()

    assert frame["sector_ref"].tolist() == ["1/9/10", "1/18/19", None]
    assert [list(value) for value in frame["sector_id_list"]] == [
        ["1", "9", "10"],
        ["1", "18", "19"],
        [],
    ]
