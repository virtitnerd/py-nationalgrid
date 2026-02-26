"""Example that fetches AMI energy usage data.

For electric meters in regions that have migrated to the new 15-minute interval
API (as of Feb 23, 2026), this example uses get_ami_energy_usages_15min().
For other meters (e.g. gas), get_ami_energy_usages() is used instead.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date, timedelta

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

            # Get the first meter's details
            meters = billing_account["meter"]["nodes"]
            if not meters:
                print("No meters found for this account.")
                return

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
            # AMI data has a delay, so end the range 3 days ago
            date_to = date.today() - timedelta(days=3)
            date_from = date_to - timedelta(days=args.days)
            fuel_type = meter.get("fuelType", "")
            print(f"Fuel type: {fuel_type}")
            print(f"Fetching AMI usage from {date_from} to {date_to}...")
            print()

            # National Grid migrated electric meters in some regions to a new
            # 15-minute interval API (amiEnergyUsages15Min) as of Feb 23, 2026.
            # Use get_ami_energy_usages_15min() for ELECTRIC meters and
            # get_ami_energy_usages() for other meter types (e.g. GAS).
            if fuel_type.upper() == "ELECTRIC":
                usages = await client.get_ami_energy_usages_15min(
                    meter_number=meter_number,
                    premise_number=premise_number,
                    service_point_number=service_point_number,
                    meter_point_number=meter_point_number,
                    date_from=date_from,
                    date_to=date_to,
                )
            else:
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
