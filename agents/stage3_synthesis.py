"""Stage 3 — Synthesis Agent: merges all Stage 2 outputs into final analysis_output.json.

Uses Anthropic Python SDK directly (no Claude Agent SDK) to avoid system-prompt overhead.
All data is pre-loaded in Python and injected into the prompt.
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
OUTFILE = os.path.join(ROOT, "analysis_output.json")


def _load(path: str) -> dict:
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return json.load(f)


def _build_context() -> str:
    portfolio = _load(os.path.join(S1, "portfolio.json"))
    macro_raw = _load(os.path.join(S1, "macro.json"))
    pa = _load(os.path.join(S2, "portfolio_analysis.json"))
    opps = _load(os.path.join(S2, "opportunities.json"))
    tech = _load(os.path.join(S2, "technicals.json"))

    # Portfolio totals
    holdings = portfolio.get("holdings", [])
    total_value = sum(h.get("current_value", 0) for h in holdings)
    total_pl = sum(h.get("unrealized_pl", 0) for h in holdings)
    total_cost = sum(h.get("avg_cost", 0) * h.get("quantity", 0) for h in holdings)
    total_pl_pct = round(total_pl / total_cost * 100, 2) if total_cost else 0

    # Compact portfolio_analysis
    hold_recs = [r for r in pa.get("holdings_analysis", []) if r.get("recommendation") in ("HOLD", "ADD")]
    sell_recs = [r for r in pa.get("holdings_analysis", []) if r.get("recommendation") in ("SELL", "REDUCE")]
    health = pa.get("portfolio_health_score", "?")
    rebalance = pa.get("rebalancing_suggestions", [])

    # Compact technicals
    tech_rows = []
    for t, d in tech.get("technicals", {}).items():
        tech_rows.append(f"{t}:{d.get('trend','?')}/rsi={d.get('rsi','?')}/entry={d.get('entry_range_low')}-{d.get('entry_range_high')}")

    # Compact opportunities
    stock_opps = opps.get("stocks", [])[:3]
    etf_opps = opps.get("etfs", [])[:2]
    crypto_opps = opps.get("crypto", [])[:2]
    watchlist = opps.get("watchlist", [])

    # Macro
    macro = macro_raw.get("macro", macro_raw)

    return (
        f"PORTFOLIO: total_value=${total_value:.0f}, total_pl=${total_pl:.0f} ({total_pl_pct}%), health={health}/10\n"
        f"MACRO: fed={macro.get('fed_funds_rate')}%, yield_inverted={macro.get('yield_curve_inverted')}, "
        f"cpi={macro.get('cpi_latest')}, unemployment={macro.get('unemployment_rate')}%\n"
        f"HOLD/ADD recs: {json.dumps([{'ticker':r['ticker'],'rec':r['recommendation'],'reason':r.get('reasoning','')[:80]} for r in hold_recs])}\n"
        f"SELL/REDUCE recs: {json.dumps([{'ticker':r['ticker'],'rec':r['recommendation'],'exit':r.get('exit_price_target'),'reason':r.get('reasoning','')[:80]} for r in sell_recs])}\n"
        f"TECHNICALS: {' | '.join(tech_rows)}\n"
        f"NEW STOCK OPPS: {json.dumps([{'ticker':o['ticker'],'conviction':o.get('conviction'),'entry':str(o.get('entry_price_low'))+'-'+str(o.get('entry_price_high')),'target':o.get('price_target_12m'),'reason':o.get('reasoning','')[:80]} for o in stock_opps])}\n"
        f"NEW ETF OPPS: {json.dumps([{'ticker':o['ticker'],'theme':o.get('theme',''),'reason':o.get('reasoning','')[:60]} for o in etf_opps])}\n"
        f"NEW CRYPTO OPPS: {json.dumps([{'symbol':o.get('symbol'),'entry':o.get('entry_price_usd'),'risk':o.get('risk_level'),'thesis':o.get('thesis','')[:60]} for o in crypto_opps])}\n"
        f"WATCHLIST: {watchlist}\n"
        f"REBALANCING SUGGESTIONS: {rebalance}"
    )


SYSTEM = "You are a portfolio synthesis agent. Respond ONLY with valid compact JSON, no markdown, no explanation."

SCHEMA = '{"portfolio_summary":{"total_value":0,"total_pl":0,"total_pl_pct":0,"health_score":7,"assessment":"..."},"holds":[{"ticker":"...","current_price":0,"pl_pct":0,"reason":"..."}],"sells":[{"ticker":"...","exit_price_target":0,"stop_loss":0,"reasoning":"..."}],"new_buys":[{"type":"stock|etf|crypto","ticker":"...","entry_price_low":0,"entry_price_high":0,"price_target_12m":0,"conviction":"HIGH","best_time_to_buy":"...","reasoning":"..."}],"watchlist":[{"ticker":"...","reason":"..."}],"macro_context":"...","strategy_summary":"...","sources":{"market_data":[],"macro":[],"crypto":[],"news":[],"filings":[]}}'


async def run() -> dict:
    context = _build_context()
    prompt = f"""Synthesize all analysis below into ONE unified investment report.

{context}

Produce the final report as compact JSON matching this schema:
{SCHEMA}

Keep reasoning fields to 1-2 sentences. Combine holds/sells/new_buys into clear action items."""

    print(f"[synthesis] Sending ~{len(prompt)//4} token prompt to Claude…")
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
    with open(OUTFILE, "w") as f:
        json.dump(data, f)

    input_tokens = response.usage.input_tokens
    output_tokens = response.usage.output_tokens
    cost = (input_tokens * 0.80 + output_tokens * 4.0) / 1_000_000
    print(f"[synthesis] ✓  {input_tokens} in / {output_tokens} out  cost=${cost:.4f}")
    return {"status": "success", "cost": cost}


if __name__ == "__main__":
    asyncio.run(run())
