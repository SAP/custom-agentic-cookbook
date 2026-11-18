"""Read a configured revenue view without printing credentials or endpoint addresses."""

import argparse
import asyncio
import json
import math
import os
import sys

from datasphere import DatasphereReader, ReaderError


async def run(region: str):
    async with DatasphereReader(
        base_url=os.environ["BDC_ODATA_BASE_URL"],
        space=os.environ["BDC_SPACE"],
        view=os.environ["BDC_VIEW"],
        shape=os.environ["BDC_SHAPE"],
        token_url=os.environ["BDC_TOKEN_URL"],
        client_id=os.environ["BDC_CLIENT_ID"],
        client_secret=os.environ["BDC_CLIENT_SECRET"],
    ) as reader:
        rows = await reader.read(select=["Region", "Revenue"], equal={"Region": region}, limit=100)
    try:
        amounts = [float(row["Revenue"]) for row in rows]
        revenue = sum(amounts)
        if not all(math.isfinite(value) for value in [*amounts, revenue]):
            raise ValueError
    except (TypeError, ValueError, OverflowError):
        raise ReaderError("Datasphere returned invalid revenue values") from None
    print(
        json.dumps(
            {
                "region": region,
                "row_count": len(rows),
                "revenue": revenue,
            }
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", required=True)
    args = parser.parse_args()
    try:
        asyncio.run(run(args.region))
    except (ReaderError, ValueError, KeyError):
        print(
            "Datasphere example failed. Check configuration and the selected view.", file=sys.stderr
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
