"""Stage 2 — Technical Analysis Agent: calculates indicators, identifies entry/exit levels"""
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

PROMPT = f"""
You are a technical analysis agent. Fetch indicators for portfolio holdings only (skip opportunity picks to stay within token limits).

Steps:
1. Read {S1}/portfolio.json to get current holdings tickers.
2. For EACH holding ticker call get_technical_indicators (skip get_price_history to save tokens).
3. For each ticker determine: trend (UPTREND/DOWNTREND/SIDEWAYS), rsi_signal, macd_bullish, support, resistance, entry_range_low, entry_range_high, stop_loss.
4. Write COMPACT JSON to {S2}/technicals.json using Write.

Output format (compact, no extra whitespace):
{{"technicals":{{"TICKER":{{"current_price":0,"trend":"UPTREND","sma_20":0,"sma_50":0,"sma_200":0,"rsi":50,"rsi_signal":"neutral","macd_bullish":true,"support":0,"resistance":0,"entry_range_low":0,"entry_range_high":0,"stop_loss":0,"technical_summary":"..."}}}},"sources":[]}}
"""


async def run() -> dict:
    output = {}
    async for message in query(
        prompt=PROMPT,
        options=ClaudeAgentOptions(
            tools=["Read", "Write", "mcp__finance__get_technical_indicators"],
            allowed_tools=[
                "Read",
                "Write",
                "mcp__finance__get_technical_indicators",
                "mcp__finance__get_price_history",
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
                    print(f"[technicals] {block.text[:120]}")
        elif isinstance(message, ResultMessage):
            output["status"] = message.subtype
            output["cost"] = message.total_cost_usd
    return output


if __name__ == "__main__":
    asyncio.run(run())
