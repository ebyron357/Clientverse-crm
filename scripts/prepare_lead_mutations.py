"""Owner-authorized preparation only; does not enable tenants or rewrite lead records."""

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from motor.motor_asyncio import AsyncIOMotorClient

from lead_mutations import prepare, require_ready


async def main(apply):
    client = AsyncIOMotorClient(os.environ["MONGO_URL"], serverSelectionTimeoutMS=5000)
    try:
        db = client[os.environ["DB_NAME"]]
        if apply:
            await prepare(db)
        await require_ready(db)
        print("Replica-set topology and unique receipt index verified. Tenant rollout remains a separate owner action.")
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Create the additive unique receipt index")
    asyncio.run(main(parser.parse_args().apply))
