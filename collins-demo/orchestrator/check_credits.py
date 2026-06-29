"""Print the Tripo credit balance in the terminal.

    cd collins-demo/orchestrator
    ../../.venv/Scripts/python.exe check_credits.py
"""
from config import config
import tripo

if not config.tripo_enabled:
    print("TRIPO_API_KEY not set in .env")
    raise SystemExit(1)

b = tripo.balance()
if "error" in b:
    print(f"Tripo balance unavailable: {b['error']}")
else:
    print(f"Tripo credits — balance: {b.get('balance')} | frozen: {b.get('frozen')}")
