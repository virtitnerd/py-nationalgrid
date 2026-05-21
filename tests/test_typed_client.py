"""Tests for typed convenience methods on NationalGridClient."""

from datetime import date
from typing import Self
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from py_nationalgrid.client import NationalGridClient
from py_nationalgrid.config import NationalGridConfig
from py_nationalgrid.exceptions import DataExtractionError, GraphQLError, RetryExhaustedError
from py_nationalgrid.graphql import GraphQLResponse
from py_nationalgrid.queries import (
    BALANCED_BILLING_ENDPOINT,
    BILL_ENDPOINT,
    COLLECTION_ARRANGEMENTS_ENDPOINT,
    ENERGY_USAGE_ENDPOINT,
    LINKED_BILLING_ENDPOINT,
    METER_READING_ENDPOINT,
    PAPERLESS_BILLING_ENDPOINT,
    PAYMENT_PLANS_ENDPOINT,
    PREMISE_ENDPOINT,
)


class _DummyResponse:
    """Mock response for GraphQL requests."""

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
    """Create a mock aiohttp session."""
    session = MagicMock(spec=aiohttp.ClientSession)
    session.closed = False
    return session


@pytest.fixture
def config() -> NationalGridConfig:
    """Create a test configuration."""
    return NationalGridConfig(endpoint="https://example.test/graphql")


