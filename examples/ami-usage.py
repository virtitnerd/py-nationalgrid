"""Example that fetches AMI energy usage data.

get_ami_energy_usages() (NrtDailyUsage) is used for all meter types.  It
supports unrestricted date ranges and is the recommended primary method for
both ELECTRIC and GAS meters.

get_ami_energy_usages_15min() (NrtDailyUsage15Min) is also available for
callers that specifically want 15-minute interval data, but note that as of
early 2026 that endpoint caps responses at ~10,000 records regardless of the
requested date range.  Use it only when the cap is acceptable or has been
removed in a future API update.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timedelta, timezone

import aiohttp

from aionatgrid import NationalGridClient, NationalGridConfig
from aionatgrid.helpers import create_cookie_jar


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch AMI energy usage")
    parser.add_argument("--username", required=True, help="National Grid username")
    parser.add_argument("--password", required=True, help="National Grid password")
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of days to look back (default: 7)",
    )
    parser.add_argument(
        "--fuel-type",
        default=None,
        help="Filter meters by fuel type (e.g. ELECTRIC, GAS). Defaults to first meter found.",
    )
    return parser.parse_args()


def pretty_print(data: object) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


async def main() -> None:
    args = parse_args()
    config = NationalGridConfig(username=args.username, password=args.password)

    cookie_jar = create_cookie_jar()
    async with aiohttp.ClientSession(cookie_jar=cookie_jar) as session:
        async with NationalGridClient(config=config, session=session) as client:
            # First, get linked billing accounts to obtain an account number
            print("Fetching linked billing accounts...")
            accounts = await client.get_linked_accounts()

            if not accounts:
                print("No linked billing accounts found.")
                return

            account_number = accounts[0]["billingAccountId"]
            print(f"Using account: {account_number}")
            print()

            # Fetch billing account info to get premise and meter details
            print("Fetching billing account info...")
            billing_account = await client.get_billing_account(account_number)

            premise_number = billing_account["premiseNumber"]
            print(f"Premise number: {premise_number}")

            # Get the desired meter's details
            meters = billing_account["meter"]["nodes"]
            if not meters:
                print("No meters found for this account.")
                return

            fuel_type_filter = args.fuel_type.upper() if args.fuel_type else None
            if fuel_type_filter:
                meter = next(
                    (
                        m
                        for m in meters
                        if isinstance(v := m.get("fuelType"), str) and v.upper() == fuel_type_filter
                    ),
                    None,
                )
                if meter is None:
                    available = [
                        v if isinstance(v := m.get("fuelType"), str) else "unknown"
                        for m in meters
                    ]
                    print(f"No meter found with fuel type '{args.fuel_type}'.")
                    print(f"Available fuel types: {', '.join(available)}")
                    return
            else:
                meter = meters[0]
            meter_number = meter["meterNumber"]
            service_point_number = meter["servicePointNumber"]
            meter_point_number = meter["meterPointNumber"]
            print(f"Meter number: {meter_number}")
            print(f"Service point number: {service_point_number}")
            print(f"Meter point number: {meter_point_number}")

            # Check if this is a smart meter with AMI capability
            has_smart_meter = meter.get("hasAmiSmartMeter", False)
            if not has_smart_meter:
                print()
                print("Warning: This meter does not have AMI smart meter capability.")
                print("AMI energy usage data may not be available.")
            print()

            # Fetch AMI energy usage for the requested date range
            # API serves verified data through 00:00 UTC of the current UTC date
            date_to = datetime.now(timezone.utc).date()
            date_from = date_to - timedelta(days=args.days)
            fuel_type = meter.get("fuelType", "")
            print(f"Fuel type: {fuel_type}")
            print(f"Fetching AMI usage from {date_from} to {date_to}...")
            print()

            # Use the standard daily endpoint for all fuel types.  It supports
            # unrestricted date ranges and works for both ELECTRIC and GAS.
            # Switch to get_ami_energy_usages_15min() if you specifically need
            # 15-minute interval data and can accept its current ~10k record cap.
            usages = await client.get_ami_energy_usages(
                meter_number=meter_number,
                premise_number=premise_number,
                service_point_number=service_point_number,
                meter_point_number=meter_point_number,
                date_from=date_from,
                date_to=date_to,
            )

            if not usages:
                print("No AMI energy usage data returned.")
                return

            print(f"Received {len(usages)} usage records:")
            pretty_print(usages)


if __name__ == "__main__":
    asyncio.run(main())
