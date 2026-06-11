"""Stage 1 — Fundamentals Agent: fetches Finnhub + analyst data directly (no SDK)"""
import asyncio
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

from mcp_server import _get_stock_fundamentals

OUTFILE = os.path.join(ROOT, "data", "stage1", "fundamentals.json")


async def run(tickers: list[str]) -> dict:
    os.makedirs(os.path.dirname(OUTFILE), exist_ok=True)
    result: dict = {}
    all_sources: list = []

    for ticker in tickers:
        try:
            fund = await _get_stock_fundamentals(ticker)
            all_sources.extend(fund.pop("sources", []))
        except Exception as e:
            print(f"[fundamentals] {ticker} error: {e}")
            fund = {"ticker": ticker}
        result[ticker] = fund
        print(f"[fundamentals] {ticker} ✓")

    result["sources"] = all_sources
    with open(OUTFILE, "w") as f:
        json.dump(result, f)
    print(f"[fundamentals] Saved {len(tickers)} tickers → {OUTFILE}")
    return {"status": "success", "cost": 0.0}


if __name__ == "__main__":
    asyncio.run(run(["AAPL", "MSFT", "NVDA"]))
