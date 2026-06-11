"""Stage 1 — Macro Agent: fetches FRED macro data and sector performance directly (no SDK)"""
import asyncio
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

from mcp_server import _get_macro_data, _get_sector_performance

OUTFILE = os.path.join(ROOT, "data", "stage1", "macro.json")


async def run() -> dict:
    os.makedirs(os.path.dirname(OUTFILE), exist_ok=True)
    macro = await _get_macro_data()
    sectors = await _get_sector_performance()

    sources = macro.pop("sources", []) + sectors.pop("sources", [])
    data = {"macro": macro, "sectors": sectors.get("sectors", sectors), "sources": sources}

    with open(OUTFILE, "w") as f:
        json.dump(data, f)
    print(f"[macro] Saved macro + {len(data['sectors'])} sectors → {OUTFILE}")
    return {"status": "success", "cost": 0.0}


if __name__ == "__main__":
    asyncio.run(run())
