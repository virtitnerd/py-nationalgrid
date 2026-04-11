"""Example that fetches real-time meter interval reads."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timedelta

import aiohttp

from py_nationalgrid import NationalGridClient, NationalGridConfig
from py_nationalgrid.helpers import create_cookie_jar


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch interval reads")
    parser.add_argument("--username", required=True, help="National Grid username")
    parser.add_argument("--password", required=True, help="National Grid password")
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

            # Get the first meter's service point number
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
            service_point_number = meter["servicePointNumber"]
            print(f"Service point number: {service_point_number}")

            # Check if this is a smart meter with AMI capability
            has_smart_meter = meter.get("hasAmiSmartMeter", False)
            if not has_smart_meter:
                print()
                print("Warning: This meter does not have AMI smart meter capability.")
                print("Interval reads may not be available.")
            print()

            # Fetch interval reads from 24 hours ago
            print("Fetching interval reads...")
            start_datetime = datetime.now() - timedelta(hours=24)
            print(f"Start datetime: {start_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
            print()

            interval_reads = await client.get_interval_reads(
                premise_number=premise_number,
                service_point_number=service_point_number,
                start_datetime=start_datetime,
            )

            if not interval_reads:
                print("No interval reads returned.")
                return

            print(f"Received {len(interval_reads)} interval reads:")
            pretty_print(interval_reads)


if __name__ == "__main__":
    asyncio.run(main())
