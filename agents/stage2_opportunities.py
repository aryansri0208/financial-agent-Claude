"""Stage 2 — Opportunity Agent: finds new stocks, ETFs, and crypto worth investing in.

Reads Stage 1 data in Python, builds a compact context, then calls Anthropic API
directly (no Claude Agent SDK overhead) for reasoning.
"""
import asyncio
import json
import os
import re
import sys

import anthropic

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

S1 = os.path.join(ROOT, "data", "stage1")
S2 = os.path.join(ROOT, "data", "stage2")
os.makedirs(S2, exist_ok=True)
OUTFILE = os.path.join(S2, "opportunities.json")


def _load(name: str) -> dict:
    path = os.path.join(S1, name)
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def _build_context() -> str:
    portfolio = _load("portfolio.json")
    macro_raw = _load("macro.json")
    etf = _load("etf.json")
    crypto = _load("crypto.json")
    news = _load("news.json")

    held = [h["ticker"] for h in portfolio.get("holdings", [])]

    macro = macro_raw.get("macro", macro_raw)
    sectors = macro_raw.get("sectors", [])
    top_sectors = sorted(
        [s for s in sectors if s.get("1m_return_pct") is not None],
        key=lambda s: s["1m_return_pct"], reverse=True
    )[:3]
    bottom_sectors = sorted(
        [s for s in sectors if s.get("1m_return_pct") is not None],
        key=lambda s: s["1m_return_pct"]
    )[:2]

    # ETF summary (top 5 by 1y return)
    etf_rows = []
    for ticker, d in etf.items():
        if ticker == "sources" or not isinstance(d, dict):
            continue
        etf_rows.append((ticker, d.get("1y_return_pct"), d.get("name", "")))
    etf_rows.sort(key=lambda x: x[1] or 0, reverse=True)
    etf_summary = ", ".join(f"{t}({r}%)" for t, r, _ in etf_rows[:5] if r is not None)

    # Crypto summary (top movers by 7d)
    coins = crypto.get("coins", {})
    crypto_rows = [(cid, d.get("7d_change_pct"), d.get("symbol", "")) for cid, d in coins.items() if isinstance(d, dict) and d.get("7d_change_pct")]
    crypto_rows.sort(key=lambda x: x[1] or 0, reverse=True)
    crypto_summary = ", ".join(f"{sym}({chg:.1f}%7d)" for _, chg, sym in crypto_rows[:4])

    trending = crypto.get("trending", [])
    trending_names = ", ".join(c.get("symbol", c.get("name", "")) for c in trending[:5])

    # News sentiment summary
    news_bullish = [(t, d.get("sentiment_score", 0)) for t, d in news.items()
                    if isinstance(d, dict) and d.get("sentiment_score") is not None]
    news_bullish.sort(key=lambda x: x[1], reverse=True)
    news_summary = ", ".join(f"{t}({s:.2f})" for t, s in news_bullish[:3])

    return (
        f"CURRENT HOLDINGS (exclude from new buys): {', '.join(held)}\n"
        f"MACRO: fed={macro.get('fed_funds_rate')}%, cpi={macro.get('cpi_latest')}, "
        f"yield_inverted={macro.get('yield_curve_inverted')}, "
        f"top_sectors={[s['sector'] for s in top_sectors]}, "
        f"weak_sectors={[s['sector'] for s in bottom_sectors]}\n"
        f"ETF PERFORMANCE (1y): {etf_summary}\n"
        f"CRYPTO 7d movers: {crypto_summary}  trending: {trending_names}\n"
        f"NEWS SENTIMENT (held, most bullish): {news_summary}"
    )


SYSTEM = "You are an investment opportunity research agent. Respond ONLY with valid compact JSON, no markdown, no explanation."

SCHEMA = '{"stocks":[{"ticker":"...","entry_price_low":0,"entry_price_high":0,"price_target_12m":0,"conviction":"HIGH|MEDIUM|LOW","reasoning":"..."}],"etfs":[{"ticker":"...","theme":"...","reasoning":"..."}],"crypto":[{"coin_id":"...","symbol":"...","entry_price_usd":0,"risk_level":"HIGH|MEDIUM|LOW","thesis":"..."}],"watchlist":[],"sources":[]}'


async def run() -> dict:
    context = _build_context()
    prompt = f"""Find new investment opportunities based on the data below. Do NOT recommend currently held tickers.

{context}

Identify (keep lists SHORT):
- STOCKS: 3-5 picks not in current holdings
- ETFs: 2-3 picks
- CRYPTO: 2-3 picks
- watchlist: 3-5 tickers to monitor

Output ONLY compact JSON matching this schema: {SCHEMA}"""

    print(f"[opportunities] Sending ~{len(prompt)//4} token prompt to Claude…")
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    data = json.loads(raw)
    with open(OUTFILE, "w") as f:
        json.dump(data, f)

    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    cost = (input_tokens * 0.80 + output_tokens * 4.0) / 1_000_000
    print(f"[opportunities] ✓  {input_tokens} in / {output_tokens} out  cost=${cost:.4f}")
    return {"status": "success", "cost": cost}


if __name__ == "__main__":
    asyncio.run(run())
