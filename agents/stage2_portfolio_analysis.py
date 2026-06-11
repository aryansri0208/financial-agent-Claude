"""Stage 2 — Portfolio Analysis Agent.

Uses the Anthropic Python SDK directly (no Claude Agent SDK) to avoid the ~9K token
system-prompt overhead that the Agent SDK injects into every call.
Data is pre-processed in Python; Claude only reasons and returns JSON.
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
OUTFILE = os.path.join(S2, "portfolio_analysis.json")


def _load(name: str) -> dict:
    path = os.path.join(S1, name)
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def _build_context() -> str:
    portfolio = _load("portfolio.json")
    fundamentals = _load("fundamentals.json")
    news = _load("news.json")
    macro_raw = _load("macro.json")

    macro = macro_raw.get("macro", macro_raw)
    sectors = macro_raw.get("sectors", [])
    top_sectors = sorted(
        [s for s in sectors if s.get("1m_return_pct") is not None],
        key=lambda s: s["1m_return_pct"], reverse=True
    )[:3]
    macro_str = (
        f"fed_rate={macro.get('fed_funds_rate')}%  "
        f"cpi={macro.get('cpi_latest')}  "
        f"unemployment={macro.get('unemployment_rate')}%  "
        f"yield_curve_inverted={macro.get('yield_curve_inverted')}  "
        f"top_sectors={[s['sector'] for s in top_sectors]}"
    )

    rows = []
    for h in portfolio.get("holdings", []):
        t = h["ticker"]
        f = fundamentals.get(t, {})
        n = news.get(t, {})
        top_headline = ""
        articles = n.get("articles", [])
        if articles:
            top_headline = articles[0].get("headline", "")[:120]
        rows.append(
            f"{t}: qty={h.get('quantity')}, avg_cost=${h.get('avg_cost')}, "
            f"price=${h.get('current_price')}, pl_pct={h.get('unrealized_pl_pct')}%, "
            f"pe={f.get('pe_ratio')}, beta={f.get('beta')}, margin={f.get('profit_margin')}, "
            f"52w_high={f.get('52w_high')}, 52w_low={f.get('52w_low')}, "
            f"sentiment={n.get('sentiment_score')}, bullish={n.get('bullish_pct')}%, "
            f"headline=\"{top_headline}\""
        )

    return f"MACRO: {macro_str}\n\nHOLDINGS:\n" + "\n".join(rows)


SYSTEM = "You are a portfolio analysis agent. Respond ONLY with valid compact JSON, no markdown, no explanation."

SCHEMA = '{"holdings_analysis":[{"ticker":"...","recommendation":"HOLD|ADD|REDUCE|SELL","reasoning":"...","exit_price_target":null,"entry_price_target":null,"risk_flags":[]}],"portfolio_health_score":7,"sector_concentration_risks":[],"rebalancing_suggestions":[],"sources":[]}'


def _build_prompt() -> str:
    context = _build_context()
    return f"""Analyze the holdings below and give actionable recommendations.

{context}

For EACH ticker produce:
- recommendation: HOLD / ADD / REDUCE / SELL
- reasoning: 2-3 sentences citing fundamentals, macro context, AND news sentiment
- exit_price_target: number if SELL/REDUCE, else null
- entry_price_target: number if ADD, else null
- risk_flags: list of strings

Also produce:
- portfolio_health_score: 1-10
- sector_concentration_risks: list of strings
- rebalancing_suggestions: list of strings
- sources: []

Output ONLY compact JSON matching this schema: {SCHEMA}"""


async def run() -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt = _build_prompt()
    print(f"[portfolio_analysis] Sending ~{len(prompt)//4} token prompt to Claude…")

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    # Strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    data = json.loads(raw)
    with open(OUTFILE, "w") as f:
        json.dump(data, f)

    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    cost = (input_tokens * 0.80 + output_tokens * 4.0) / 1_000_000
    print(f"[portfolio_analysis] ✓  {input_tokens} in / {output_tokens} out  cost=${cost:.4f}")
    return {"status": "success", "cost": cost}


if __name__ == "__main__":
    asyncio.run(run())
