"""Stage 1 — Macro Agent: fetches FRED macro data and sector performance"""
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

OUTFILE = os.path.join(ROOT, "data", "stage1", "macro.json")

PROMPT = f"""
You are a data collection agent. Fetch macroeconomic and sector performance data.

Steps:
1. Call get_macro_data to get Fed funds rate, CPI, unemployment, and yield curve.
2. Call get_sector_performance to get sector ETF 1-month and YTD returns.
3. Combine into a single JSON object with keys "macro" and "sectors".
4. Write to {OUTFILE} using the Write tool.
   Include a top-level "sources" array aggregating all sources.

Do not analyze. Just fetch and save.
"""


async def run() -> dict:
    output = {}
    async for message in query(
        prompt=PROMPT,
        options=ClaudeAgentOptions(
            tools=["Write", "mcp__finance__get_macro_data"],
            allowed_tools=[
                "mcp__finance__get_macro_data",
                "mcp__finance__get_sector_performance",
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
                    print(f"[macro] {block.text[:120]}")
        elif isinstance(message, ResultMessage):
            output["status"] = message.subtype
            output["cost"] = message.total_cost_usd
    return output


if __name__ == "__main__":
    asyncio.run(run())