@pytest.mark.asyncio
async def test_get_linked_accounts_returns_typed_list(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Verify get_linked_accounts returns a properly typed list."""
    mock_session.post.return_value = _DummyResponse(
        {
            "data": {
                "user": {
                    "accountLinks": {
                        "totalCount": 2,
                        "nodes": [
                            {
                                "accountLinkId": "link-1",
                                "billingAccountId": "acct-001",
                                "billingAccount": {"nextSchedReadingDate": "2026-06-15"},
                            },
                            {
                                "accountLinkId": "link-2",
                                "billingAccountId": "acct-002",
                                "billingAccount": {"nextSchedReadingDate": None},
                            },
                        ],
                    }
                }
            }
        }
    )

    client = NationalGridClient(config=config, session=mock_session)
    accounts = await client.get_linked_accounts()

    assert len(accounts) == 2
    assert accounts[0]["accountLinkId"] == "link-1"
    assert accounts[0]["billingAccountId"] == "acct-001"
    assert accounts[0]["billingAccount"]["nextSchedReadingDate"] == "2026-06-15"
    assert accounts[1]["billingAccountId"] == "acct-002"
    assert accounts[1]["billingAccount"]["nextSchedReadingDate"] is None


@pytest.mark.asyncio
async def test_get_billing_account_returns_typed_dict(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Verify get_billing_account returns a properly typed dict."""
    mock_session.post.return_value = _DummyResponse(
        {
            "data": {
                "billingAccount": {
                    "region": "Massachusetts",
                    "regionAbbreviation": "MA",
                    "type": "RESIDENTIAL",
                    "fuelTypes": [{"type": "ELECTRIC"}],
                    "status": "ACTIVE",
                    "serviceAddress": {"serviceAddressCompressed": "123 Main St"},
                    "customerInfo": {"customerType": "RESIDENTIAL"},
                    "customerNumber": "CUST-001",
                    "premiseNumber": "PREM-001",
                    "meter": {
                        "nodes": [
                            {
                                "isSmartMeter": True,
                                "hasAmiSmartMeter": True,
                                "deviceCode": "AMI",
                                "fuelType": "ELECTRIC",
                                "meterPointTypeCode": "E",
                                "meterPointNumber": "MP-001",
                                "servicePointNumber": "SP-001",
                                "meterNumber": "M-001",
                            }
                        ]
                    },
                }
            }
        }
    )

    client = NationalGridClient(config=config, session=mock_session)
    account = await client.get_billing_account("acct-001")

    assert account["region"] == "Massachusetts"
    assert account["regionAbbreviation"] == "MA"
    assert account["status"] == "ACTIVE"
    assert account["premiseNumber"] == "PREM-001"
    assert account["meter"]["nodes"][0]["isSmartMeter"] is True


@pytest.mark.asyncio
async def test_get_billing_account_passes_account_number(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Verify get_billing_account passes the account number as a variable."""
    mock_session.post.return_value = _DummyResponse(
        {
            "data": {
                "billingAccount": {
                    "region": "MA",
                    "regionAbbreviation": "MA",
                    "type": "RESIDENTIAL",
                    "fuelTypes": [],
                    "status": "ACTIVE",
                    "serviceAddress": {"serviceAddressCompressed": "123 Main"},
                    "customerInfo": {"customerType": "RES"},
                    "customerNumber": "C001",
                    "premiseNumber": "P001",
                    "meter": {"nodes": []},
                }
            }
        }
    )

    client = NationalGridClient(config=config, session=mock_session)
    await client.get_billing_account("my-account-123")

    _, kwargs = mock_session.post.call_args
    payload = kwargs["json"]
    assert payload["variables"]["accountNumber"] == "my-account-123"


@pytest.mark.asyncio
async def test_get_energy_usage_costs_accepts_date_object(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Verify get_energy_usage_costs accepts a date object."""
    mock_session.post.return_value = _DummyResponse(
        {
            "data": {
                "energyUsageCosts": {
                    "nodes": [
                        {
                            "date": "2024-01-15",
                            "fuelType": "ELECTRIC",
                            "amount": 125.50,
                            "month": "January",
                        }
                    ]
                }
            }
        }
    )

    client = NationalGridClient(config=config, session=mock_session)
    costs = await client.get_energy_usage_costs(
        "acct-001",
        date(2024, 1, 15),
        "NECO",
    )

    assert len(costs) == 1
    assert costs[0]["amount"] == 125.50

    # Verify date was converted to ISO string
    _, kwargs = mock_session.post.call_args
    payload = kwargs["json"]
    assert payload["variables"]["date"] == "2024-01-15"


@pytest.mark.asyncio
async def test_get_energy_usage_costs_accepts_string_date(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Verify get_energy_usage_costs accepts a string date."""
    mock_session.post.return_value = _DummyResponse(
        {
            "data": {
                "energyUsageCosts": {
                    "nodes": [
                        {
                            "date": "2024-02-20",
                            "fuelType": "ELECTRIC",
                            "amount": 98.75,
                            "month": "February",
                        }
                    ]
                }
            }
        }
    )

    client = NationalGridClient(config=config, session=mock_session)
    costs = await client.get_energy_usage_costs(
        "acct-001",
        "2024-02-20",
        "KEDNE",
    )

    assert len(costs) == 1
    _, kwargs = mock_session.post.call_args
    payload = kwargs["json"]
    assert payload["variables"]["date"] == "2024-02-20"
    assert payload["variables"]["companyCode"] == "KEDNE"


@pytest.mark.asyncio
async def test_get_energy_usages_returns_typed_list(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Verify get_energy_usages returns a properly typed list."""
    mock_session.post.return_value = _DummyResponse(
        {
            "data": {
                "energyUsages": {
                    "nodes": [
                        {"usage": 450.5, "usageType": "ACTUAL", "usageYearMonth": 202401},
                        {"usage": 380.2, "usageType": "ACTUAL", "usageYearMonth": 202402},
                    ]
                }
            }
        }
    )

    client = NationalGridClient(config=config, session=mock_session)
    usages = await client.get_energy_usages("acct-001", 202401)

    assert len(usages) == 2
    assert usages[0]["usage"] == 450.5
    assert usages[0]["usageYearMonth"] == 202401


@pytest.mark.asyncio
async def test_get_energy_usages_passes_variables(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Verify get_energy_usages passes the correct variables."""
    mock_session.post.return_value = _DummyResponse({"data": {"energyUsages": {"nodes": []}}})

    client = NationalGridClient(config=config, session=mock_session)
    await client.get_energy_usages("acct-001", 202301, first=24)

    _, kwargs = mock_session.post.call_args
    payload = kwargs["json"]
    assert payload["variables"]["accountNumber"] == "acct-001"
    assert payload["variables"]["from"] == 202301
    assert payload["variables"]["first"] == 24


@pytest.mark.asyncio
async def test_typed_method_raises_on_graphql_errors(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Verify typed methods raise ValueError on GraphQL errors."""
    mock_session.post.return_value = _DummyResponse(
        {
            "data": None,
            "errors": [{"message": "Unauthorized", "extensions": {"code": "UNAUTHENTICATED"}}],
        }
    )

    client = NationalGridClient(config=config, session=mock_session)

    with pytest.raises(ValueError, match="GraphQL errors encountered"):
        await client.get_linked_accounts()


@pytest.mark.asyncio
async def test_typed_method_raises_data_extraction_error(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Verify typed methods raise DataExtractionError on missing data."""
    mock_session.post.return_value = _DummyResponse(
        {"data": {"user": {}}}  # Missing accountLinks
    )

    client = NationalGridClient(config=config, session=mock_session)

    with pytest.raises(DataExtractionError, match="Missing 'accountLinks' field"):
        await client.get_linked_accounts()


@pytest.mark.asyncio
async def test_get_linked_accounts_returns_empty_list(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Verify get_linked_accounts handles empty account list."""
    mock_session.post.return_value = _DummyResponse(
        {
            "data": {
                "user": {
                    "accountLinks": {
                        "totalCount": 0,
                        "nodes": [],
                    }
                }
            }
        }
    )

    client = NationalGridClient(config=config, session=mock_session)
    accounts = await client.get_linked_accounts()

    assert accounts == []


@pytest.mark.asyncio
async def test_get_ami_energy_usages_15min_returns_typed_list(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Verify get_ami_energy_usages_15min returns a properly typed list."""
    mock_session.post.return_value = _DummyResponse(
        {
            "data": {
                "amiEnergyUsages15Min": {
                    "nodes": [
                        {"date": "2024-03-01", "fuelType": "ELECTRIC", "quantity": 1.25},
                        {"date": "2024-03-01", "fuelType": "ELECTRIC", "quantity": 1.50},
                    ]
                }
            }
        }
    )

    client = NationalGridClient(config=config, session=mock_session)
    usages = await client.get_ami_energy_usages_15min(
        meter_number="M-001",
        premise_number="PREM-001",
        service_point_number="SP-001",
        meter_point_number="MP-001",
        date_from="2024-03-01",
        date_to="2024-03-01",
    )

    assert len(usages) == 2
    assert usages[0]["fuelType"] == "ELECTRIC"
    assert usages[0]["quantity"] == 1.25
    assert usages[1]["quantity"] == 1.50


@pytest.mark.asyncio
async def test_get_ami_energy_usages_15min_passes_variables(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Verify get_ami_energy_usages_15min passes correct variables and uses 15min operation."""
    mock_session.post.return_value = _DummyResponse(
        {"data": {"amiEnergyUsages15Min": {"nodes": []}}}
    )

    client = NationalGridClient(config=config, session=mock_session)
    await client.get_ami_energy_usages_15min(
        meter_number="M-123",
        premise_number=456,
        service_point_number=789,
        meter_point_number=101,
        date_from=date(2024, 3, 1),
        date_to=date(2024, 3, 7),
    )

    args, kwargs = mock_session.post.call_args
    assert args[0] == ENERGY_USAGE_ENDPOINT
    payload = kwargs["json"]
    assert payload["variables"]["meterNumber"] == "M-123"
    assert payload["variables"]["premiseNumber"] == "456"
    assert payload["variables"]["servicePointNumber"] == "789"
    assert payload["variables"]["meterPointNumber"] == "101"
    assert payload["variables"]["dateFrom"] == "2024-03-01"
    assert payload["variables"]["dateTo"] == "2024-03-07"
    assert payload["operationName"] == "NrtDailyUsage15Min"


@pytest.mark.asyncio
async def test_get_ami_energy_usages_15min_falls_back_on_graphql_errors(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Verify get_ami_energy_usages_15min falls back to amiEnergyUsages on GraphQL errors."""
    mock_session.post.side_effect = [
        _DummyResponse(
            {
                "errors": [
                    {
                        "message": "Unable to cast object of type 'System.DateTime'",
                        "path": "amiEnergyUsages15Min",
                        "extensions": {"code": "BadRequest"},
                    }
                ],
                "data": {"amiEnergyUsages15Min": None},
            }
        ),
        _DummyResponse(
            {
                "data": {
                    "amiEnergyUsages": {
                        "nodes": [{"date": "2024-03-01", "fuelType": "GAS", "quantity": 3.0}]
                    }
                }
            }
        ),
    ]

    client = NationalGridClient(config=config, session=mock_session)
    usages = await client.get_ami_energy_usages_15min(
        meter_number="M-001",
        premise_number="PREM-001",
        service_point_number="SP-001",
        meter_point_number="MP-001",
        date_from="2024-03-01",
        date_to="2024-03-01",
    )

    assert mock_session.post.call_count == 2
    first_payload = mock_session.post.call_args_list[0][1]["json"]
    assert first_payload["operationName"] == "NrtDailyUsage15Min"
    fallback_payload = mock_session.post.call_args_list[1][1]["json"]
    assert fallback_payload["operationName"] == "NrtDailyUsage"
    assert len(usages) == 1
    assert usages[0]["quantity"] == 3.0
    assert usages[0]["fuelType"] == "GAS"


@pytest.mark.asyncio
async def test_get_ami_energy_usages_15min_raises_data_extraction_error(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Verify get_ami_energy_usages_15min raises DataExtractionError when field is missing."""
    mock_session.post.return_value = _DummyResponse({"data": {}})

    client = NationalGridClient(config=config, session=mock_session)

    with pytest.raises(DataExtractionError, match="Missing 'amiEnergyUsages15Min' field"):
        await client.get_ami_energy_usages_15min(
            meter_number="M-001",
            premise_number="PREM-001",
            service_point_number="SP-001",
            meter_point_number="MP-001",
            date_from="2024-03-01",
            date_to="2024-03-07",
        )


# ---------------------------------------------------------------------------
# Chunking tests
# ---------------------------------------------------------------------------


def _ami_15min_payload(records: list[dict[str, object]]) -> dict[str, object]:
    """Build a minimal amiEnergyUsages15Min response payload."""
    return {"data": {"amiEnergyUsages15Min": {"nodes": records}}}


def _ami_daily_payload(records: list[dict[str, object]]) -> dict[str, object]:
    """Build a minimal amiEnergyUsages (daily) response payload."""
    return {"data": {"amiEnergyUsages": {"nodes": records}}}


@pytest.mark.asyncio
async def test_no_chunking_when_range_fits_in_one_window(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Range within chunk limit → single request, no split."""
    mock_session.post.return_value = _DummyResponse(
        _ami_15min_payload([{"date": "2024-03-01", "fuelType": "ELECTRIC", "quantity": 1.0}])
    )

    client = NationalGridClient(config=config, session=mock_session)
    # 7-day range is well inside the 90-day ELECTRIC window.
    usages = await client.get_ami_energy_usages_15min(
        meter_number="M-001",
        premise_number="PREM-001",
        service_point_number="SP-001",
        meter_point_number="MP-001",
        date_from=date(2024, 3, 1),
        date_to=date(2024, 3, 7),
        fuel_type="ELECTRIC",
    )

    assert mock_session.post.call_count == 1
    assert len(usages) == 1


@pytest.mark.asyncio
async def test_electric_chunking_splits_into_correct_windows(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """ELECTRIC 180-day range → three 60-day chunks with correct date boundaries."""
    # 2024-01-01 to 2024-06-28 = 180 days → 3 chunks (60 + 60 + 60)
    # Chunks built oldest-first then reversed for newest-first iteration:
    # (Apr 30–Jun 28), (Mar 1–Apr 29), (Jan 1–Feb 29)
    mock_session.post.side_effect = [
        _DummyResponse(
            _ami_15min_payload([{"date": "2024-06-01", "fuelType": "ELECTRIC", "quantity": 3.0}])
        ),
        _DummyResponse(
            _ami_15min_payload([{"date": "2024-04-01", "fuelType": "ELECTRIC", "quantity": 2.0}])
        ),
        _DummyResponse(
            _ami_15min_payload([{"date": "2024-01-15", "fuelType": "ELECTRIC", "quantity": 1.0}])
        ),
    ]

    client = NationalGridClient(config=config, session=mock_session)
    usages = await client.get_ami_energy_usages_15min(
        meter_number="M-001",
        premise_number="PREM-001",
        service_point_number="SP-001",
        meter_point_number="MP-001",
        date_from=date(2024, 1, 1),
        date_to=date(2024, 6, 28),
        fuel_type="ELECTRIC",
    )

    assert mock_session.post.call_count == 3
    assert len(usages) == 3
    assert usages[0]["quantity"] == 1.0
    assert usages[1]["quantity"] == 2.0
    assert usages[2]["quantity"] == 3.0

    # Verify chunk boundaries — newest chunk is requested first
    chunk1_vars = mock_session.post.call_args_list[0][1]["json"]["variables"]
    assert chunk1_vars["dateFrom"] == "2024-04-30"
    assert chunk1_vars["dateTo"] == "2024-06-28"

    chunk2_vars = mock_session.post.call_args_list[1][1]["json"]["variables"]
    assert chunk2_vars["dateFrom"] == "2024-03-01"
    assert chunk2_vars["dateTo"] == "2024-04-29"

    chunk3_vars = mock_session.post.call_args_list[2][1]["json"]["variables"]
    assert chunk3_vars["dateFrom"] == "2024-01-01"
    assert chunk3_vars["dateTo"] == "2024-02-29"


@pytest.mark.asyncio
async def test_gas_chunking_uses_60_day_windows(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """GAS uses the same 60-day chunk window as ELECTRIC."""
    # 2024-01-01 to 2024-03-10 = 70 days → 2 chunks (60 + 10)
    # Chunks newest-first: (Mar 1–Mar 10), (Jan 1–Feb 29)
    mock_session.post.side_effect = [
        _DummyResponse(
            _ami_15min_payload([{"date": "2024-03-05", "fuelType": "GAS", "quantity": 2.0}])
        ),
        _DummyResponse(
            _ami_15min_payload([{"date": "2024-01-10", "fuelType": "GAS", "quantity": 1.0}])
        ),
    ]

    client = NationalGridClient(config=config, session=mock_session)
    usages = await client.get_ami_energy_usages_15min(
        meter_number="M-001",
        premise_number="PREM-001",
        service_point_number="SP-001",
        meter_point_number="MP-001",
        date_from=date(2024, 1, 1),
        date_to=date(2024, 3, 10),
        fuel_type="GAS",
    )

    assert mock_session.post.call_count == 2
    assert len(usages) == 2

    # Newest chunk is requested first
    chunk1_vars = mock_session.post.call_args_list[0][1]["json"]["variables"]
    assert chunk1_vars["dateFrom"] == "2024-03-01"
    assert chunk1_vars["dateTo"] == "2024-03-10"

    chunk2_vars = mock_session.post.call_args_list[1][1]["json"]["variables"]
    assert chunk2_vars["dateFrom"] == "2024-01-01"
    assert chunk2_vars["dateTo"] == "2024-02-29"


@pytest.mark.asyncio
async def test_unknown_fuel_type_uses_60_day_window(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """fuel_type=None defaults to 60-day chunks."""
    # 80-day range → 2 chunks (60 + 20); would be 1 chunk with a >80-day window
    mock_session.post.side_effect = [
        _DummyResponse(
            _ami_15min_payload([{"date": "2024-03-05", "fuelType": "ELECTRIC", "quantity": 2.0}])
        ),
        _DummyResponse(
            _ami_15min_payload([{"date": "2024-01-15", "fuelType": "ELECTRIC", "quantity": 1.0}])
        ),
    ]

    client = NationalGridClient(config=config, session=mock_session)
    usages = await client.get_ami_energy_usages_15min(
        meter_number="M-001",
        premise_number="PREM-001",
        service_point_number="SP-001",
        meter_point_number="MP-001",
        date_from=date(2024, 1, 1),
        date_to=date(2024, 3, 20),  # 80 days
        fuel_type=None,
    )

    assert mock_session.post.call_count == 2
    assert len(usages) == 2


@pytest.mark.asyncio
async def test_fallback_on_first_chunk_uses_full_date_range(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """When the first chunk returns GraphQL errors, fall back to a single daily request
    covering the full original date range — no further 15min chunks attempted."""
    full_from = date(2024, 1, 1)
    full_to = date(2024, 6, 28)  # 180-day range → would chunk if 15min worked

    mock_session.post.side_effect = [
        # First chunk: 15min returns errors
        _DummyResponse(
            {
                "errors": [{"message": "Cast error", "extensions": {"code": "BadRequest"}}],
                "data": {"amiEnergyUsages15Min": None},
            }
        ),
        # Fallback: daily endpoint returns full range in one shot
        _DummyResponse(
            _ami_daily_payload(
                [
                    {"date": "2024-01-15", "fuelType": "GAS", "quantity": 5.0},
                    {"date": "2024-03-01", "fuelType": "GAS", "quantity": 6.0},
                ]
            )
        ),
    ]

    client = NationalGridClient(config=config, session=mock_session)
    usages = await client.get_ami_energy_usages_15min(
        meter_number="M-001",
        premise_number="PREM-001",
        service_point_number="SP-001",
        meter_point_number="MP-001",
        date_from=full_from,
        date_to=full_to,
        fuel_type="ELECTRIC",
    )

    # Only 2 calls total: first 15min chunk + one full-range daily fallback.
    assert mock_session.post.call_count == 2

    # Fallback request must span the full original date range.
    fallback_vars = mock_session.post.call_args_list[1][1]["json"]["variables"]
    assert fallback_vars["dateFrom"] == full_from.isoformat()
    assert fallback_vars["dateTo"] == full_to.isoformat()
    assert mock_session.post.call_args_list[1][1]["json"]["operationName"] == "NrtDailyUsage"

    assert len(usages) == 2
    assert usages[0]["quantity"] == 5.0
    assert usages[1]["quantity"] == 6.0


# ---------------------------------------------------------------------------
# 504 graceful truncation tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_504_on_first_chunk_returns_empty_list(
    mock_session: MagicMock, config: NationalGridConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the very first chunk 504s, return an empty list rather than raising."""
    err = RetryExhaustedError(
        "Exhausted",
        attempts=3,
        last_error=GraphQLError("504", endpoint="x", status=504),
    )
    client = NationalGridClient(config=config, session=mock_session)
    monkeypatch.setattr(client, "execute", AsyncMock(side_effect=err))

    usages = await client.get_ami_energy_usages_15min(
        meter_number="M-001",
        premise_number="PREM-001",
        service_point_number="SP-001",
        meter_point_number="MP-001",
        date_from=date(2024, 1, 1),
        date_to=date(2024, 1, 5),
        fuel_type="ELECTRIC",
    )
    assert usages == []


@pytest.mark.asyncio
async def test_504_on_later_chunk_returns_partial_results(
    mock_session: MagicMock, config: NationalGridConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When a later chunk 504s, return the records collected from earlier chunks."""
    good = GraphQLResponse(
        data={
            "amiEnergyUsages15Min": {
                "nodes": [{"date": "2024-01-15", "fuelType": "GAS", "quantity": 1.0}]
            }
        }
    )
    err = RetryExhaustedError(
        "Exhausted",
        attempts=3,
        last_error=GraphQLError("504", endpoint="x", status=504),
    )
    client = NationalGridClient(config=config, session=mock_session)
    # 80-day range → 2 chunks: newest (20 days) ok, oldest (60 days) 504s.
    # The 60-day chunk triggers sub-chunk retry; the first sub-chunk also 504s → stop.
    monkeypatch.setattr(client, "execute", AsyncMock(side_effect=[good, err, err]))

    usages = await client.get_ami_energy_usages_15min(
        meter_number="M-001",
        premise_number="PREM-001",
        service_point_number="SP-001",
        meter_point_number="MP-001",
        date_from=date(2024, 1, 1),
        date_to=date(2024, 3, 20),  # 80 days → 60-day oldest chunk + 20-day newest
        fuel_type="GAS",
    )
    assert len(usages) == 1
    assert usages[0]["quantity"] == 1.0


@pytest.mark.asyncio
async def test_15min_mid_run_fallback_switches_to_daily(
    mock_session: MagicMock, config: NationalGridConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When a mid-run (i>0) chunk returns errors, remaining chunks use daily endpoint."""
    # 3-chunk range (180 days at 60-day windows). Chunks fetched newest-first.
    # Chunk 0 (newest): 15min succeeds
    # Chunk 1 (middle): 15min returns errors → switch to daily for remainder
    # Chunk 2 (oldest): daily succeeds
    chunk0_ok = GraphQLResponse(
        data={
            "amiEnergyUsages15Min": {
                "nodes": [{"date": "2024-04-15", "fuelType": "ELECTRIC", "quantity": 3.0}]
            }
        }
    )
    chunk1_errors = GraphQLResponse(
        data={"amiEnergyUsages15Min": None},
        errors=[{"message": "mid-run error", "extensions": {"code": "InternalError"}}],
    )
    # After fell_back=True, execute is called with daily endpoint
    chunk1_daily_ok = GraphQLResponse(
        data={
            "amiEnergyUsages": {
                "nodes": [{"date": "2024-03-01", "fuelType": "ELECTRIC", "quantity": 2.0}]
            }
        }
    )
    chunk2_daily_ok = GraphQLResponse(
        data={
            "amiEnergyUsages": {
                "nodes": [{"date": "2024-01-15", "fuelType": "ELECTRIC", "quantity": 1.0}]
            }
        }
    )

    client = NationalGridClient(config=config, session=mock_session)
    monkeypatch.setattr(
        client,
        "execute",
        AsyncMock(side_effect=[chunk0_ok, chunk1_errors, chunk1_daily_ok, chunk2_daily_ok]),
    )

    usages = await client.get_ami_energy_usages_15min(
        meter_number="M-001",
        premise_number="PREM-001",
        service_point_number="SP-001",
        meter_point_number="MP-001",
        date_from=date(2024, 1, 1),
        date_to=date(2024, 6, 28),  # 180 days → 3 × 60-day chunks
        fuel_type="ELECTRIC",
    )

    # 4 execute calls: 15min(ok), 15min(err), daily(ok), daily(ok)
    assert client.execute.call_count == 4  # type: ignore[attr-defined]
    # Results in chronological order
    assert len(usages) == 3
    assert usages[0]["quantity"] == 1.0
    assert usages[1]["quantity"] == 2.0
    assert usages[2]["quantity"] == 3.0


@pytest.mark.asyncio
async def test_504_on_large_chunk_retries_as_subchunks(
    mock_session: MagicMock, config: NationalGridConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When a 60-day chunk 504s, the method retries it split into 45-day sub-chunks."""
    err = RetryExhaustedError(
        "Exhausted",
        attempts=3,
        last_error=GraphQLError("504", endpoint="x", status=504),
    )
    # 80-day range → 2 main chunks: newest (20 days) ok, oldest (60 days) 504s.
    # Sub-chunks of the 60-day chunk: newer (15 days Jan 1-Feb 14 reversed → Feb 15-Feb 29)
    # and older (45 days Jan 1-Feb 14) — both succeed.
    newest_ok = GraphQLResponse(
        data={
            "amiEnergyUsages15Min": {
                "nodes": [{"date": "2024-03-10", "fuelType": "ELECTRIC", "quantity": 3.0}]
            }
        }
    )
    sub1_ok = GraphQLResponse(
        data={
            "amiEnergyUsages15Min": {
                "nodes": [{"date": "2024-02-20", "fuelType": "ELECTRIC", "quantity": 2.0}]
            }
        }
    )
    sub2_ok = GraphQLResponse(
        data={
            "amiEnergyUsages15Min": {
                "nodes": [{"date": "2024-01-10", "fuelType": "ELECTRIC", "quantity": 1.0}]
            }
        }
    )

    client = NationalGridClient(config=config, session=mock_session)
    monkeypatch.setattr(
        client, "execute", AsyncMock(side_effect=[newest_ok, err, sub1_ok, sub2_ok])
    )

    usages = await client.get_ami_energy_usages_15min(
        meter_number="M-001",
        premise_number="PREM-001",
        service_point_number="SP-001",
        meter_point_number="MP-001",
        date_from=date(2024, 1, 1),
        date_to=date(2024, 3, 20),  # 80 days → 60-day oldest chunk + 20-day newest
        fuel_type="ELECTRIC",
    )

    # 4 execute calls: newest(ok), oldest_60day(504), sub-chunk1(ok), sub-chunk2(ok)
    assert client.execute.call_count == 4  # type: ignore[attr-defined]
    assert len(usages) == 3
    assert usages[0]["quantity"] == 1.0
    assert usages[1]["quantity"] == 2.0
    assert usages[2]["quantity"] == 3.0


@pytest.mark.asyncio
async def test_15min_first_chunk_error_then_daily_fallback_504(
    mock_session: MagicMock, config: NationalGridConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """First chunk errors on 15min; the full-range daily fallback also 504s → empty list."""
    first_chunk_errors = GraphQLResponse(
        data={"amiEnergyUsages15Min": None},
        errors=[{"message": "cast error", "extensions": {"code": "BadRequest"}}],
    )
    daily_504 = RetryExhaustedError(
        "Exhausted",
        attempts=3,
        last_error=GraphQLError("504", endpoint="x", status=504),
    )

    client = NationalGridClient(config=config, session=mock_session)
    monkeypatch.setattr(client, "execute", AsyncMock(side_effect=[first_chunk_errors, daily_504]))

    usages = await client.get_ami_energy_usages_15min(
        meter_number="M-001",
        premise_number="PREM-001",
        service_point_number="SP-001",
        meter_point_number="MP-001",
        date_from=date(2024, 1, 1),
        date_to=date(2024, 1, 31),
    )
    assert usages == []


@pytest.mark.asyncio
async def test_15min_non_504_exception_propagates(
    mock_session: MagicMock, config: NationalGridConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-504 exception from execute() inside the chunk loop propagates."""
    err = RetryExhaustedError(
        "Exhausted",
        attempts=3,
        last_error=GraphQLError("500 Internal Server Error", endpoint="x", status=500),
    )
    client = NationalGridClient(config=config, session=mock_session)
    monkeypatch.setattr(client, "execute", AsyncMock(side_effect=err))

    with pytest.raises(RetryExhaustedError):
        await client.get_ami_energy_usages_15min(
            meter_number="M-001",
            premise_number="PREM-001",
            service_point_number="SP-001",
            meter_point_number="MP-001",
            date_from=date(2024, 1, 1),
            date_to=date(2024, 1, 5),
        )


@pytest.mark.asyncio
async def test_15min_fell_back_chunk_504_stops_iteration(
    mock_session: MagicMock, config: NationalGridConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After fell_back=True, a 504 on a daily chunk stops iteration gracefully."""
    # 3-chunk range (180 days at 60-day windows). Chunk 0 (newest) 15min ok,
    # chunk 1 15min errors (fell_back=True), chunk 1 daily ok, chunk 2 daily 504 → stop.
    chunk0_15min = GraphQLResponse(
        data={
            "amiEnergyUsages15Min": {
                "nodes": [{"date": "2024-04-15", "fuelType": "ELECTRIC", "quantity": 3.0}]
            }
        }
    )
    chunk1_15min_errors = GraphQLResponse(
        data={"amiEnergyUsages15Min": None},
        errors=[{"message": "err", "extensions": {"code": "InternalError"}}],
    )
    chunk1_daily_ok = GraphQLResponse(
        data={
            "amiEnergyUsages": {
                "nodes": [{"date": "2024-03-01", "fuelType": "ELECTRIC", "quantity": 2.0}]
            }
        }
    )
    chunk2_daily_504 = RetryExhaustedError(
        "Exhausted",
        attempts=3,
        last_error=GraphQLError("504", endpoint="x", status=504),
    )

    client = NationalGridClient(config=config, session=mock_session)
    monkeypatch.setattr(
        client,
        "execute",
        AsyncMock(
            side_effect=[chunk0_15min, chunk1_15min_errors, chunk1_daily_ok, chunk2_daily_504]
        ),
    )

    usages = await client.get_ami_energy_usages_15min(
        meter_number="M-001",
        premise_number="PREM-001",
        service_point_number="SP-001",
        meter_point_number="MP-001",
        date_from=date(2024, 1, 1),
        date_to=date(2024, 6, 28),  # 180 days → 3 × 60-day chunks
        fuel_type="ELECTRIC",
    )

    # Returned what was collected before the 504 — in chronological order
    assert len(usages) == 2
    assert usages[0]["quantity"] == 2.0
    assert usages[1]["quantity"] == 3.0


# ---------------------------------------------------------------------------
# get_ami_energy_usages() — daily-primary with 15-min fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_ami_energy_usages_returns_daily_data(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Happy path: daily endpoint succeeds → single request, results returned."""
    mock_session.post.return_value = _DummyResponse(
        _ami_daily_payload([{"date": "2024-03-01", "fuelType": "ELECTRIC", "quantity": 5.0}])
    )

    client = NationalGridClient(config=config, session=mock_session)
    usages = await client.get_ami_energy_usages(
        meter_number="M-001",
        premise_number="PREM-001",
        service_point_number="SP-001",
        meter_point_number="MP-001",
        date_from=date(2024, 3, 1),
        date_to=date(2024, 3, 31),
    )

    assert mock_session.post.call_count == 1
    assert len(usages) == 1
    assert usages[0]["quantity"] == 5.0


@pytest.mark.asyncio
async def test_get_ami_energy_usages_passes_variables(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Verify correct variables and NrtDailyUsage operation name are sent."""
    mock_session.post.return_value = _DummyResponse(_ami_daily_payload([]))

    client = NationalGridClient(config=config, session=mock_session)
    await client.get_ami_energy_usages(
        meter_number="M-123",
        premise_number=456,
        service_point_number=789,
        meter_point_number=101,
        date_from=date(2024, 3, 1),
        date_to=date(2024, 3, 31),
    )

    args, kwargs = mock_session.post.call_args
    assert args[0] == ENERGY_USAGE_ENDPOINT
    payload = kwargs["json"]
    assert payload["operationName"] == "NrtDailyUsage"
    assert payload["variables"]["meterNumber"] == "M-123"
    assert payload["variables"]["premiseNumber"] == "456"
    assert payload["variables"]["servicePointNumber"] == "789"
    assert payload["variables"]["meterPointNumber"] == "101"
    assert payload["variables"]["dateFrom"] == "2024-03-01"
    assert payload["variables"]["dateTo"] == "2024-03-31"


@pytest.mark.asyncio
async def test_get_ami_energy_usages_accepts_string_dates(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """String date inputs are forwarded unchanged as ISO strings."""
    mock_session.post.return_value = _DummyResponse(_ami_daily_payload([]))

    client = NationalGridClient(config=config, session=mock_session)
    await client.get_ami_energy_usages(
        meter_number="M-001",
        premise_number="PREM-001",
        service_point_number="SP-001",
        meter_point_number="MP-001",
        date_from="2024-01-01",
        date_to="2024-12-31",
    )

    _, kwargs = mock_session.post.call_args
    variables = kwargs["json"]["variables"]
    assert variables["dateFrom"] == "2024-01-01"
    assert variables["dateTo"] == "2024-12-31"


@pytest.mark.asyncio
async def test_get_ami_energy_usages_falls_back_on_graphql_errors(
    mock_session: MagicMock, config: NationalGridConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When NrtDailyUsage returns has_errors, fall back to get_ami_energy_usages_15min."""
    error_response = _DummyResponse(
        {
            "errors": [{"message": "Upstream error", "extensions": {"code": "InternalError"}}],
            "data": {"amiEnergyUsages": None},
        }
    )
    mock_session.post.return_value = error_response

    fallback_records = [{"date": "2024-03-01", "fuelType": "ELECTRIC", "quantity": 9.0}]
    fallback_mock = AsyncMock(return_value=fallback_records)
    client = NationalGridClient(config=config, session=mock_session)
    monkeypatch.setattr(client, "get_ami_energy_usages_15min", fallback_mock)

    usages = await client.get_ami_energy_usages(
        meter_number="M-001",
        premise_number="PREM-001",
        service_point_number="SP-001",
        meter_point_number="MP-001",
        date_from=date(2024, 3, 1),
        date_to=date(2024, 3, 31),
        fuel_type="ELECTRIC",
    )

    # Daily was attempted once, then fallback was invoked
    assert mock_session.post.call_count == 1
    fallback_mock.assert_called_once_with(
        "M-001",
        "PREM-001",
        "SP-001",
        "MP-001",
        date(2024, 3, 1),
        date(2024, 3, 31),
        fuel_type="ELECTRIC",
        headers=None,
        timeout=None,
    )
    assert usages == fallback_records


@pytest.mark.asyncio
async def test_get_ami_energy_usages_falls_back_on_504(
    mock_session: MagicMock, config: NationalGridConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When NrtDailyUsage hits a 504, fall back to get_ami_energy_usages_15min."""
    err = RetryExhaustedError(
        "Exhausted",
        attempts=3,
        last_error=GraphQLError("504", endpoint="x", status=504),
    )
    client = NationalGridClient(config=config, session=mock_session)
    monkeypatch.setattr(client, "execute", AsyncMock(side_effect=err))

    fallback_records = [{"date": "2024-03-01", "fuelType": "GAS", "quantity": 2.5}]
    fallback_mock = AsyncMock(return_value=fallback_records)
    monkeypatch.setattr(client, "get_ami_energy_usages_15min", fallback_mock)

    usages = await client.get_ami_energy_usages(
        meter_number="M-001",
        premise_number="PREM-001",
        service_point_number="SP-001",
        meter_point_number="MP-001",
        date_from=date(2024, 3, 1),
        date_to=date(2024, 3, 31),
        fuel_type="GAS",
    )

    fallback_mock.assert_called_once()
    assert usages == fallback_records


@pytest.mark.asyncio
async def test_get_ami_energy_usages_propagates_non_504_exceptions(
    mock_session: MagicMock, config: NationalGridConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-504 exceptions from execute() propagate — no fallback triggered."""
    err = RetryExhaustedError(
        "Exhausted",
        attempts=3,
        last_error=GraphQLError("500", endpoint="x", status=500),
    )
    client = NationalGridClient(config=config, session=mock_session)
    monkeypatch.setattr(client, "execute", AsyncMock(side_effect=err))

    with pytest.raises(RetryExhaustedError):
        await client.get_ami_energy_usages(
            meter_number="M-001",
            premise_number="PREM-001",
            service_point_number="SP-001",
            meter_point_number="MP-001",
            date_from=date(2024, 3, 1),
            date_to=date(2024, 3, 31),
        )


@pytest.mark.asyncio
async def test_get_ami_energy_usages_graphql_error_propagates(
    mock_session: MagicMock, config: NationalGridConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bare non-504 GraphQLError (not wrapped in RetryExhaustedError) propagates."""
    err = GraphQLError("403 Forbidden", endpoint="x", status=403)
    client = NationalGridClient(config=config, session=mock_session)
    monkeypatch.setattr(client, "execute", AsyncMock(side_effect=err))

    with pytest.raises(GraphQLError):
        await client.get_ami_energy_usages(
            meter_number="M-001",
            premise_number="PREM-001",
            service_point_number="SP-001",
            meter_point_number="MP-001",
            date_from="2024-03-01",
            date_to="2024-03-31",
        )


@pytest.mark.asyncio
async def test_get_ami_energy_usages_fallback_passes_fuel_type(
    mock_session: MagicMock, config: NationalGridConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """fuel_type is forwarded to get_ami_energy_usages_15min() on fallback."""
    mock_session.post.return_value = _DummyResponse(
        {"errors": [{"message": "err"}], "data": {"amiEnergyUsages": None}}
    )

    fallback_mock = AsyncMock(return_value=[])
    client = NationalGridClient(config=config, session=mock_session)
    monkeypatch.setattr(client, "get_ami_energy_usages_15min", fallback_mock)

    await client.get_ami_energy_usages(
        meter_number="M-001",
        premise_number="P-001",
        service_point_number="SP-001",
        meter_point_number="MP-001",
        date_from="2024-01-01",
        date_to="2024-12-31",
        fuel_type="GAS",
    )

    _, kwargs = fallback_mock.call_args
    assert kwargs["fuel_type"] == "GAS"


@pytest.mark.asyncio
async def test_get_ami_energy_usages_fallback_triggers_chunking(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """When daily fails, the 15-min fallback chunks a long date range automatically."""
    # First POST: daily endpoint returns errors
    # Next 2 POSTs: 15-min chunked requests (80-day range → 2 × 60-day chunks)
    mock_session.post.side_effect = [
        _DummyResponse({"errors": [{"message": "err"}], "data": {"amiEnergyUsages": None}}),
        _DummyResponse(
            _ami_15min_payload([{"date": "2024-03-10", "fuelType": "ELECTRIC", "quantity": 2.0}])
        ),
        _DummyResponse(
            _ami_15min_payload([{"date": "2024-01-15", "fuelType": "ELECTRIC", "quantity": 1.0}])
        ),
    ]

    client = NationalGridClient(config=config, session=mock_session)
    usages = await client.get_ami_energy_usages(
        meter_number="M-001",
        premise_number="PREM-001",
        service_point_number="SP-001",
        meter_point_number="MP-001",
        date_from=date(2024, 1, 1),
        date_to=date(2024, 3, 20),  # 80 days → 2 × 60-day chunks
        fuel_type="ELECTRIC",
    )

    # 1 daily attempt + 2 chunked 15-min requests
    assert mock_session.post.call_count == 3

    # First request is the daily attempt
    daily_payload = mock_session.post.call_args_list[0][1]["json"]
    assert daily_payload["operationName"] == "NrtDailyUsage"

    # Remaining requests are 15-min chunks (newest-first)
    chunk1_payload = mock_session.post.call_args_list[1][1]["json"]
    assert chunk1_payload["operationName"] == "NrtDailyUsage15Min"
    assert chunk1_payload["variables"]["dateFrom"] == "2024-03-01"
    assert chunk1_payload["variables"]["dateTo"] == "2024-03-20"

    # Results reassembled in chronological order
    assert len(usages) == 2
    assert usages[0]["quantity"] == 1.0
    assert usages[1]["quantity"] == 2.0


@pytest.mark.asyncio
async def test_get_ami_energy_usages_raises_data_extraction_error(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """DataExtractionError propagates when the daily response is missing the root field."""
    mock_session.post.return_value = _DummyResponse({"data": {}})

    client = NationalGridClient(config=config, session=mock_session)

    with pytest.raises(DataExtractionError, match="Missing 'amiEnergyUsages' field"):
        await client.get_ami_energy_usages(
            meter_number="M-001",
            premise_number="PREM-001",
            service_point_number="SP-001",
            meter_point_number="MP-001",
            date_from="2024-03-01",
            date_to="2024-03-31",
        )


# ---------------------------------------------------------------------------
# Early termination on empty chunks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_chunk_stops_iteration(
    mock_session: MagicMock, config: NationalGridConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty chunk stops iteration; records from prior chunks are returned."""
    good = GraphQLResponse(
        data={
            "amiEnergyUsages15Min": {
                "nodes": [{"date": "2024-03-10", "fuelType": "ELECTRIC", "quantity": 2.0}]
            }
        }
    )
    empty = GraphQLResponse(data={"amiEnergyUsages15Min": {"nodes": []}})
    client = NationalGridClient(config=config, session=mock_session)
    # 3-chunk range (180 days). Newest chunk returns data; second chunk is empty → stop.
    monkeypatch.setattr(client, "execute", AsyncMock(side_effect=[good, empty]))

    usages = await client.get_ami_energy_usages_15min(
        meter_number="M-001",
        premise_number="PREM-001",
        service_point_number="SP-001",
        meter_point_number="MP-001",
        date_from=date(2024, 1, 1),
        date_to=date(2024, 6, 29),  # 180 days → 3 × 60-day chunks
        fuel_type="ELECTRIC",
    )

    assert len(usages) == 1
    assert usages[0]["quantity"] == 2.0
    # Third chunk was never requested — execute called exactly twice.
    assert client.execute.call_count == 2  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_all_zero_chunk_does_not_stop_iteration(
    mock_session: MagicMock, config: NationalGridConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An all-zero-quantity chunk is valid data and does NOT stop iteration."""
    good = GraphQLResponse(
        data={
            "amiEnergyUsages15Min": {
                "nodes": [{"date": "2024-03-10", "fuelType": "ELECTRIC", "quantity": 1.5}]
            }
        }
    )
    all_zero = GraphQLResponse(
        data={
            "amiEnergyUsages15Min": {
                "nodes": [
                    {"date": "2024-01-10", "fuelType": "ELECTRIC", "quantity": 0.0},
                    {"date": "2024-01-11", "fuelType": "ELECTRIC", "quantity": 0.0},
                ]
            }
        }
    )
    client = NationalGridClient(config=config, session=mock_session)
    # 2-chunk range (80 days). Both chunks succeed; all-zero is kept, not discarded.
    monkeypatch.setattr(client, "execute", AsyncMock(side_effect=[good, all_zero]))

    usages = await client.get_ami_energy_usages_15min(
        meter_number="M-001",
        premise_number="PREM-001",
        service_point_number="SP-001",
        meter_point_number="MP-001",
        date_from=date(2024, 1, 1),
        date_to=date(2024, 3, 20),  # 80 days → 60-day + 20-day chunks
        fuel_type="ELECTRIC",
    )

    # Both chunks returned: 2 all-zero + 1 good = 3 records total (chronological order).
    assert len(usages) == 3
    assert usages[0]["quantity"] == 0.0
    assert usages[2]["quantity"] == 1.5


@pytest.mark.asyncio
async def test_first_chunk_empty_returns_empty_list(
    mock_session: MagicMock, config: NationalGridConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the first (newest) chunk is empty, return an empty list."""
    empty = GraphQLResponse(data={"amiEnergyUsages15Min": {"nodes": []}})
    client = NationalGridClient(config=config, session=mock_session)
    monkeypatch.setattr(client, "execute", AsyncMock(side_effect=[empty]))

    usages = await client.get_ami_energy_usages_15min(
        meter_number="M-001",
        premise_number="PREM-001",
        service_point_number="SP-001",
        meter_point_number="MP-001",
        date_from=date(2024, 1, 1),
        date_to=date(2024, 1, 20),
        fuel_type="ELECTRIC",
    )

    assert usages == []


@pytest.mark.asyncio
async def test_empty_chunk_mid_run_daily_fallback_stops_iteration(
    mock_session: MagicMock, config: NationalGridConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Empty result on mid-run daily fallback stops iteration; prior data is returned."""
    chunk0_ok = GraphQLResponse(
        data={
            "amiEnergyUsages15Min": {
                "nodes": [{"date": "2024-04-15", "fuelType": "ELECTRIC", "quantity": 3.0}]
            }
        }
    )
    chunk1_errors = GraphQLResponse(
        data={"amiEnergyUsages15Min": None},
        errors=[{"message": "mid-run error", "extensions": {"code": "InternalError"}}],
    )
    # Daily fallback for chunk 1 returns empty → should stop before chunk 2.
    chunk1_daily_empty = GraphQLResponse(data={"amiEnergyUsages": {"nodes": []}})
    client = NationalGridClient(config=config, session=mock_session)
    # 3-chunk range (180 days). Chunk 0 ok, chunk 1 errors → daily fallback → empty → stop.
    monkeypatch.setattr(
        client,
        "execute",
        AsyncMock(side_effect=[chunk0_ok, chunk1_errors, chunk1_daily_empty]),
    )

    usages = await client.get_ami_energy_usages_15min(
        meter_number="M-001",
        premise_number="PREM-001",
        service_point_number="SP-001",
        meter_point_number="MP-001",
        date_from=date(2024, 1, 1),
        date_to=date(2024, 6, 29),  # 180 days → 3 × 60-day chunks
        fuel_type="ELECTRIC",
    )

    # Only the newest chunk's record survives; third chunk was never fetched.
    assert len(usages) == 1
    assert usages[0]["quantity"] == 3.0
    assert client.execute.call_count == 3  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# get_bills
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_bills_returns_typed_list(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Verify get_bills returns a properly typed list."""
    mock_session.post.return_value = _DummyResponse(
        {
            "data": {
                "bills": {
                    "nodes": [
                        {
                            "dueDate": "2026-04-25",
                            "statementDate": "2026-04-01",
                            "status": "UNPAID",
                            "accountNumber": "0209976152",
                            "totalDueAmount": 123.45,
                            "currentChargesAmount": 110.00,
                        },
                        {
                            "dueDate": "2026-03-25",
                            "statementDate": "2026-03-01",
                            "status": "PAID",
                            "accountNumber": "0209976152",
                            "totalDueAmount": 0.00,
                            "currentChargesAmount": 98.00,
                        },
                    ]
                }
            }
        }
    )

    client = NationalGridClient(config=config, session=mock_session)
    bills = await client.get_bills("acct-001")

    assert len(bills) == 2
    assert bills[0]["statementDate"] == "2026-04-01"
    assert bills[0]["totalDueAmount"] == 123.45
    assert bills[0]["dueDate"] == "2026-04-25"
    assert bills[0]["status"] == "UNPAID"
    assert bills[1]["totalDueAmount"] == 0.00


@pytest.mark.asyncio
async def test_get_bills_passes_account_number_and_uses_bill_endpoint(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Verify get_bills sends accountNumber variable to the correct endpoint."""
    mock_session.post.return_value = _DummyResponse({"data": {"bills": {"nodes": []}}})

    client = NationalGridClient(config=config, session=mock_session)
    await client.get_bills("acct-007")

    args, kwargs = mock_session.post.call_args
    assert args[0] == BILL_ENDPOINT
    payload = kwargs["json"]
    assert payload["variables"]["accountNumber"] == "acct-007"
    assert payload["operationName"] == "BillList"


@pytest.mark.asyncio
async def test_get_bills_raises_data_extraction_error(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """DataExtractionError propagates when 'bills' field is absent."""
    mock_session.post.return_value = _DummyResponse({"data": {}})

    client = NationalGridClient(config=config, session=mock_session)

    with pytest.raises(DataExtractionError, match="Missing 'bills' field"):
        await client.get_bills("acct-001")


# ---------------------------------------------------------------------------
# get_payment_history
# ---------------------------------------------------------------------------

PAYMENT_ENDPOINT = "https://myaccount.nationalgrid.com/api/payment-cu-uwp-gql"


@pytest.mark.asyncio
async def test_get_payment_history_returns_typed_list(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Verify get_payment_history returns a properly typed list."""
    mock_session.post.return_value = _DummyResponse(
        {
            "data": {
                "payments": {
                    "nodes": [
                        {
                            "paymentDate": None,
                            "processedDate": "2025-09-04T22:02:41.471Z",
                            "amount": 17.76,
                            "status": None,
                            "type": None,
                            "method": "ACH_PAYMENT",
                            "source": "PAYMENT",
                            "accountNumber": "0209976152",
                            "errorCode": None,
                            "errorMessage": None,
                        },
                        {
                            "paymentDate": "2025-08-01",
                            "processedDate": "2025-08-02T10:00:00.000Z",
                            "amount": 39.87,
                            "status": "COMPLETED",
                            "type": "ONE_TIME",
                            "method": "ACH_PAYMENT",
                            "source": "PAYMENT",
                            "accountNumber": "0209976152",
                            "errorCode": None,
                            "errorMessage": None,
                        },
                    ]
                }
            }
        }
    )

    client = NationalGridClient(config=config, session=mock_session)
    payments = await client.get_payment_history("acct-001")

    assert len(payments) == 2
    assert payments[0]["processedDate"] == "2025-09-04T22:02:41.471Z"
    assert payments[0]["amount"] == 17.76
    assert payments[0]["method"] == "ACH_PAYMENT"
    assert payments[0]["paymentDate"] is None
    assert payments[1]["status"] == "COMPLETED"


@pytest.mark.asyncio
async def test_get_payment_history_passes_account_number_and_uses_payment_endpoint(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Verify get_payment_history sends accountNumber to the correct endpoint."""
    mock_session.post.return_value = _DummyResponse({"data": {"payments": {"nodes": []}}})

    client = NationalGridClient(config=config, session=mock_session)
    await client.get_payment_history("acct-007")

    args, kwargs = mock_session.post.call_args
    assert args[0] == PAYMENT_ENDPOINT
    payload = kwargs["json"]
    assert payload["variables"]["accountNumber"] == "acct-007"
    assert payload["operationName"] == "PaymentHistory"


@pytest.mark.asyncio
async def test_get_payment_history_raises_data_extraction_error(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """DataExtractionError propagates when 'payments' field is absent."""
    mock_session.post.return_value = _DummyResponse({"data": {}})

    client = NationalGridClient(config=config, session=mock_session)

    with pytest.raises(DataExtractionError, match="Missing 'payments' field"):
        await client.get_payment_history("acct-001")


# ---------------------------------------------------------------------------
# get_account_dashboard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_account_dashboard_returns_typed_dict(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Verify get_account_dashboard returns properly typed data."""
    mock_session.post.return_value = _DummyResponse(
        {
            "data": {
                "user": {
                    "firstName": "Jane",
                    "lastName": "Doe",
                    "accountLinks": {
                        "nodes": [
                            {
                                "billingAccount": {
                                    "accountNumber": "0209976152",
                                    "currentBalance": 123.45,
                                    "currentBalanceRefreshDate": "2026-05-01",
                                    "status": "ACTIVE",
                                    "collectionStatus": None,
                                    "isCashOnly": False,
                                    "isEnrolledInPaymentPlan": False,
                                    "isEnrolledInRecurringPay": True,
                                    "paperlessBilling": {
                                        "accountNumber": "0209976152",
                                        "status": "ENROLLED",
                                        "enrolledVia": "WEB",
                                    },
                                    "balancedBilling": None,
                                    "recurringPayDetails": {
                                        "amountType": "BALANCE_DUE",
                                        "amount": None,
                                        "status": "ACTIVE",
                                        "planStartDate": "2025-01-01",
                                        "paymentType": "ACH",
                                    },
                                    "scheduledPayments": {
                                        "nodes": [
                                            {
                                                "amount": 99.00,
                                                "paymentDate": "2026-05-15",
                                                "status": "SCHEDULED",
                                                "method": "ACH_PAYMENT",
                                                "type": "RECURRING",
                                                "paymentSequenceNumber": 1,
                                            }
                                        ]
                                    },
                                    "recentBills": {
                                        "nodes": [
                                            {
                                                "currentChargesAmount": 99.00,
                                                "totalDueAmount": 123.45,
                                                "statementDate": "2026-04-01",
                                                "dueDate": "2026-04-25",
                                            }
                                        ]
                                    },
                                }
                            }
                        ]
                    },
                }
            }
        }
    )

    client = NationalGridClient(config=config, session=mock_session)
    dashboard = await client.get_account_dashboard("0209976152")

    assert dashboard["firstName"] == "Jane"
    assert dashboard["lastName"] == "Doe"
    assert dashboard["accountNumber"] == "0209976152"
    assert dashboard["currentBalance"] == 123.45
    assert dashboard["status"] == "ACTIVE"
    assert dashboard["isEnrolledInRecurringPay"] is True
    assert dashboard["paperlessBilling"] is not None
    assert dashboard["paperlessBilling"]["status"] == "ENROLLED"
    assert dashboard["balancedBilling"] is None
    assert len(dashboard["scheduledPayments"]) == 1
    assert dashboard["scheduledPayments"][0]["amount"] == 99.00
    assert len(dashboard["recentBills"]) == 1
    assert dashboard["recentBills"][0]["totalDueAmount"] == 123.45


@pytest.mark.asyncio
async def test_get_account_dashboard_passes_variables_and_uses_correct_endpoint(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Verify get_account_dashboard sends correct variables and hits user endpoint."""
    mock_session.post.return_value = _DummyResponse(
        {
            "data": {
                "user": {
                    "firstName": "A",
                    "lastName": "B",
                    "accountLinks": {
                        "nodes": [
                            {
                                "billingAccount": {
                                    "accountNumber": "acct-001",
                                    "currentBalance": 0.0,
                                    "currentBalanceRefreshDate": None,
                                    "status": None,
                                    "collectionStatus": None,
                                    "isCashOnly": None,
                                    "isEnrolledInPaymentPlan": None,
                                    "isEnrolledInRecurringPay": None,
                                    "paperlessBilling": None,
                                    "balancedBilling": None,
                                    "recurringPayDetails": None,
                                    "scheduledPayments": {"nodes": []},
                                    "recentBills": {"nodes": []},
                                }
                            }
                        ]
                    },
                }
            }
        }
    )

    client = NationalGridClient(config=config, session=mock_session)
    client._login_data["sub"] = "user-sub-abc"
    await client.get_account_dashboard("acct-001")

    args, kwargs = mock_session.post.call_args
    assert args[0] == LINKED_BILLING_ENDPOINT
    payload = kwargs["json"]
    assert payload["variables"]["accountNumber"] == "acct-001"
    assert payload["variables"]["userId"] == "user-sub-abc"
    assert payload["operationName"] == "AccountDashboard"


@pytest.mark.asyncio
async def test_get_account_dashboard_raises_when_no_account_links(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """DataExtractionError raised when accountLinks.nodes is empty."""
    mock_session.post.return_value = _DummyResponse(
        {
            "data": {
                "user": {
                    "firstName": "A",
                    "lastName": "B",
                    "accountLinks": {"nodes": []},
                }
            }
        }
    )

    client = NationalGridClient(config=config, session=mock_session)

    with pytest.raises(DataExtractionError, match="No account links found"):
        await client.get_account_dashboard("acct-001")


# ---------------------------------------------------------------------------
# get_meter_reading
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_meter_reading_returns_typed_dict(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Verify get_meter_reading returns typed MeterReading."""
    mock_session.post.return_value = _DummyResponse(
        {
            "data": {
                "meterReading": {
                    "meterReadingStatus": "ELIGIBLE",
                    "isEligible": True,
                    "transactionDate": "2026-04-01",
                    "reading": 12345,
                    "submitMeterReadingInEligibleReason": None,
                    "errorMessage": None,
                }
            }
        }
    )

    client = NationalGridClient(config=config, session=mock_session)
    result = await client.get_meter_reading("acct-001")

    assert result is not None
    assert result["isEligible"] is True
    assert result["reading"] == 12345
    assert result["meterReadingStatus"] == "ELIGIBLE"


@pytest.mark.asyncio
async def test_get_meter_reading_returns_none_when_absent(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """get_meter_reading returns None when meterReading field is null."""
    mock_session.post.return_value = _DummyResponse({"data": {"meterReading": None}})

    client = NationalGridClient(config=config, session=mock_session)
    result = await client.get_meter_reading("acct-001")

    assert result is None


@pytest.mark.asyncio
async def test_get_meter_reading_uses_correct_endpoint_and_no_variables(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Verify meter reading uses inline account number and no variables key."""
    mock_session.post.return_value = _DummyResponse({"data": {"meterReading": None}})

    client = NationalGridClient(config=config, session=mock_session)
    await client.get_meter_reading("acct-007")

    args, kwargs = mock_session.post.call_args
    assert args[0] == METER_READING_ENDPOINT
    payload = kwargs["json"]
    assert "variables" not in payload
    assert "acct-007" in payload["query"]
    assert payload["operationName"] == "MeterReading"


# ---------------------------------------------------------------------------
# get_paperless_billing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_paperless_billing_returns_typed_dict(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Verify get_paperless_billing returns typed PaperlessBilling."""
    mock_session.post.return_value = _DummyResponse(
        {
            "data": {
                "paperlessBilling": {
                    "accountNumber": "acct-001",
                    "status": "ENROLLED",
                    "enrolledVia": "WEB",
                }
            }
        }
    )

    client = NationalGridClient(config=config, session=mock_session)
    result = await client.get_paperless_billing("acct-001")

    assert result is not None
    assert result["status"] == "ENROLLED"
    assert result["enrolledVia"] == "WEB"


@pytest.mark.asyncio
async def test_get_paperless_billing_returns_none_when_absent(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """get_paperless_billing returns None when field is null."""
    mock_session.post.return_value = _DummyResponse({"data": {"paperlessBilling": None}})

    client = NationalGridClient(config=config, session=mock_session)
    result = await client.get_paperless_billing("acct-001")

    assert result is None


@pytest.mark.asyncio
async def test_get_paperless_billing_uses_correct_endpoint_and_no_variables(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Verify paperless billing uses inline account number and no variables key."""
    mock_session.post.return_value = _DummyResponse({"data": {"paperlessBilling": None}})

    client = NationalGridClient(config=config, session=mock_session)
    await client.get_paperless_billing("acct-007")

    args, kwargs = mock_session.post.call_args
    assert args[0] == PAPERLESS_BILLING_ENDPOINT
    payload = kwargs["json"]
    assert "variables" not in payload
    assert "acct-007" in payload["query"]
    assert payload["operationName"] == "PaperlessBilling"


# ---------------------------------------------------------------------------
# get_balanced_billing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_balanced_billing_returns_typed_dict(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Verify get_balanced_billing returns typed BalancedBilling."""
    mock_session.post.return_value = _DummyResponse(
        {
            "data": {
                "balancedBilling": {
                    "status": "ACTIVE",
                    "billingAccountNumber": "acct-001",
                    "amountBilledToDate": 500.00,
                    "actualUsageToDate": 480.00,
                    "planStartDate": "2026-01-01",
                    "currentMonthlyPayment": 100.00,
                    "difference": 20.00,
                }
            }
        }
    )

    client = NationalGridClient(config=config, session=mock_session)
    result = await client.get_balanced_billing("acct-001")

    assert result is not None
    assert result["status"] == "ACTIVE"
    assert result["currentMonthlyPayment"] == 100.00


@pytest.mark.asyncio
async def test_get_balanced_billing_returns_none_when_not_enrolled(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """get_balanced_billing returns None when not enrolled."""
    mock_session.post.return_value = _DummyResponse({"data": {"balancedBilling": None}})

    client = NationalGridClient(config=config, session=mock_session)
    result = await client.get_balanced_billing("acct-001")

    assert result is None


@pytest.mark.asyncio
async def test_get_balanced_billing_uses_correct_endpoint_and_no_variables(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Verify balanced billing uses inline account number and no variables key."""
    mock_session.post.return_value = _DummyResponse({"data": {"balancedBilling": None}})

    client = NationalGridClient(config=config, session=mock_session)
    await client.get_balanced_billing("acct-007")

    args, kwargs = mock_session.post.call_args
    assert args[0] == BALANCED_BILLING_ENDPOINT
    payload = kwargs["json"]
    assert "variables" not in payload
    assert "acct-007" in payload["query"]
    assert payload["operationName"] == "BalancedBilling"


# ---------------------------------------------------------------------------
# get_payment_plans
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_payment_plans_returns_typed_list(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Verify get_payment_plans returns typed list of PaymentPlan."""
    mock_session.post.return_value = _DummyResponse(
        {
            "data": {
                "paymentPlans": {
                    "nodes": [
                        {
                            "paymentAgreementStatus": "ACTIVE",
                            "monthlyInstallmentAmount": 50.00,
                            "totalNumberOfInstallments": 12,
                            "totalNumberOfInstallmentsRemaining": 8,
                            "currentInstallmentStatus": "CURRENT",
                            "finalInstallmentAmount": 50.00,
                            "requiredDownPaymentAmount": 0.00,
                            "downPaymentStatus": None,
                            "downPaymentDueDate": None,
                            "planSequenceNumber": 1,
                            "reactivationFee": None,
                            "planCompletedDate": None,
                        }
                    ]
                }
            }
        }
    )

    client = NationalGridClient(config=config, session=mock_session)
    plans = await client.get_payment_plans("acct-001")

    assert len(plans) == 1
    assert plans[0]["paymentAgreementStatus"] == "ACTIVE"
    assert plans[0]["monthlyInstallmentAmount"] == 50.00
    assert plans[0]["totalNumberOfInstallments"] == 12


@pytest.mark.asyncio
async def test_get_payment_plans_returns_empty_list(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """get_payment_plans returns empty list when no plans active."""
    mock_session.post.return_value = _DummyResponse({"data": {"paymentPlans": {"nodes": []}}})

    client = NationalGridClient(config=config, session=mock_session)
    plans = await client.get_payment_plans("acct-001")

    assert plans == []


@pytest.mark.asyncio
async def test_get_payment_plans_uses_correct_endpoint_and_no_variables(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Verify payment plans uses inline account number and no variables key."""
    mock_session.post.return_value = _DummyResponse({"data": {"paymentPlans": {"nodes": []}}})

    client = NationalGridClient(config=config, session=mock_session)
    await client.get_payment_plans("acct-007")

    args, kwargs = mock_session.post.call_args
    assert args[0] == PAYMENT_PLANS_ENDPOINT
    payload = kwargs["json"]
    assert "variables" not in payload
    assert "acct-007" in payload["query"]
    assert payload["operationName"] == "PaymentPlans"


@pytest.mark.asyncio
async def test_get_payment_plans_raises_data_extraction_error(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """DataExtractionError propagates when 'paymentPlans' field is absent."""
    mock_session.post.return_value = _DummyResponse({"data": {}})

    client = NationalGridClient(config=config, session=mock_session)

    with pytest.raises(DataExtractionError, match="Missing 'paymentPlans' field"):
        await client.get_payment_plans("acct-001")


# ---------------------------------------------------------------------------
# get_collection_arrangements
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_collection_arrangements_returns_typed_list(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Verify get_collection_arrangements returns typed list."""
    mock_session.post.return_value = _DummyResponse(
        {
            "data": {
                "collectionArrangements": {
                    "nodes": [
                        {
                            "totalAmountDue": 300.00,
                            "numberOfInstallments": 3,
                            "agreementDate": "2026-01-01",
                            "arrangementStatus": "ACTIVE",
                            "statusUpdateDate": "2026-01-01",
                            "completedDate": None,
                            "addedOn": "2026-01-01",
                            "details": {
                                "nodes": [
                                    {
                                        "sequenceNumber": 1,
                                        "installmentAmount": 100.00,
                                        "installmentDueDate": "2026-02-01",
                                        "installmentStatus": "PAID",
                                    }
                                ]
                            },
                        }
                    ]
                }
            }
        }
    )

    client = NationalGridClient(config=config, session=mock_session)
    arrangements = await client.get_collection_arrangements("acct-001")

    assert len(arrangements) == 1
    assert arrangements[0]["totalAmountDue"] == 300.00
    assert arrangements[0]["arrangementStatus"] == "ACTIVE"
    assert len(arrangements[0]["details"]["nodes"]) == 1
    assert arrangements[0]["details"]["nodes"][0]["installmentAmount"] == 100.00


@pytest.mark.asyncio
async def test_get_collection_arrangements_returns_empty_list(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """get_collection_arrangements returns empty list when none active."""
    mock_session.post.return_value = _DummyResponse(
        {"data": {"collectionArrangements": {"nodes": []}}}
    )

    client = NationalGridClient(config=config, session=mock_session)
    arrangements = await client.get_collection_arrangements("acct-001")

    assert arrangements == []


@pytest.mark.asyncio
async def test_get_collection_arrangements_uses_correct_endpoint_and_no_variables(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """Verify collection arrangements uses inline account number and no variables key."""
    mock_session.post.return_value = _DummyResponse(
        {"data": {"collectionArrangements": {"nodes": []}}}
    )

    client = NationalGridClient(config=config, session=mock_session)
    await client.get_collection_arrangements("acct-007")

    args, kwargs = mock_session.post.call_args
    assert args[0] == COLLECTION_ARRANGEMENTS_ENDPOINT
    payload = kwargs["json"]
    assert "variables" not in payload
    assert "acct-007" in payload["query"]
    assert payload["operationName"] == "CollectionArrangements"


@pytest.mark.asyncio
async def test_get_collection_arrangements_raises_data_extraction_error(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """DataExtractionError propagates when 'collectionArrangements' field is absent."""
    mock_session.post.return_value = _DummyResponse({"data": {}})

    client = NationalGridClient(config=config, session=mock_session)

    with pytest.raises(DataExtractionError, match="Missing 'collectionArrangements' field"):
        await client.get_collection_arrangements("acct-001")


# ---------------------------------------------------------------------------
# get_premise
# ---------------------------------------------------------------------------

_PREMISE_NODE = {
    "premiseSummaryKey": "PSK001",
    "premiseNumber": "123456",
    "premiseStatus": "ACTIVE",
    "isCrisAddress": False,
    "streetNumber": "1",
    "streetName": "Example Road",
    "streetAddress": "1 Example Road",
    "apartment": "",
    "city": "Anytown",
    "buildingNumber": None,
    "notes": None,
    "zipcode": "12345",
    "state": "NY",
    "compressedAddress": "1 EXAMPLE RD, ANYTOWN, NY 12345",
    "companyCode": "EXAMPLE_CO",
    "region": "NY",
    "meter": {
        "nodes": [
            {
                "meterNumber": "M001",
                "premiseNumber": "123456",
                "fuelType": "ELECTRIC",
                "meterStatus": "ACTIVE",
            }
        ]
    },
}


@pytest.mark.asyncio
async def test_get_premise_returns_nodes(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """get_premise returns parsed premise nodes including nested meter data."""
    mock_session.post.return_value = _DummyResponse(
        {"data": {"premise": {"nodes": [_PREMISE_NODE]}}}
    )

    client = NationalGridClient(config=config, session=mock_session)
    result = await client.get_premise(
        city="Anytown", state="NY", street_name="1 Example Road", zip_code="12345"
    )

    assert len(result) == 1
    assert result[0]["premiseNumber"] == "123456"
    assert result[0]["premiseStatus"] == "ACTIVE"
    assert result[0]["compressedAddress"] == "1 EXAMPLE RD, ANYTOWN, NY 12345"
    assert result[0]["meter"]["nodes"][0]["fuelType"] == "ELECTRIC"
    assert result[0]["meter"]["nodes"][0]["meterNumber"] == "M001"


@pytest.mark.asyncio
async def test_get_premise_returns_empty_list(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """get_premise returns an empty list when no premises match."""
    mock_session.post.return_value = _DummyResponse({"data": {"premise": {"nodes": []}}})

    client = NationalGridClient(config=config, session=mock_session)
    result = await client.get_premise(
        city="Nowhere", state="NY", street_name="999 Fake Street", zip_code="00000"
    )

    assert result == []


@pytest.mark.asyncio
async def test_get_premise_routes_to_premise_endpoint(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """get_premise sends the request to the premise-cu-uwp-gql endpoint."""
    mock_session.post.return_value = _DummyResponse({"data": {"premise": {"nodes": []}}})

    client = NationalGridClient(config=config, session=mock_session)
    await client.get_premise(
        city="Anytown", state="NY", street_name="1 Example Road", zip_code="12345"
    )

    args, kwargs = mock_session.post.call_args
    assert args[0] == PREMISE_ENDPOINT
    assert kwargs["json"]["operationName"] == "Premise"


@pytest.mark.asyncio
async def test_get_premise_sends_correct_variables(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """get_premise sends the expected GraphQL variables."""
    mock_session.post.return_value = _DummyResponse({"data": {"premise": {"nodes": []}}})

    client = NationalGridClient(config=config, session=mock_session)
    await client.get_premise(
        city="Anytown",
        state="NY",
        street_name="1 Example Road",
        zip_code="12345",
        apartment="2B",
    )

    variables = mock_session.post.call_args[1]["json"]["variables"]
    assert variables["city"] == "Anytown"
    assert variables["state"] == "NY"
    assert variables["streetName"] == "1 Example Road"
    assert variables["zipCode"] == "12345"
    assert variables["apartment"] == "2B"


@pytest.mark.asyncio
async def test_get_premise_raises_data_extraction_error(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """DataExtractionError propagates when 'premise' field is absent."""
    mock_session.post.return_value = _DummyResponse({"data": {}})

    client = NationalGridClient(config=config, session=mock_session)

    with pytest.raises(DataExtractionError, match="Missing 'premise' field"):
        await client.get_premise(
            city="Anytown", state="NY", street_name="1 Example Road", zip_code="12345"
        )


# ---------------------------------------------------------------------------
# get_electric_bill_history
# ---------------------------------------------------------------------------

_ELECTRIC_BILL = {
    "readDate": "2026-04-13T00:00:00",
    "readDays": 33,
    "readType": "Actual",
    "totalKwh": 144.0,
    "utilityCharges": 34.29,
    "supplierCharges": 11.75,
    "latePayment": 0.0,
    "totalCharges": 45.44,
    "avgDailyUsage": 4.0,
    "rkva": 0.0,
    "meteredPeakKw": 0.0,
    "meteredOnPeakKw": 0.0,
    "billedPeakKw": 0.0,
    "billedOnPeakKw": 0.0,
    "touOnPeakKwh": 0.0,
    "touOffPeakKwh": 0.0,
    "loadFactor": 0.0,
    "readFromDate": "2026-03-11T00:00:00",
    "relativeMonthBillDate": "2026-04-01T00:00:00",
    "timeStamp": "2026-04-13T18:17:15.304388",
}

_GAS_BILL = {
    "readDate": "2026-04-13T00:00:00",
    "readDays": 33,
    "readType": "Actual",
    "totalTherms": 57.0,
    "utilityCharges": 69.26,
    "supplierCharges": 35.86,
    "latePayment": 0.0,
    "totalCharges": 105.12,
    "avgDailyUsage": 2.0,
    "readFromDate": "2026-03-11T00:00:00",
    "relativeMonthBillDate": "2026-04-01T00:00:00",
    "timeStamp": "2026-04-13T18:17:15.299589",
}


@pytest.mark.asyncio
async def test_get_electric_bill_history_returns_records(
    mock_session: MagicMock, config: NationalGridConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Happy path: returns a list of ElectricBillRecord dicts."""
    from py_nationalgrid.rest import RestResponse

    client = NationalGridClient(config=config, session=mock_session)
    monkeypatch.setattr(client, "_get_business_id_token", AsyncMock(return_value="id-tok"))
    monkeypatch.setattr(
        client,
        "_request_business_rest",
        AsyncMock(
            return_value=RestResponse(
                status=200, headers={}, data={"electricBillHistory": [_ELECTRIC_BILL]}
            )
        ),
    )

    records = await client.get_electric_bill_history("0209976152", "88144626")

    assert len(records) == 1
    assert records[0]["totalKwh"] == 144.0
    assert records[0]["utilityCharges"] == 34.29
    assert records[0]["supplierCharges"] == 11.75
    assert records[0]["readFromDate"] == "2026-03-11T00:00:00"


@pytest.mark.asyncio
async def test_get_electric_bill_history_sends_correct_payload(
    mock_session: MagicMock, config: NationalGridConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies the POST body and business auth headers are correct."""
    from py_nationalgrid.rest import RestResponse
    from py_nationalgrid.rest_queries import BUSINESS_SUBSCRIPTION_KEY

    client = NationalGridClient(config=config, session=mock_session)
    client._login_data["sub"] = "test-object-id"
    monkeypatch.setattr(client, "_get_business_id_token", AsyncMock(return_value="id-tok"))
    mock_rest = AsyncMock(
        return_value=RestResponse(status=200, headers={}, data={"electricBillHistory": []})
    )
    monkeypatch.setattr(client, "_request_business_rest", mock_rest)

    await client.get_electric_bill_history("0209976152", "88144626")

    _, kwargs = mock_rest.call_args
    assert kwargs["json"] == {
        "accountNumber": "0209976152",
        "customerNumber": "88144626",
        "isPal": False,
    }
    headers = kwargs["headers"]
    assert headers["Authorization"] == "Bearer id-tok"
    assert headers["ObjectId"] == "test-object-id"
    assert headers["Ocp-Apim-Subscription-Key"] == BUSINESS_SUBSCRIPTION_KEY


@pytest.mark.asyncio
async def test_get_electric_bill_history_returns_empty_on_204(
    mock_session: MagicMock, config: NationalGridConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """204 No Content returns an empty list."""
    from py_nationalgrid.rest import RestResponse

    client = NationalGridClient(config=config, session=mock_session)
    monkeypatch.setattr(client, "_get_business_id_token", AsyncMock(return_value="id-tok"))
    monkeypatch.setattr(
        client,
        "_request_business_rest",
        AsyncMock(return_value=RestResponse(status=204, headers={}, data=None)),
    )

    records = await client.get_electric_bill_history("0209976152", "88144626")
    assert records == []


# ---------------------------------------------------------------------------
# get_gas_bill_history
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_gas_bill_history_returns_records(
    mock_session: MagicMock, config: NationalGridConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Happy path: returns a list of GasBillRecord dicts."""
    from py_nationalgrid.rest import RestResponse

    client = NationalGridClient(config=config, session=mock_session)
    monkeypatch.setattr(client, "_get_business_id_token", AsyncMock(return_value="id-tok"))
    monkeypatch.setattr(
        client,
        "_request_business_rest",
        AsyncMock(
            return_value=RestResponse(status=200, headers={}, data={"gasBillHistory": [_GAS_BILL]})
        ),
    )

    records = await client.get_gas_bill_history("0209976152", "88144626")

    assert len(records) == 1
    assert records[0]["totalTherms"] == 57.0
    assert records[0]["utilityCharges"] == 69.26
    assert records[0]["readFromDate"] == "2026-03-11T00:00:00"


@pytest.mark.asyncio
async def test_get_gas_bill_history_returns_empty_on_204(
    mock_session: MagicMock, config: NationalGridConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """204 No Content returns an empty list."""
    from py_nationalgrid.rest import RestResponse

    client = NationalGridClient(config=config, session=mock_session)
    monkeypatch.setattr(client, "_get_business_id_token", AsyncMock(return_value="id-tok"))
    monkeypatch.setattr(
        client,
        "_request_business_rest",
        AsyncMock(return_value=RestResponse(status=204, headers={}, data=None)),
    )

    records = await client.get_gas_bill_history("0209976152", "88144626")
    assert records == []
