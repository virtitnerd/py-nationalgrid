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
from py_nationalgrid.queries import BILL_ENDPOINT, ENERGY_USAGE_ENDPOINT


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
    """ELECTRIC 120-day range → three 45-day chunks with correct date boundaries."""
    # 2024-01-01 to 2024-04-29 = 120 days → 3 chunks (45 + 45 + 30)
    # Chunks are fetched newest-first: (Mar 31–Apr 29), (Feb 15–Mar 30), (Jan 1–Feb 14)
    mock_session.post.side_effect = [
        _DummyResponse(
            _ami_15min_payload([{"date": "2024-04-10", "fuelType": "ELECTRIC", "quantity": 3.0}])
        ),
        _DummyResponse(
            _ami_15min_payload([{"date": "2024-03-01", "fuelType": "ELECTRIC", "quantity": 2.0}])
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
        date_to=date(2024, 4, 29),
        fuel_type="ELECTRIC",
    )

    assert mock_session.post.call_count == 3
    assert len(usages) == 3
    assert usages[0]["quantity"] == 1.0
    assert usages[1]["quantity"] == 2.0
    assert usages[2]["quantity"] == 3.0

    # Verify chunk boundaries — newest chunk is requested first
    chunk1_vars = mock_session.post.call_args_list[0][1]["json"]["variables"]
    assert chunk1_vars["dateFrom"] == "2024-03-31"
    assert chunk1_vars["dateTo"] == "2024-04-29"

    chunk2_vars = mock_session.post.call_args_list[1][1]["json"]["variables"]
    assert chunk2_vars["dateFrom"] == "2024-02-15"
    assert chunk2_vars["dateTo"] == "2024-03-30"

    chunk3_vars = mock_session.post.call_args_list[2][1]["json"]["variables"]
    assert chunk3_vars["dateFrom"] == "2024-01-01"
    assert chunk3_vars["dateTo"] == "2024-02-14"


@pytest.mark.asyncio
async def test_gas_chunking_uses_45_day_windows(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """GAS 91-day range → three 45-day-max chunks."""
    # 2024-01-01 to 2024-04-01 = 92 days → 3 chunks (45 + 45 + 2)
    # Chunks are fetched newest-first: (Mar 31–Apr 1), (Feb 15–Mar 30), (Jan 1–Feb 14)
    mock_session.post.side_effect = [
        _DummyResponse(
            _ami_15min_payload([{"date": "2024-04-01", "fuelType": "GAS", "quantity": 3.0}])
        ),
        _DummyResponse(
            _ami_15min_payload([{"date": "2024-02-25", "fuelType": "GAS", "quantity": 2.0}])
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
        date_to=date(2024, 4, 1),
        fuel_type="GAS",
    )

    assert mock_session.post.call_count == 3
    assert len(usages) == 3

    # Newest chunk is requested first
    chunk1_vars = mock_session.post.call_args_list[0][1]["json"]["variables"]
    assert chunk1_vars["dateFrom"] == "2024-03-31"
    assert chunk1_vars["dateTo"] == "2024-04-01"

    chunk2_vars = mock_session.post.call_args_list[1][1]["json"]["variables"]
    assert chunk2_vars["dateFrom"] == "2024-02-15"
    assert chunk2_vars["dateTo"] == "2024-03-30"

    chunk3_vars = mock_session.post.call_args_list[2][1]["json"]["variables"]
    assert chunk3_vars["dateFrom"] == "2024-01-01"
    assert chunk3_vars["dateTo"] == "2024-02-14"


@pytest.mark.asyncio
async def test_unknown_fuel_type_uses_conservative_45_day_window(
    mock_session: MagicMock, config: NationalGridConfig
) -> None:
    """fuel_type=None defaults to 45-day chunks (same as ELECTRIC and GAS)."""
    # 50-day range → would be 1 chunk at 90 days but 2 chunks at 45 days
    mock_session.post.side_effect = [
        _DummyResponse(
            _ami_15min_payload([{"date": "2024-01-15", "fuelType": "ELECTRIC", "quantity": 1.0}])
        ),
        _DummyResponse(
            _ami_15min_payload([{"date": "2024-03-01", "fuelType": "ELECTRIC", "quantity": 2.0}])
        ),
    ]

    client = NationalGridClient(config=config, session=mock_session)
    usages = await client.get_ami_energy_usages_15min(
        meter_number="M-001",
        premise_number="PREM-001",
        service_point_number="SP-001",
        meter_point_number="MP-001",
        date_from=date(2024, 1, 1),
        date_to=date(2024, 2, 19),  # 50 days
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
    full_to = date(2024, 4, 29)  # 120-day range → would chunk if 15min worked

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
    monkeypatch.setattr(client, "execute", AsyncMock(side_effect=[good, err]))

    # 50-day range → 2 × 45-day chunks for GAS; second chunk hits 504
    usages = await client.get_ami_energy_usages_15min(
        meter_number="M-001",
        premise_number="PREM-001",
        service_point_number="SP-001",
        meter_point_number="MP-001",
        date_from=date(2024, 1, 1),
        date_to=date(2024, 2, 19),
        fuel_type="GAS",
    )
    assert len(usages) == 1
    assert usages[0]["quantity"] == 1.0


@pytest.mark.asyncio
async def test_15min_mid_run_fallback_switches_to_daily(
    mock_session: MagicMock, config: NationalGridConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When a mid-run (i>0) chunk returns errors, remaining chunks use daily endpoint."""
    # 3-chunk range (120 days). Chunks fetched newest-first.
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
        date_to=date(2024, 4, 29),
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
    # 3-chunk range. Chunk 0 (newest) 15min ok, chunk 1 15min errors (fell_back=True),
    # chunk 1 daily ok, chunk 2 daily 504 → stop, return collected so far.
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
        date_to=date(2024, 4, 29),
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
    # Next 3 POSTs: 15-min chunked requests (120-day range → 3 × 45-day chunks)
    mock_session.post.side_effect = [
        _DummyResponse({"errors": [{"message": "err"}], "data": {"amiEnergyUsages": None}}),
        _DummyResponse(
            _ami_15min_payload([{"date": "2024-04-10", "fuelType": "ELECTRIC", "quantity": 3.0}])
        ),
        _DummyResponse(
            _ami_15min_payload([{"date": "2024-03-01", "fuelType": "ELECTRIC", "quantity": 2.0}])
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
        date_to=date(2024, 4, 29),
        fuel_type="ELECTRIC",
    )

    # 1 daily attempt + 3 chunked 15-min requests
    assert mock_session.post.call_count == 4

    # First request is the daily attempt
    daily_payload = mock_session.post.call_args_list[0][1]["json"]
    assert daily_payload["operationName"] == "NrtDailyUsage"

    # Remaining 3 requests are 15-min chunks (newest-first)
    chunk1_payload = mock_session.post.call_args_list[1][1]["json"]
    assert chunk1_payload["operationName"] == "NrtDailyUsage15Min"
    assert chunk1_payload["variables"]["dateFrom"] == "2024-03-31"
    assert chunk1_payload["variables"]["dateTo"] == "2024-04-29"

    # Results reassembled in chronological order
    assert len(usages) == 3
    assert usages[0]["quantity"] == 1.0
    assert usages[1]["quantity"] == 2.0
    assert usages[2]["quantity"] == 3.0


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
