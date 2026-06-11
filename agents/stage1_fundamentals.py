"""Stage 1 — Fundamentals Agent: fetches Finnhub + analyst data for all portfolio tickers"""
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


OUTFILE = os.path.join(ROOT, "data", "stage1", "fundamentals.json")


def build_prompt(tickers: list[str]) -> str:
    ticker_list = ", ".join(tickers)
    return f"""
You are a data collection agent. Fetch fundamental data for these tickers: {ticker_list}

Steps:
1. For each ticker call ONLY get_stock_fundamentals (one call per ticker). Skip insider/institutional calls.
2. Combine into a single compact JSON object keyed by ticker. Include ONLY these fields per ticker:
   name, sector, market_cap, pe_ratio, eps_ttm, beta, 52w_high, 52w_low, revenue_growth_yoy, profit_margin
3. Also call get_analyst_targets for each ticker. Add fields: target_mean, strong_buy, buy, hold, sell.
4. Add a top-level "sources" array listing the API sources used.
5. Write to {OUTFILE} using Write. Keep the JSON compact — no extra whitespace.

Fetch all tickers before writing anything. Do not analyze.
"""


async def run(tickers: list[str]) -> dict:
    output = {}
    async for message in query(
        prompt=build_prompt(tickers),
        options=ClaudeAgentOptions(
            tools=["Write", "mcp__finance__get_stock_fundamentals"],
            allowed_tools=[
                "mcp__finance__get_stock_fundamentals",
                "mcp__finance__get_analyst_targets",
                "mcp__finance__get_insider_trades",
                "mcp__finance__get_institutional_holdings",
                "Write",
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
                    print(f"[fundamentals] {block.text[:120]}")
        elif isinstance(message, ResultMessage):
            output["status"] = message.subtype
            output["cost"] = message.total_cost_usd
    return output


if __name__ == "__main__":
    asyncio.run(run(["AAPL", "MSFT", "NVDA"]))
