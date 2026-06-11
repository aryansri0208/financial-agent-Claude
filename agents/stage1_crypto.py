"""Stage 1 — Crypto Agent: fetches CoinGecko data for major coins + trending"""
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

OUTFILE = os.path.join(ROOT, "data", "stage1", "crypto.json")

PROMPT = f"""
You are a data collection agent. Fetch cryptocurrency market data.

Steps:
1. Call get_crypto_data for each of: bitcoin, ethereum, solana, binancecoin, ripple, cardano, avalanche-2, chainlink.
2. Call get_crypto_trending to get today's top trending coins.
3. Combine into a JSON object: keys "coins" (dict by coin_id) and "trending".
4. Write to {OUTFILE} using the Write tool.
   Include a top-level "sources" array aggregating all sources.

Do not analyze. Just fetch and save.
"""


async def run() -> dict:
    output = {}
    async for message in query(
        prompt=PROMPT,
        options=ClaudeAgentOptions(
            tools=["Write", "mcp__finance__get_crypto_data"],
            allowed_tools=[
                "mcp__finance__get_crypto_data",
                "mcp__finance__get_crypto_trending",
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
                    print(f"[crypto] {block.text[:120]}")
        elif isinstance(message, ResultMessage):
            output["status"] = message.subtype
            output["cost"] = message.total_cost_usd
    return output


if __name__ == "__main__":
    asyncio.run(run())
