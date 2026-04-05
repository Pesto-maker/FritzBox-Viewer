"""Convenience entry-point: python run.py [--debug]"""
import os
import sys

# Ensure the console can display UTF-8 (matters on Windows cmd/PowerShell)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Parse flags ────────────────────────────────────────────────────────────
debug = "--debug" in sys.argv or "-debug" in sys.argv
os.environ["FRITZ_DEBUG"] = "1" if debug else "0"

# ── Startup banner ──────────────────────────────────────────────────────────
print()
print("  +------------------------------------------+")
print("  |          FritzBox Viewer                 |")
print("  |                                          |")
print("  |  Oberflaeche:  http://localhost:8000     |")
print("  |  Admin:        http://localhost:8000/admin |")
if debug:
    print("  |                                          |")
    print("  |  Modus: DEBUG (ausfuehrliche Ausgabe)    |")
print("  +------------------------------------------+")
print()
print("  Mit Strg+C beenden.")
print()

# ── Start server ────────────────────────────────────────────────────────────
import uvicorn

if getattr(sys, "frozen", False):
    # PyInstaller exe: string-based import is unreliable when frozen
    from app.main import app as _app
    uvicorn.run(
        _app,
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="debug" if debug else "warning",
    )
else:
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="debug" if debug else "warning",
    )
