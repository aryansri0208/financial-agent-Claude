"""Stage 2 — Technical Analysis Agent.

Pre-fetches technical indicators in Python, then calls Anthropic API directly
(no Claude Agent SDK overhead) for reasoning/analysis.
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

from mcp_server import _get_technical_indicators

S1 = os.path.join(ROOT, "data", "stage1")
S2 = os.path.join(ROOT, "data", "stage2")
os.makedirs(S2, exist_ok=True)
OUTFILE = os.path.join(S2, "technicals.json")


def _get_tickers() -> list[str]:
    path = os.path.join(S1, "portfolio.json")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        data = json.load(f)
    return [h["ticker"] for h in data.get("holdings", [])]


SYSTEM = "You are a technical analysis agent. Respond ONLY with valid compact JSON, no markdown, no explanation."

SCHEMA = '{"technicals":{"TICKER":{"current_price":0,"trend":"UPTREND","sma_20":0,"sma_50":0,"sma_200":0,"rsi":50,"rsi_signal":"neutral","macd_bullish":true,"support":0,"resistance":0,"entry_range_low":0,"entry_range_high":0,"stop_loss":0,"technical_summary":"..."}},"sources":[]}'


async def run() -> dict:
    tickers = _get_tickers()

    # Pre-fetch all technical data in Python
    tech_data: dict = {}
    all_sources: list = []
    for ticker in tickers:
        try:
            data = await _get_technical_indicators(ticker)
            all_sources.extend(data.pop("sources", []))
            tech_data[ticker] = data
            print(f"[technicals] {ticker} ✓  rsi={data.get('rsi_14')}  macd_bull={data.get('macd_bullish_cross')}")
        except Exception as e:
            print(f"[technicals] {ticker} error: {e}")
            tech_data[ticker] = {"ticker": ticker, "error": str(e)}

    # Build compact prompt
    rows = []
    for t, d in tech_data.items():
        if "error" in d:
            continue
        rows.append(
            f"{t}: price={d.get('current_price')}, sma20={d.get('sma_20')}, sma50={d.get('sma_50')}, "
            f"sma200={d.get('sma_200')}, above_sma20={d.get('above_sma20')}, above_sma50={d.get('above_sma50')}, "
            f"above_sma200={d.get('above_sma200')}, rsi={d.get('rsi_14')}, rsi_signal={d.get('rsi_signal')}, "
            f"macd={d.get('macd')}, macd_signal={d.get('macd_signal')}, macd_bullish={d.get('macd_bullish_cross')}"
        )

    prompt = f"""Analyze the technical data below for each ticker and provide entry/exit levels.

TECHNICAL DATA:
{chr(10).join(rows)}

For EACH ticker determine:
- trend: UPTREND / DOWNTREND / SIDEWAYS (based on price vs SMAs)
- rsi_signal: overbought / oversold / neutral
- macd_bullish: true/false
- support: estimated support level (below current price)
- resistance: estimated resistance level (above current price)
- entry_range_low / entry_range_high: ideal buy zone
- stop_loss: stop loss price
- technical_summary: 1 sentence

Output ONLY compact JSON matching this schema: {SCHEMA}"""

    print(f"[technicals] Sending ~{len(prompt)//4} token prompt to Claude…")
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    data = json.loads(raw)
    data["sources"] = all_sources
    with open(OUTFILE, "w") as f:
        json.dump(data, f)

    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    cost = (input_tokens * 0.80 + output_tokens * 4.0) / 1_000_000
    print(f"[technicals] ✓  {input_tokens} in / {output_tokens} out  cost=${cost:.4f}")
    return {"status": "success", "cost": cost}


if __name__ == "__main__":
    asyncio.run(run())
