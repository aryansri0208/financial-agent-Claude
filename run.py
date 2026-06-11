"""Entry point: run the full pipeline then launch the Streamlit dashboard."""
import asyncio
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)


async def main():
    print("=" * 60)
    print("  Portfolio Advisor — Multi-Agent Pipeline")
    print("=" * 60)

    skip_pipeline = "--dashboard-only" in sys.argv

    if not skip_pipeline:
        from orchestrator import run_pipeline
        await run_pipeline()
    else:
        print("Skipping pipeline (--dashboard-only flag set).")

    print("\nLaunching dashboard at http://localhost:8501 ...")
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run",
         os.path.join(ROOT, "dashboard.py"),
         "--server.headless", "false"],
        cwd=ROOT,
    )


if __name__ == "__main__":
    asyncio.run(main())
