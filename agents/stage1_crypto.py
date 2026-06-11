"""Stage 1 — Crypto Agent: fetches CoinGecko data for major coins + trending directly (no SDK)"""
import asyncio
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

from mcp_server import _get_crypto_data, _get_crypto_trending

OUTFILE = os.path.join(ROOT, "data", "stage1", "crypto.json")

COINS = ["bitcoin", "ethereum", "solana", "binancecoin", "ripple", "cardano", "avalanche-2", "chainlink"]


async def run() -> dict:
    os.makedirs(os.path.dirname(OUTFILE), exist_ok=True)
    coins: dict = {}
    all_sources: list = []

    for coin_id in COINS:
        try:
            data = await _get_crypto_data(coin_id)
            all_sources.extend(data.pop("sources", []))
            coins[coin_id] = data
            print(f"[crypto] {coin_id} ✓")
        except Exception as e:
            print(f"[crypto] {coin_id} error: {e}")
            coins[coin_id] = {"coin_id": coin_id, "error": str(e)}

    trending = await _get_crypto_trending()
    all_sources.extend(trending.pop("sources", []))

    result = {"coins": coins, "trending": trending.get("trending_coins", trending), "sources": all_sources}
    with open(OUTFILE, "w") as f:
        json.dump(result, f)
    print(f"[crypto] Saved {len(coins)} coins + trending → {OUTFILE}")
    return {"status": "success", "cost": 0.0}


if __name__ == "__main__":
    asyncio.run(run())
