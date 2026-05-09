import argparse
import asyncio
import logging

import aiohttp

from py_nationalgrid import NationalGridClient, NationalGridConfig
from py_nationalgrid.helpers import create_cookie_jar


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show payment history for each linked account")
    parser.add_argument("--username", required=True, help="National Grid username")
    parser.add_argument("--password", required=True, help="National Grid password")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser.parse_args()


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
            accounts = await client.get_linked_accounts()
            print(f"Found {len(accounts)} linked billing account(s):\n")

            for account in accounts:
                acct_id = account["billingAccountId"]
                print(f"Account: {acct_id}")

                payments = await client.get_payment_history(acct_id)
                if payments:
                    print(f"  Payment history ({len(payments)} record(s)):")
                    for payment in payments:
                        date = (
                            payment.get("paymentDate")
                            or payment.get("processedDate")
                            or "unknown date"
                        )
                        amount = payment.get("amount", 0)
                        status = payment.get("status") or "unknown"
                        method = payment.get("method") or ""
                        method_str = f"  via {method}" if method else ""
                        print(f"    {date}  ${amount:.2f}  {status}{method_str}")
                else:
                    print("  No payment history found.")
                print()


if __name__ == "__main__":
    asyncio.run(main())
