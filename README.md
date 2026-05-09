# py-nationalgrid

[![PyPI](https://img.shields.io/pypi/v/py-nationalgrid)](https://pypi.org/project/py-nationalgrid/)
[![CI](https://github.com/virtitnerd/py-nationalgrid/actions/workflows/ci.yml/badge.svg)](https://github.com/virtitnerd/py-nationalgrid/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/virtitnerd/py-nationalgrid/graph/badge.svg)](https://codecov.io/gh/virtitnerd/py-nationalgrid)

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
            acct_id = account["billingAccountId"]
            next_read = account["billingAccount"].get("nextSchedReadingDate")
            print(f"Account: {acct_id}  next read: {next_read}")

            # Single call: balance, autopay, paperless, scheduled payments, recent bills
            dashboard = await client.get_account_dashboard(acct_id)
            print(f"  Balance: ${dashboard['currentBalance']:.2f}")
            print(f"  Paperless: {dashboard['paperlessBilling']['status'] if dashboard['paperlessBilling'] else 'N/A'}")
            print(f"  Autopay: {'enrolled' if dashboard['isEnrolledInRecurringPay'] else 'not enrolled'}")
            for bill in dashboard["recentBills"]:
                print(
                    f"  {bill['statementDate']}  due {bill['dueDate']}  "
                    f"${bill['totalDueAmount']:.2f}"
                )

if __name__ == "__main__":
    asyncio.run(main())
```

## API Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `get_linked_accounts()` | `list[AccountLink]` | Linked billing account IDs and next scheduled meter read date |
| `get_billing_account(account_number)` | `BillingAccount` | Account details: region, address, fuel types, and meter info (including smart meter flags) |
| `get_bills(account_number)` | `list[Bill]` | Bill history, newest first — statement date, due date, charges, and status |
| `get_energy_usage_costs(...)` | `list[EnergyUsageCost]` | Daily energy costs for a billing period |
| `get_energy_usages(...)` | `list[EnergyUsage]` | Monthly historical usage data |
| `get_ami_energy_usages(...)` | `list[AmiEnergyUsage]` | **Primary AMI method.** Tries the daily `NrtDailyUsage` endpoint first (no chunking required). Falls back to `get_ami_energy_usages_15min()` automatically on GraphQL errors or 504. See below. |
| `get_ami_energy_usages_15min(...)` | `list[AmiEnergyUsage]` | AMI 15-minute interval data. Call directly only when you specifically need 15-minute granularity. Auto-chunks large ranges, falls back to daily on API errors, and handles the ~45-day hot storage limit gracefully. |
| `get_payment_history(account_number)` | `list[Payment]` | Payment history — payment date, amount, status, method, and error info |
| `get_account_dashboard(account_number)` | `AccountDashboard` | Account summary — balance, autopay/paperless status, scheduled payments, and recent bills in one call |
| `get_paperless_billing(account_number)` | `PaperlessBilling \| None` | Paperless billing enrollment status |
| `get_balanced_billing(account_number)` | `BalancedBilling \| None` | Budget billing plan status and monthly payment details |
| `get_payment_plans(account_number)` | `list[PaymentPlan]` | Active payment plans — installment amounts, counts, and status |
| `get_collection_arrangements(account_number)` | `list[CollectionArrangement]` | Collection arrangements — total due, installment schedule, and status |
| `get_meter_reading(account_number)` | `MeterReading \| None` | Current meter read eligibility and last submitted reading |
| `get_interval_reads(...)` | `list[IntervalRead]` | Real-time meter interval reads. Returns `[]` for meters with no interval data (e.g. GAS). |

All methods return typed results using TypedDict models.

## AMI Energy Usage

### Primary method: `get_ami_energy_usages()`

This is the recommended entry point for AMI data. It sends a single full-range request to the `NrtDailyUsage` (daily) endpoint — no chunking required. If that request returns GraphQL errors or a 504 Gateway Timeout, it automatically falls back to `get_ami_energy_usages_15min()` (with chunking) and returns whatever that produces.

```python
from datetime import date, timedelta

date_to   = date.today()
date_from = date_to - timedelta(days=60)

usages = await client.get_ami_energy_usages(
    meter_number=meter["meterNumber"],
    premise_number=billing_account["premiseNumber"],
    service_point_number=meter["servicePointNumber"],
    meter_point_number=meter["meterPointNumber"],
    date_from=date_from,
    date_to=date_to,
    fuel_type=meter.get("fuelType"),   # forwarded to the fallback path if triggered
)
```

### Explicit 15-minute method: `get_ami_energy_usages_15min()`

Use this directly only when you specifically need 15-minute interval granularity. It handles several API constraints automatically.

#### Chunking

The National Grid API imposes a hard limit of approximately 10,000 records per response, and the Azure Application Gateway enforces a backend timeout on large requests.

The method automatically splits any date range that exceeds 60 days into **60-day chunks** and concatenates the results. Chunks are requested **newest-first** to ensure the most recent data is always fetched before older chunks that may hit the cold-storage boundary. Each chunk is logged at `DEBUG` level.

If a 60-day chunk returns a 504 Gateway Timeout or a request timeout, the method automatically retries that chunk split into **45-day sub-chunks** before giving up:

```
WARNING amiEnergyUsages15Min: request failed on 60-day chunk 4/7 (2025-11-04 to 2026-01-02) — retrying as 45-day sub-chunks.
```

#### Hot Storage Window (~45 days)

National Grid's API only serves data from "hot" (immediately accessible) storage for approximately the last 45 days from today. Data older than that sits in cold/archive storage. Any query that touches cold storage will trigger a 504 Gateway Timeout or a request timeout.

**This is a server-side constraint.** There is no client-side configuration that can change it.

Because chunks are fetched newest-first, a failure on an older chunk does not discard the recent data already collected. When a 45-day sub-chunk also times out, the method logs a warning and returns whatever records were successfully retrieved:

```
WARNING amiEnergyUsages15Min: request failed on sub-chunk (2025-09-05 to 2025-10-19) —
data is likely beyond the ~45-day accessible window. Returning 19101 record(s)
collected so far.
```

**Callers should not assume the returned list covers the full requested date range.** If you request 365 days, you will receive roughly the last 45 days of records without an exception being raised.

#### Fallback to Daily Endpoint

Some meters do not support the 15-minute (`amiEnergyUsages15Min`) GraphQL operation and return a GraphQL error response instead of data. When this happens on the first chunk, the method transparently falls back to a single full-range request against the standard daily endpoint (`amiEnergyUsages`). The fallback is automatic and invisible to the caller.

#### Example

```python
from datetime import date, timedelta

date_to   = date.today()
date_from = date_to - timedelta(days=90)   # > 60 days → auto-chunked into 60-day windows

usages = await client.get_ami_energy_usages_15min(
    meter_number=meter["meterNumber"],
    premise_number=billing_account["premiseNumber"],
    service_point_number=meter["servicePointNumber"],
    meter_point_number=meter["meterPointNumber"],
    date_from=date_from,
    date_to=date_to,
    fuel_type=meter.get("fuelType"),   # "ELECTRIC" or "GAS"; controls chunk size
)
# usages may cover less than the full range if older data is beyond the ~45-day window
```

## Examples

```bash
uv run python examples/list-accounts.py      --username user@example.com --password secret
uv run python examples/account-info.py       --username user@example.com --password secret
uv run python examples/billing-info.py       --username user@example.com --password secret
uv run python examples/payment-history.py    --username user@example.com --password secret
uv run python examples/account-dashboard.py  --username user@example.com --password secret
uv run python examples/energy-usage.py       --username user@example.com --password secret
uv run python examples/interval-reads.py     --username user@example.com --password secret
uv run python examples/ami-usage.py          --username user@example.com --password secret
uv run python examples/ami-usage.py       --username user@example.com --password secret --fuel-type ELECTRIC
uv run python examples/ami-usage.py       --username user@example.com --password secret --fuel-type GAS --days 30
uv run python examples/ami-usage.py       --username user@example.com --password secret --15min
```

## Development

Requires Python 3.13+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                # install dependencies
uv run pytest          # run tests
uv run ruff check .    # lint
uv run ruff format .   # format
uv run mypy src        # type-check
```
