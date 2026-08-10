from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from dojo.resources.analysis import Analysis, AsyncAnalysis
from dojo.types.models import (
    SectorBriefExtractListResponse,
    SectorBriefExtractWriteResponse,
)

BODY = {
    "items": [
        {
            "brief_uid": "brief-1",
            "market": "cn",
            "sector_id": "1/9/10",
            "as_of_date": "2026-07-31",
            "key_drivers": [
                {
                    "title": {"zh": "算力需求增长", "en": "Compute demand expands"},
                    "importance": "high",
                    "price_direction": "up",
                }
            ],
            "key_risks": [],
            "top_components": [
                {
                    "ticker": "002916.SZ",
                    "role_label": {"zh": "算力龙头", "en": "AI leader"},
                    "thesis": {"zh": "受益服务器需求", "en": "Benefits from server demand"},
                }
            ],
        }
    ]
}


def test_sector_brief_extract_sync_list_and_create() -> None:
    client = Mock()
    listed = SectorBriefExtractListResponse(total_num=0, data=[])
    created = SectorBriefExtractWriteResponse(data=[])
    client.get.return_value = listed
    client.post.return_value = created
    resource = Analysis(client)

    assert resource.get_sector_brief_extract.__func__ is resource.list_sector_brief_extract.__func__

    assert (
        resource.list_sector_brief_extract(
            market="cn",
            sector_id="1/9/10",
            as_of_date="2026-07-31",
            limit=20,
        )
        is listed
    )
    client.get.assert_called_once_with(
        "/api/qdata/v1/analysis/sector_brief_extract",
        cast_to=SectorBriefExtractListResponse,
        options={
            "params": {
                "market": "cn",
                "sector_id": "1/9/10",
                "as_of_date": "2026-07-31",
                "limit": 20,
            }
        },
    )

    assert resource.create_sector_brief_extract(body=BODY) is created
    client.post.assert_called_once_with(
        "/api/qdata/v1/analysis/sector_brief_extract",
        cast_to=SectorBriefExtractWriteResponse,
        options={"json": BODY},
    )


def test_sector_brief_extract_rejects_invalid_payload_before_request() -> None:
    client = Mock()
    invalid = {**BODY["items"][0], "as_of_date": "2026-07-31T10:00:00"}

    with pytest.raises(ValidationError):
        Analysis(client).create_sector_brief_extract(body={"items": [invalid]})

    client.post.assert_not_called()


@pytest.mark.asyncio
async def test_sector_brief_extract_async_list_and_create() -> None:
    client = Mock()
    listed = SectorBriefExtractListResponse(total_num=0, data=[])
    created = SectorBriefExtractWriteResponse(data=[])
    client.get = AsyncMock(return_value=listed)
    client.post = AsyncMock(return_value=created)
    resource = AsyncAnalysis(client)

    assert resource.get_sector_brief_extract.__func__ is resource.list_sector_brief_extract.__func__

    assert await resource.list_sector_brief_extract(start_date="2026-07-01", end_date="2026-07-31") is listed
    client.get.assert_awaited_once_with(
        "/api/qdata/v1/analysis/sector_brief_extract",
        cast_to=SectorBriefExtractListResponse,
        options={"params": {"start_date": "2026-07-01", "end_date": "2026-07-31"}},
    )

    assert await resource.create_sector_brief_extract(body=BODY) is created
    client.post.assert_awaited_once_with(
        "/api/qdata/v1/analysis/sector_brief_extract",
        cast_to=SectorBriefExtractWriteResponse,
        options={"json": BODY},
    )
