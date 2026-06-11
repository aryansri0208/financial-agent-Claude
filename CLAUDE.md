# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```bash
source .venv/bin/activate
```

Requires `ANTHROPIC_API_KEY` in `.env`.

## Running

```bash
python agent.py
```

## Architecture

This project experiments with the **Claude Agent SDK** (`claude_agent_sdk`) to run agentic loops — where Claude autonomously uses tools across multiple steps to complete a task.

**[agent.py](agent.py)** — Entry point. Defines async functions that call `query()` from the SDK, stream back `AssistantMessage` and `ResultMessage` events, and print Claude's reasoning and tool calls. Currently runs `claude_billing_research()`, with an earlier bug-fixing experiment commented out.

**[utils.py](utils.py)** — Standalone Python utility functions (no SDK dependency). Used as test input for agent tasks that involve reading/editing code.

### SDK Pattern

```python
async for message in query(prompt="...", options=ClaudeAgentOptions(...)):
    if isinstance(message, AssistantMessage): ...   # Claude's reasoning + tool calls
    elif isinstance(message, ResultMessage): ...    # Final outcome
```

`allowed_tools` controls which built-in tools Claude can use (`Read`, `Edit`, `Glob`, `WebSearch`, `Bash`, etc.). `permission_mode="bypassPermissions"` skips approval prompts.
