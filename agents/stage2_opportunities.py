"""Stage 2 — Opportunity Agent: finds new stocks, ETFs, and crypto worth investing in"""
import asyncio
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
You are an investment opportunity research agent. Find new stocks, ETFs, and cryptos worth buying — beyond what the user holds.

Read these Stage 1 files:
- {S1}/portfolio.json — current holdings (do not recommend these as new buys)
- {S1}/macro.json — macro environment (rates, sectors in favor)
- {S1}/etf.json — ETF watchlist performance
- {S1}/crypto.json — crypto market data and trending coins
- {NEWS_FILE} — news sentiment for held tickers (bullish_pct, top headlines). Use bearish signals as contra-indicators and bullish signals as confirmation when identifying related opportunities.

Identify (keep lists SHORT to stay within output limits):
- STOCKS: 3-5 picks with ticker, entry_price_low, entry_price_high, price_target_12m, conviction (HIGH/MEDIUM/LOW), reasoning (1 sentence, reference news signal if relevant)
- ETFs: 2-3 picks with ticker, theme, reasoning (1 sentence)
- CRYPTO: 2-3 picks with coin_id, symbol, entry_price_usd, risk_level, thesis (1 sentence)
- watchlist: 3-5 ticker strings to monitor

Output COMPACT JSON and write to {S2}/opportunities.json using Write.
"""


async def run() -> dict:
    output = {}
    async for message in query(
        prompt=PROMPT,
        options=ClaudeAgentOptions(
            tools=["Read", "Write", "mcp__finance__get_stock_fundamentals"],
            allowed_tools=[
                "Read",
                "Write",
                "mcp__finance__get_stock_fundamentals",
                "mcp__finance__get_analyst_targets",
            ],
            permission_mode="bypassPermissions",
            mcp_servers=MCP_CONFIG,
            model="claude-haiku-4-5-20251001",
            cwd=ROOT,
            env={"ANTHROPIC_API_KEY": os.environ["ANTHROPIC_API_KEY"]},
        ),
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if hasattr(block, "text") and block.text:
                    print(f"[opportunities] {block.text[:120]}")
        elif isinstance(message, ResultMessage):
            output["status"] = message.subtype
            output["cost"] = message.total_cost_usd
    return output


if __name__ == "__main__":
    asyncio.run(run())
