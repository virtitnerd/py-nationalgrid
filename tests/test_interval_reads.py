"""Tests for get_interval_reads() and REST query builder."""

from datetime import datetime
from typing import Self
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from py_nationalgrid.client import NationalGridClient
from py_nationalgrid.config import NationalGridConfig
from py_nationalgrid.exceptions import DataExtractionError, RestAPIError
from py_nationalgrid.rest import RestResponse
from py_nationalgrid.rest_queries import RealtimeMeterInfo, _validate_start_datetime

# ---------------------------------------------------------------------------
# REST query builder tests
# ---------------------------------------------------------------------------


class TestRealtimeMeterInfo:
    def test_to_request_builds_correct_path(self) -> None:
        info = RealtimeMeterInfo(
            premise_number="12345",
            service_point_number="67890",
            start_datetime="2024-03-01 00:00:00",
        )
        req = info.to_request()
        assert "12345" in req.path_or_url
        assert "67890" in req.path_or_url
        assert req.method == "GET"
        assert req.params is not None
        assert req.params["startDateTime"] == "2024-03-01 00:00:00"

    def test_to_request_merges_extra_params(self) -> None:
        info = RealtimeMeterInfo(
            premise_number="12345",
            service_point_number="67890",
            start_datetime="2024-03-01 00:00:00",
            params={"EndDateTime": "2024-03-02 00:00:00"},
        )
        req = info.to_request()
        assert req.params is not None
        assert req.params["EndDateTime"] == "2024-03-02 00:00:00"
        assert req.params["startDateTime"] == "2024-03-01 00:00:00"

    def test_to_request_raises_when_start_datetime_empty(self) -> None:
        info = RealtimeMeterInfo(
            premise_number="12345",
            service_point_number="67890",
            start_datetime="",
        )
        with pytest.raises(ValueError, match="start_datetime is required"):
            info.to_request()

    def test_validate_start_datetime_rejects_bad_format(self) -> None:
        with pytest.raises(ValueError, match="YYYY-MM-DD hh:mm:ss"):
            _validate_start_datetime("2024-03-01")

    def test_validate_start_datetime_rejects_empty(self) -> None:
        with pytest.raises(ValueError, match="startDateTime is required"):
            _validate_start_datetime("")

    def test_validate_start_datetime_accepts_correct_format(self) -> None:
        _validate_start_datetime("2024-03-01 00:00:00")  # should not raise


# ---------------------------------------------------------------------------
# get_interval_reads() tests
# ---------------------------------------------------------------------------


class _DummyRestResponse:
    def __init__(self, payload: object, *, status: int = 200) -> None:
        self._payload = payload
        self.status = status
        self.headers: dict[str, str] = {}

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:  # type: ignore[override]
        return False

    async def json(self, content_type: str | None = None) -> object:
        return self._payload

    async def text(self) -> str:
        return str(self._payload)

    def raise_for_status(self) -> None:
        pass


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
    """Happy path: REST endpoint returns a list of interval read dicts."""
    payload = [
        {"dateTime": "2024-03-01 00:00:00", "value": 1.5, "fuelType": "ELECTRIC"},
        {"dateTime": "2024-03-01 00:15:00", "value": 1.2, "fuelType": "ELECTRIC"},
    ]
    mock_session.request.return_value = _DummyRestResponse(payload)

    client = NationalGridClient(config=config, session=mock_session)
    reads = await client.get_interval_reads(
        premise_number="12345",
        service_point_number="67890",
        start_datetime="2024-03-01 00:00:00",
    )

    assert len(reads) == 2
    assert reads[0]["value"] == 1.5
    assert reads[1]["value"] == 1.2


@pytest.mark.asyncio
async def test_get_interval_reads_accepts_datetime_object(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """datetime objects are formatted as 'YYYY-MM-DD HH:MM:SS' strings."""
    mock_session.request.return_value = _DummyRestResponse([])

    client = NationalGridClient(config=config, session=mock_session)
    await client.get_interval_reads(
        premise_number=12345,
        service_point_number=67890,
        start_datetime=datetime(2024, 3, 1, 6, 30, 0),
    )

    _, kwargs = mock_session.request.call_args
    assert kwargs["params"]["startDateTime"] == "2024-03-01 06:30:00"


@pytest.mark.asyncio
async def test_get_interval_reads_returns_empty_on_404(
    mock_session: MagicMock, config: NationalGridConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """404 from the NRT endpoint (GAS meter) returns empty list, no exception."""
    err = RestAPIError("Not Found", url="https://x", method="GET", status=404)
    client = NationalGridClient(config=config, session=mock_session)
    monkeypatch.setattr(client, "request_rest", AsyncMock(side_effect=err))

    reads = await client.get_interval_reads(
        premise_number="12345",
        service_point_number="67890",
        start_datetime="2024-03-01 00:00:00",
    )
    assert reads == []


@pytest.mark.asyncio
async def test_get_interval_reads_propagates_non_404_rest_errors(
    mock_session: MagicMock, config: NationalGridConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-404 RestAPIError propagates."""
    err = RestAPIError("Service Unavailable", url="https://x", method="GET", status=503)
    client = NationalGridClient(config=config, session=mock_session)
    monkeypatch.setattr(client, "request_rest", AsyncMock(side_effect=err))

    with pytest.raises(RestAPIError):
        await client.get_interval_reads(
            premise_number="12345",
            service_point_number="67890",
            start_datetime="2024-03-01 00:00:00",
        )


@pytest.mark.asyncio
async def test_get_interval_reads_raises_when_response_not_list(
    mock_session: MagicMock, config: NationalGridConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DataExtractionError raised when the REST payload is not a list."""
    rest_response = RestResponse(status=200, headers={}, data={"unexpected": "dict"})
    client = NationalGridClient(config=config, session=mock_session)
    monkeypatch.setattr(client, "request_rest", AsyncMock(return_value=rest_response))

    with pytest.raises(DataExtractionError, match="Expected list"):
        await client.get_interval_reads(
            premise_number="12345",
            service_point_number="67890",
            start_datetime="2024-03-01 00:00:00",
        )
