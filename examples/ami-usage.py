"""Example that fetches AMI energy usage data.

get_ami_energy_usages() is the primary method for AMI data. It tries the
standard amiEnergyUsages (NrtDailyUsage) endpoint first, which handles
unrestricted date ranges in a single request with no chunking required.

If NrtDailyUsage returns GraphQL errors or a 504 Gateway Timeout, the method
automatically falls back to get_ami_energy_usages_15min(), which targets
amiEnergyUsages15Min (NrtDailyUsage15Min) and splits the date range into
45-day chunks automatically.

Pass --15min to use the 15-minute endpoint directly (e.g. when you specifically
need 15-minute granularity rather than hourly/daily data).
"""

import argparse
import asyncio
import json
import logging
from datetime import UTC, datetime, timedelta

import aiohttp

from py_nationalgrid import NationalGridClient, NationalGridConfig
from py_nationalgrid.helpers import create_cookie_jar


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
    parser.add_argument(
        "--15min",
        dest="use_15min",
        action="store_true",
        help="Use the 15-minute endpoint directly (NrtDailyUsage15Min with chunking).",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser.parse_args()


def pretty_print(data: object) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


async def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
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
                        v if isinstance(v := m.get("fuelType"), str) else "unknown" for m in meters
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
            date_to = datetime.now(UTC).date()
            date_from = date_to - timedelta(days=args.days)
            fuel_type = meter.get("fuelType")
            fuel_type = fuel_type if isinstance(fuel_type, str) else ""
            print(f"Fuel type: {fuel_type}")
            print(f"Fetching AMI usage from {date_from} to {date_to}...")

            if args.use_15min:
                print("Endpoint: amiEnergyUsages15Min (NrtDailyUsage15Min, chunked)")
                print()
                usages = await client.get_ami_energy_usages_15min(
                    meter_number=meter_number,
                    premise_number=premise_number,
                    service_point_number=service_point_number,
                    meter_point_number=meter_point_number,
                    date_from=date_from,
                    date_to=date_to,
                    fuel_type=fuel_type,
                )
            else:
                print("Endpoint: amiEnergyUsages (NrtDailyUsage) with 15min fallback")
                print()
                usages = await client.get_ami_energy_usages(
                    meter_number=meter_number,
                    premise_number=premise_number,
                    service_point_number=service_point_number,
                    meter_point_number=meter_point_number,
                    date_from=date_from,
                    date_to=date_to,
                    fuel_type=fuel_type,
                )

            if not usages:
                print("No AMI energy usage data returned.")
                return

            print(f"Received {len(usages)} usage records:")
            pretty_print(usages)


if __name__ == "__main__":
    asyncio.run(main())
