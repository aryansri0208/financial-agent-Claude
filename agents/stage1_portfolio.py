"""Stage 1 — Portfolio Agent: fetches Robinhood holdings directly (no SDK)"""
import asyncio
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

from mcp_server import _get_portfolio

OUTFILE = os.path.join(ROOT, "data", "stage1", "portfolio.json")


async def run() -> dict:
    os.makedirs(os.path.dirname(OUTFILE), exist_ok=True)
    data = await _get_portfolio()
    with open(OUTFILE, "w") as f:
        json.dump(data, f)
    print(f"[portfolio] Saved {len(data.get('holdings', []))} holdings → {OUTFILE}")
    return {"status": "success", "cost": 0.0}


if __name__ == "__main__":
    asyncio.run(run())
