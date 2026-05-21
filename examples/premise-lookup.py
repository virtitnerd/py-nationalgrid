"""Example that looks up premise information by address.

get_premise() targets premise-cu-uwp-gql, which does not require authentication.
It returns the premise number and associated meter nodes (meterNumber, fuelType,
meterStatus) for a given address.
"""

import argparse
import asyncio
import json

import aiohttp

from py_nationalgrid import NationalGridClient, NationalGridConfig
from py_nationalgrid.helpers import create_cookie_jar


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Look up a National Grid premise by address")
    parser.add_argument("--street", required=True, help="Street address (e.g. '1 Example Road')")
    parser.add_argument("--city", required=True, help="City (e.g. Anytown)")
    parser.add_argument("--state", required=True, help="Two-letter state (e.g. NY)")
    parser.add_argument("--zip", required=True, help="ZIP code (e.g. 12345)")
    parser.add_argument("--apartment", default=None, help="Apartment or unit number")
    return parser.parse_args()


def pretty_print(data: object) -> None:
    print(json.dumps(data, indent=2, sort_keys=True))


async def main() -> None:
    args = parse_args()
    config = NationalGridConfig(username="", password="")
    cookie_jar = create_cookie_jar()

    async with aiohttp.ClientSession(cookie_jar=cookie_jar) as session:
        async with NationalGridClient(config=config, session=session) as client:
            print(
                f"Looking up: {args.street}, {args.city}, {args.state} {args.zip}"
                + (f" apt {args.apartment}" if args.apartment else "")
            )
            premises = await client.get_premise(
                city=args.city,
                state=args.state,
                street_name=args.street,
                zip_code=args.zip,
                apartment=args.apartment,
            )

            if not premises:
                print("No premises found for this address.")
                return

            print(f"\nFound {len(premises)} premise(s):")
            pretty_print(premises)  # type: ignore[arg-type]


if __name__ == "__main__":
    asyncio.run(main())
