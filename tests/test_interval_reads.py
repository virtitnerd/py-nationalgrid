"""Tests for get_interval_reads()."""

from datetime import datetime
from typing import Self
from unittest.mock import MagicMock

import aiohttp
import pytest

from py_nationalgrid.client import NationalGridClient
from py_nationalgrid.config import NationalGridConfig
from py_nationalgrid.exceptions import DataExtractionError
from py_nationalgrid.extractors import extract_interval_reads
from py_nationalgrid.graphql import GraphQLResponse
from py_nationalgrid.queries import ENERGY_USAGE_ENDPOINT


class _DummyResponse:
    def __init__(self, payload: dict[str, object]):
        self._payload = payload

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:  # type: ignore[override]
        return False

    async def json(self, content_type: str | None = None) -> dict[str, object]:
        return self._payload

    def raise_for_status(self) -> None:
        return None


@pytest.fixture
def mock_session() -> MagicMock:
    session = MagicMock(spec=aiohttp.ClientSession)
    session.closed = False
    return session


@pytest.fixture
def config() -> NationalGridConfig:
    return NationalGridConfig(endpoint="https://example.test/graphql")


@pytest.mark.asyncio
async def test_get_interval_reads_returns_typed_list(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Happy path: nrtEnergyUsages returns a list of interval read dicts.

    `date` is a full ISO 8601 timestamp equal to the interval's own `timeTo`,
    with the DST-aware offset baked in; `timeFrom`/`timeTo` are "HH:MM" —
    this mirrors the live API's actual response.
    """
    mock_session.post.return_value = _DummyResponse(
        {
            "data": {
                "nrtEnergyUsages": {
                    "nodes": [
                        {
                            "date": "2024-03-01T00:15:00.000-05:00",
                            "timeFrom": "00:00",
                            "timeTo": "00:15",
                            "quantity": 1.5,
                        },
                        {
                            "date": "2024-03-01T00:30:00.000-05:00",
                            "timeFrom": "00:15",
                            "timeTo": "00:30",
                            "quantity": 1.2,
                        },
                    ]
                }
            }
        }
    )

    client = NationalGridClient(config=config, session=mock_session)
    reads = await client.get_interval_reads(
        premise_number="12345",
        service_point_number="67890",
        start_datetime="2024-03-01 00:00:00",
    )

    assert len(reads) == 2
    assert reads[0]["startTime"] == "2024-03-01T00:00:00-05:00"
    assert reads[0]["endTime"] == "2024-03-01T00:15:00-05:00"
    assert reads[0]["value"] == 1.5
    assert reads[1]["startTime"] == "2024-03-01T00:15:00-05:00"
    assert reads[1]["endTime"] == "2024-03-01T00:30:00-05:00"
    assert reads[1]["value"] == 1.2


@pytest.mark.asyncio
async def test_get_interval_reads_returns_empty_on_no_nrt_data(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """nrtEnergyUsages returns {"nodes": []} for meters with no NRT data (e.g. GAS)."""
    mock_session.post.return_value = _DummyResponse({"data": {"nrtEnergyUsages": {"nodes": []}}})

    client = NationalGridClient(config=config, session=mock_session)
    reads = await client.get_interval_reads(
        premise_number="12345",
        service_point_number="67890",
        start_datetime="2024-03-01 00:00:00",
    )

    assert reads == []


@pytest.mark.asyncio
async def test_get_interval_reads_accepts_datetime_object(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """datetime objects are formatted as 'YYYY-MM-DD HH:MM:SS' strings."""
    mock_session.post.return_value = _DummyResponse({"data": {"nrtEnergyUsages": {"nodes": []}}})

    client = NationalGridClient(config=config, session=mock_session)
    await client.get_interval_reads(
        premise_number=12345,
        service_point_number=67890,
        start_datetime=datetime(2024, 3, 1, 6, 30, 0),
    )

    _, kwargs = mock_session.post.call_args
    payload = kwargs["json"]
    assert payload["variables"]["startDateTime"] == "2024-03-01 06:30:00"
    assert payload["variables"]["premiseNumber"] == "12345"
    assert payload["variables"]["servicePointNumber"] == "67890"


@pytest.mark.asyncio
async def test_get_interval_reads_uses_energy_usage_endpoint(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    mock_session.post.return_value = _DummyResponse({"data": {"nrtEnergyUsages": {"nodes": []}}})

    client = NationalGridClient(config=config, session=mock_session)
    await client.get_interval_reads(
        premise_number="12345",
        service_point_number="67890",
        start_datetime="2024-03-01 00:00:00",
    )

    args, _ = mock_session.post.call_args
    assert args[0] == ENERGY_USAGE_ENDPOINT


@pytest.mark.asyncio
async def test_get_interval_reads_returns_empty_on_graphql_errors(
    mock_session: MagicMock, config: NationalGridConfig, caplog: pytest.LogCaptureFixture
) -> None:
    """GraphQL-level errors (e.g. non-AMI meters) are swallowed to [] with a logged warning."""
    mock_session.post.return_value = _DummyResponse(
        {
            "data": None,
            "errors": [{"message": "Unauthorized", "extensions": {"code": "UNAUTHENTICATED"}}],
        }
    )

    client = NationalGridClient(config=config, session=mock_session)

    with caplog.at_level("WARNING"):
        reads = await client.get_interval_reads(
            premise_number="12345",
            service_point_number="67890",
            start_datetime="2024-03-01 00:00:00",
        )

    assert reads == []
    assert "Failed to extract interval reads from response" in caplog.text


@pytest.mark.asyncio
async def test_get_interval_reads_raises_data_extraction_error(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """DataExtractionError raised when the response is missing the expected field."""
    mock_session.post.return_value = _DummyResponse({"data": {}})

    client = NationalGridClient(config=config, session=mock_session)

    with pytest.raises(DataExtractionError, match="Missing 'nrtEnergyUsages' field"):
        await client.get_interval_reads(
            premise_number="12345",
            service_point_number="67890",
            start_datetime="2024-03-01 00:00:00",
        )


def test_extract_interval_reads_wraps_midnight_and_reuses_api_offset() -> None:
    """`date` is the interval's own end timestamp — its clock time equals

    `timeTo`, and its calendar date is already rolled forward when the
    interval crosses midnight (confirmed against a real API payload: a
    node with timeFrom="23:45"/timeTo="00:00" carries a `date` dated the
    *next* day). `startTime` is derived by placing `timeFrom` on that same
    date, rolling back a day if that lands after `date`."""
    response = GraphQLResponse(
        data={
            "nrtEnergyUsages": {
                "nodes": [
                    {
                        "date": "2024-03-02T00:00:00.000-05:00",
                        "timeFrom": "23:45",
                        "timeTo": "00:00",
                        "quantity": 0.8,
                    },
                    {
                        "date": "2024-07-01T12:15:00.000-04:00",
                        "timeFrom": "12:00",
                        "timeTo": "12:15",
                        "quantity": 2.1,
                    },
                ]
            }
        }
    )

    reads = extract_interval_reads(response)

    assert reads[0]["startTime"] == "2024-03-01T23:45:00-05:00"
    assert reads[0]["endTime"] == "2024-03-02T00:00:00-05:00"
    assert reads[1]["startTime"] == "2024-07-01T12:00:00-04:00"
    assert reads[1]["endTime"] == "2024-07-01T12:15:00-04:00"


def test_extract_interval_reads_matches_live_api_payload() -> None:
    """Regression test using a real nrtEnergyUsages payload excerpt (2026-08-22

    into 2026-08-23), including the midnight-crossing interval."""
    response = GraphQLResponse(
        data={
            "nrtEnergyUsages": {
                "nodes": [
                    {
                        "date": "2026-08-22T23:45:00.000-04:00",
                        "timeFrom": "23:30",
                        "timeTo": "23:45",
                        "quantity": 0.17305,
                    },
                    {
                        "date": "2026-08-23T00:00:00.000-04:00",
                        "timeFrom": "23:45",
                        "timeTo": "00:00",
                        "quantity": 0.185709,
                    },
                    {
                        "date": "2026-08-23T00:30:00.000-04:00",
                        "timeFrom": "00:15",
                        "timeTo": "00:30",
                        "quantity": 0.61209,
                    },
                ]
            }
        }
    )

    reads = extract_interval_reads(response)

    assert reads[0]["startTime"] == "2026-08-22T23:30:00-04:00"
    assert reads[0]["endTime"] == "2026-08-22T23:45:00-04:00"
    assert reads[1]["startTime"] == "2026-08-22T23:45:00-04:00"
    assert reads[1]["endTime"] == "2026-08-23T00:00:00-04:00"
    assert reads[2]["startTime"] == "2026-08-23T00:15:00-04:00"
    assert reads[2]["endTime"] == "2026-08-23T00:30:00-04:00"
