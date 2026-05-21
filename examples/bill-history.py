"""Detailed billing history from the business portal.

Shows per-billing-period electric and gas data including the utility/supplier
charge breakdown, metered usage (kWh / therms), and average daily usage.
This is more granular than the standard get_bills() endpoint.

Usage:
    uv run python examples/bill-history.py --username user@example.com --password secret
"""

import argparse
import asyncio
import logging

import aiohttp

from py_nationalgrid import NationalGridClient, NationalGridConfig
from py_nationalgrid.helpers import create_cookie_jar


def parse_args() -> argparse.Namespace:
    """
    Parse CLI arguments for the bill-history example script.
    
    Supports the following command-line options:
      --username   National Grid username (required)
      --password   National Grid password (required)
      --account    Billing account number; if omitted, the first linked account is used
      --debug      Enable debug logging
    
    Returns:
        argparse.Namespace: Parsed arguments with attributes `username` (str), `password` (str),
        `account` (str or None), and `debug` (bool).
    """
    parser = argparse.ArgumentParser(description="Fetch detailed billing history")
    parser.add_argument("--username", required=True, help="National Grid username")
    parser.add_argument("--password", required=True, help="National Grid password")
    parser.add_argument(
        "--account",
        default=None,
        help="Billing account number (default: first linked account)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser.parse_args()


async def main() -> None:
    """
    Run the example CLI: parse credentials, create a client session,
    resolve a billing account, and fetch and print electric and/or gas
    billing history.

    Prints a brief account summary and, for each available fuel type, up
    to 12 billing periods showing period range, number of days, metered
    usage (kWh or therms), utility and supplier charges, total charges,
    and average daily usage. If no linked accounts are found or a fuel
    type has no history, prints an explanatory message and returns.
    """
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    config = NationalGridConfig(username=args.username, password=args.password)
    cookie_jar = create_cookie_jar()

    async with aiohttp.ClientSession(cookie_jar=cookie_jar) as session:
        async with NationalGridClient(config=config, session=session) as client:
            # Resolve account number and customer number
            if args.account:
                acct_id = args.account
                billing_account = await client.get_billing_account(acct_id)
            else:
                accounts = await client.get_linked_accounts()
                if not accounts:
                    print("No linked accounts found.")
                    return
                acct_id = accounts[0]["billingAccountId"]
                billing_account = await client.get_billing_account(acct_id)

            customer_number = str(billing_account["customerNumber"])
            fuel_types = [ft["type"] for ft in billing_account.get("fuelTypes", [])]
            print(f"Account: {acct_id}  customer: {customer_number}  fuels: {fuel_types}\n")

            # Electric bill history
            if "ELECTRIC" in fuel_types:
                print("Electric bill history:")
                electric = await client.get_electric_bill_history(acct_id, customer_number)
                if electric:
                    print(
                        f"  {'Period':<22} {'Days':>4} {'kWh':>6} {'Utility':>9}"
                        f" {'Supplier':>9} {'Total':>8} {'Avg/day':>7}"
                    )
                    print("  " + "-" * 72)
                    for r in electric[:12]:
                        period = f"{r['readFromDate'][:10]} → {r['readDate'][:10]}"
                        print(
                            f"  {period:<22} {r['readDays']:>4} {r['totalKwh']:>6.0f}"
                            f" ${r['utilityCharges']:>8.2f} ${r['supplierCharges']:>8.2f}"
                            f" ${r['totalCharges']:>7.2f} {r['avgDailyUsage']:>6.0f}"
                        )
                else:
                    print("  No electric bill history returned.")
                print()

            # Gas bill history
            if "GAS" in fuel_types:
                print("Gas bill history:")
                gas = await client.get_gas_bill_history(acct_id, customer_number)
                if gas:
                    print(
                        f"  {'Period':<22} {'Days':>4} {'Therms':>7} {'Utility':>9}"
                        f" {'Supplier':>9} {'Total':>8} {'Avg/day':>7}"
                    )
                    print("  " + "-" * 74)
                    for r in gas[:12]:
                        period = f"{r['readFromDate'][:10]} → {r['readDate'][:10]}"
                        print(
                            f"  {period:<22} {r['readDays']:>4} {r['totalTherms']:>7.0f}"
                            f" ${r['utilityCharges']:>8.2f} ${r['supplierCharges']:>8.2f}"
                            f" ${r['totalCharges']:>7.2f} {r['avgDailyUsage']:>6.0f}"
                        )
                else:
                    print("  No gas bill history returned.")


if __name__ == "__main__":
    asyncio.run(main())
