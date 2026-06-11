"""Stage 2 — Portfolio Analysis Agent: analyzes current holdings and gives hold/add/reduce/sell recs"""
import asyncio
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dotenv import load_dotenv
load_dotenv(os.path.join(ROOT, ".env"))

from claude_agent_sdk import query, ClaudeAgentOptions, AssistantMessage, ResultMessage

MCP_CONFIG = {
    "finance": {
        "type": "stdio",
        "command": sys.executable,
        "args": [os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mcp_server.py")],
    }
}

S1 = os.path.join(ROOT, "data", "stage1")
S2 = os.path.join(ROOT, "data", "stage2")
os.makedirs(S2, exist_ok=True)

NEWS_FILE = os.path.join(S1, "news.json")

PROMPT = f"""
You are a portfolio analysis agent. Analyze the user's current Robinhood holdings and provide actionable recommendations.

Read these Stage 1 data files:
- {S1}/portfolio.json  — current holdings, quantities, avg cost, current value, P&L
- {S1}/fundamentals.json — P/E, EPS, analyst targets
- {S1}/macro.json — macro environment (rates, inflation, yield curve, sector performance)
- {NEWS_FILE} — news sentiment per ticker (bullish_pct, bearish_pct, top headlines). Use this to strengthen or temper your recommendation: bearish news on a holding raises risk, bullish news supports ADD.

Your analysis must cover for EACH holding:
1. Recommendation: HOLD / ADD / REDUCE / SELL
2. Reasoning (2-3 sentences): cite fundamentals, macro context, AND news sentiment if available
3. If SELL or REDUCE: specify a target exit price and the key risk
4. If ADD: specify a target entry price and the catalyst
5. Risk flags: overconcentration, sector correlation, macro sensitivity, negative news signal

Also assess the portfolio as a whole:
- Sector concentration risks
- Overall portfolio health score (1-10)
- Suggested rebalancing actions

Output a COMPACT JSON object (no extra whitespace) and write it to {S2}/portfolio_analysis.json using the Write tool.
Schema:
{{"holdings_analysis":[{{"ticker":"...","recommendation":"HOLD|ADD|REDUCE|SELL","reasoning":"...","exit_price_target":null,"entry_price_target":null,"risk_flags":[]}}],"portfolio_health_score":7,"sector_concentration_risks":[],"rebalancing_suggestions":[],"sources":[]}}
"""


async def run() -> dict:
    output = {}
    async for message in query(
        prompt=PROMPT,
        options=ClaudeAgentOptions(
            tools=["Read", "Write"],
            allowed_tools=["Read", "Write"],
            permission_mode="bypassPermissions",
            model="claude-haiku-4-5-20251001",
            cwd=ROOT,
            env={"ANTHROPIC_API_KEY": os.environ["ANTHROPIC_API_KEY"]},
        ),
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if hasattr(block, "text") and block.text:
                    print(f"[portfolio_analysis] {block.text[:120]}")
        elif isinstance(message, ResultMessage):
            output["status"] = message.subtype
            output["cost"] = message.total_cost_usd
    return output


if __name__ == "__main__":
    asyncio.run(run())
