"""Stage 1 — ETF Agent: fetches data for a curated list of notable ETFs"""
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

# Broad market, thematic, and factor ETFs worth monitoring
WATCH_ETFS = ["SPY", "QQQ", "VTI", "IWM", "ARKK", "SOXX", "CQQQ", "GLD", "TLT", "SCHD", "VIG", "JEPI"]

OUTFILE = os.path.join(ROOT, "data", "stage1", "etf.json")

PROMPT = f"""
You are a data collection agent. Fetch ETF data for this watchlist: {", ".join(WATCH_ETFS)}.

Steps:
1. For each ETF ticker call get_etf_info.
2. Combine results into a JSON object keyed by ticker.
3. Write to {OUTFILE} using the Write tool.
   Include a top-level "sources" array aggregating all sources.

Do not analyze. Just fetch and save.
"""


async def run() -> dict:
    output = {}
    async for message in query(
        prompt=PROMPT,
        options=ClaudeAgentOptions(
            tools=["Write", "mcp__finance__get_etf_info"],
            allowed_tools=["mcp__finance__get_etf_info", "Write"],
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
                    print(f"[etf] {block.text[:120]}")
        elif isinstance(message, ResultMessage):
            output["status"] = message.subtype
            output["cost"] = message.total_cost_usd
    return output


if __name__ == "__main__":
    asyncio.run(run())
