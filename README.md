# py-nationalgrid

[![PyPI](https://img.shields.io/pypi/v/py-nationalgrid)](https://pypi.org/project/py-nationalgrid/)

Async Python client for National Grid's GraphQL and REST APIs.

## Installation
```bash
pip install py-nationalgrid
```

## Quick Start
```python
import asyncio
from py_nationalgrid import NationalGridClient, NationalGridConfig

async def main() -> None:
    config = NationalGridConfig(
        username="user@example.com",
        password="your-password",
    )

    async with NationalGridClient(config=config) as client:
        accounts = await client.get_linked_accounts()
        for account in accounts:
            print(account["billingAccountId"])

if __name__ == "__main__":
    asyncio.run(main())
```

## API Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get_linked_accounts()` | `list[AccountLink]` | Get linked billing account IDs |
| `get_billing_account()` | `BillingAccount` | Get account details (region, meters, address) |
| `get_energy_usage_costs()` | `list[EnergyUsageCost]` | Get energy costs for a billing period |
| `get_energy_usages()` | `list[EnergyUsage]` | Get historical usage data |
| `get_ami_energy_usages_15min()` | `list[AmiEnergyUsage]` | **Primary AMI method.** 15-minute interval data for ELECTRIC & GAS. Auto-chunks large ranges, falls back to daily on API errors, and handles the ~45-day hot storage limit gracefully. See below. |
| `get_ami_energy_usages()` | `list[AmiEnergyUsage]` | AMI daily energy usage. Used as the fallback inside `get_ami_energy_usages_15min()`; call directly only if you want to bypass the 15-minute endpoint entirely. |
| `get_interval_reads()` | `list[IntervalRead]` | Real-time meter interval reads. Returns `[]` for meters with no interval data (e.g. GAS). |

All methods return typed results using TypedDict models.

## AMI 15-Minute Energy Usage

`get_ami_energy_usages_15min()` is the primary method for fetching AMI interval data and handles several National Grid API quirks automatically.

### Chunking

The National Grid API imposes a hard limit of approximately 10,000 records per response, and the Azure Application Gateway enforces a backend timeout that cuts off requests spanning more than roughly 45 days of data regardless of record count.

To work around this, the method automatically splits any date range that exceeds 45 days into 45-day chunks and concatenates the results. Both ELECTRIC and GAS meters use 45-day chunks:

- ELECTRIC: 96 records/day × 45 days = 4,320 records per chunk (well inside the 10k cap)
- GAS: 24 records/day × 45 days = 1,080 records per chunk

Chunks are requested **newest-first** to ensure the most recent data is always fetched successfully before older chunks are attempted.

### Hot Storage Window (~45 days)

National Grid's API only serves data from "hot" (immediately accessible) storage for approximately the last 45 days from today. Data older than that sits in cold/archive storage. Any query that touches cold storage — even a single-day range — will trigger a 504 Gateway Timeout from the Azure Application Gateway.

**This is a server-side constraint.** There is no client-side configuration that can change it.

Because chunks are fetched newest-first, a 504 on an older chunk does not discard the recent data already collected. The method logs a warning and returns whatever records were successfully retrieved:

```
WARNING amiEnergyUsages15Min: 504 on chunk 2/4 (2025-01-01 to 2025-02-14) —
data is likely beyond the ~45-day accessible window. Returning 135 record(s)
collected so far.
```

**Callers should not assume the returned list covers the full requested date range.** If you request 180 days, you will receive roughly the last 45 days of records without an exception being raised.

### Fallback to Daily Endpoint

Some meters do not support the 15-minute (`amiEnergyUsages15Min`) GraphQL operation and return a GraphQL error response instead of data. When this happens on the first chunk, the method transparently falls back to a single full-range request against the standard daily endpoint (`amiEnergyUsages`). The fallback is automatic and invisible to the caller.

### Example

```python
from datetime import date, timedelta

date_to   = date.today()
date_from = date_to - timedelta(days=60)   # spans more than 45 days → auto-chunked

usages = await client.get_ami_energy_usages_15min(
    meter_number=meter["meterNumber"],
    premise_number=billing_account["premiseNumber"],
    service_point_number=meter["servicePointNumber"],
    meter_point_number=meter["meterPointNumber"],
    date_from=date_from,
    date_to=date_to,
    fuel_type=meter.get("fuelType"),   # "ELECTRIC" or "GAS"; controls chunk size
)
# usages covers only the accessible ~45-day window even though 60 days were requested
```

## Examples

```bash
uv run python examples/list-accounts.py   --username user@example.com --password secret
uv run python examples/account-info.py    --username user@example.com --password secret
uv run python examples/energy-usage.py   --username user@example.com --password secret
uv run python examples/interval-reads.py --username user@example.com --password secret
uv run python examples/ami-usage.py      --username user@example.com --password secret
uv run python examples/ami-usage.py      --username user@example.com --password secret --fuel-type ELECTRIC
uv run python examples/ami-usage.py      --username user@example.com --password secret --fuel-type GAS --days 30
```

## Development

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                # install dependencies
uv run pytest          # run tests
uv run ruff check .    # lint
uv run ruff format .   # format
uv run mypy src        # type-check
```
