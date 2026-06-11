"""Stage 1 — Portfolio Agent: fetches Robinhood holdings and writes data/stage1/portfolio.json"""
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

OUTFILE = os.path.join(ROOT, "data", "stage1", "portfolio.json")

PROMPT = f"""
You are a data collection agent. Your only job is to fetch the user's Robinhood portfolio data.

Steps:
1. Call get_portfolio to retrieve all holdings.
2. Write the complete result as JSON to the file {OUTFILE} using the Write tool.
   The JSON must include a top-level "sources" array listing every data source used.

Do not perform any analysis. Just fetch and save.
"""


async def run() -> dict:
    output = {}
    async for message in query(
        prompt=PROMPT,
        options=ClaudeAgentOptions(
            tools=["Write", "mcp__finance__get_portfolio"],
            allowed_tools=["mcp__finance__get_portfolio", "Write"],
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
                    print(f"[portfolio] {block.text[:120]}")
        elif isinstance(message, ResultMessage):
            output["status"] = message.subtype
            output["cost"] = message.total_cost_usd
    return output


if __name__ == "__main__":
    asyncio.run(run())
