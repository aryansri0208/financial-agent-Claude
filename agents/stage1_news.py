"""Stage 1 — News & Sentiment Agent: fetches news and sentiment per ticker directly (no SDK)"""
import asyncio
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

from mcp_server import _get_news_and_sentiment

OUTFILE = os.path.join(ROOT, "data", "stage1", "news.json")


async def run(tickers: list[str]) -> dict:
    os.makedirs(os.path.dirname(OUTFILE), exist_ok=True)
    result: dict = {}
    all_sources: list = []

    for ticker in tickers:
        try:
            data = await _get_news_and_sentiment(ticker)
            all_sources.extend(data.pop("sources", []))
            result[ticker] = data
            print(f"[news] {ticker} ✓  sentiment={data.get('sentiment_score')}")
        except Exception as e:
            print(f"[news] {ticker} error: {e}")
            result[ticker] = {"ticker": ticker, "error": str(e)}

    result["sources"] = all_sources
    with open(OUTFILE, "w") as f:
        json.dump(result, f)
    print(f"[news] Saved {len(tickers)} tickers → {OUTFILE}")
    return {"status": "success", "cost": 0.0}


if __name__ == "__main__":
    asyncio.run(run(["AAPL", "MSFT", "NVDA"]))
