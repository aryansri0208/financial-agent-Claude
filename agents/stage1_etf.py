"""Stage 1 — ETF Agent: fetches ETF data for watchlist directly (no SDK)"""
import asyncio
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

from mcp_server import _get_etf_info

OUTFILE = os.path.join(ROOT, "data", "stage1", "etf.json")

WATCH_ETFS = ["SPY", "QQQ", "VTI", "IWM", "ARKK", "SOXX", "CQQQ", "GLD", "TLT", "SCHD", "VIG", "JEPI"]


async def run() -> dict:
    os.makedirs(os.path.dirname(OUTFILE), exist_ok=True)
    result: dict = {}
    all_sources: list = []

    for ticker in WATCH_ETFS:
        try:
            data = await _get_etf_info(ticker)
            all_sources.extend(data.pop("sources", []))
            result[ticker] = data
            print(f"[etf] {ticker} ✓")
        except Exception as e:
            print(f"[etf] {ticker} error: {e}")
            result[ticker] = {"ticker": ticker, "error": str(e)}

    result["sources"] = all_sources
    with open(OUTFILE, "w") as f:
        json.dump(result, f)
    print(f"[etf] Saved {len(WATCH_ETFS)} ETFs → {OUTFILE}")
    return {"status": "success", "cost": 0.0}


if __name__ == "__main__":
    asyncio.run(run())
