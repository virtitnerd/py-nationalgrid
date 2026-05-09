import argparse
import asyncio
import logging

import aiohttp

from py_nationalgrid import NationalGridClient, NationalGridConfig
from py_nationalgrid.helpers import create_cookie_jar


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show account dashboard for each linked account")
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
                ba = account.get("billingAccount") or {}
                next_read = ba.get("nextSchedReadingDate")
                print(f"Account: {acct_id}  (next read: {next_read or 'N/A'})")

                dashboard = await client.get_account_dashboard(acct_id)

                print(f"  Balance: ${dashboard['currentBalance']:.2f}")
                autopay = "enrolled" if dashboard["isEnrolledInRecurringPay"] else "not enrolled"
                print(f"  Autopay: {autopay}")
                on_plan = "yes" if dashboard["isEnrolledInPaymentPlan"] else "no"
                print(f"  Payment plan: {on_plan}")

                pb = dashboard.get("paperlessBilling")
                print(f"  Paperless: {pb['status'] if pb else 'N/A'}")

                bb = dashboard.get("balancedBilling")
                if bb and bb.get("status"):
                    monthly = bb.get("currentMonthlyPayment") or 0
                    print(f"  Budget billing: {bb['status']}  ${monthly:.2f}/mo")

                rp = dashboard.get("recurringPayDetails")
                if rp and rp.get("status"):
                    print(f"  Recurring pay: {rp['status']}  {rp.get('amountType') or ''}")

                scheduled = dashboard.get("scheduledPayments") or []
                if scheduled:
                    print(f"  Scheduled payments ({len(scheduled)}):")
                    for pmt in scheduled:
                        amt = pmt.get("amount") or 0
                        date = pmt.get("paymentDate") or "unknown"
                        status = pmt.get("status") or ""
                        print(f"    {date}  ${amt:.2f}  {status}")

                bills = dashboard.get("recentBills") or []
                if bills:
                    print(f"  Recent bills ({len(bills)}):")
                    for bill in bills:
                        print(
                            f"    {bill['statementDate']}  due {bill['dueDate']}  "
                            f"${bill['totalDueAmount']:.2f}"
                        )

                print()


if __name__ == "__main__":
    asyncio.run(main())
