"""Convenience entry-point: python run.py [--debug]"""
import os
import sys

# ── Parse flags ────────────────────────────────────────────────────────────
debug = "--debug" in sys.argv or "-debug" in sys.argv
os.environ["FRITZ_DEBUG"] = "1" if debug else "0"

# ── Startup banner ──────────────────────────────────────────────────────────
print()
print("  ┌─────────────────────────────────────────┐")
print("  │         FritzBox Viewer                 │")
print("  │                                         │")
print("  │   Oberfläche:  http://localhost:8000    │")
print("  │   Admin:       http://localhost:8000/admin │")
if debug:
    print("  │                                         │")
    print("  │   Modus: DEBUG (ausführliche Ausgabe)   │")
print("  └─────────────────────────────────────────┘")
print()
print("  Mit Strg+C beenden.")
print()

# ── Start server ────────────────────────────────────────────────────────────
import uvicorn

uvicorn.run(
    "app.main:app",
    host="0.0.0.0",
    port=8000,
    reload=False,
    log_level="debug" if debug else "warning",
)
