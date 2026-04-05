# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for FritzBox Viewer
# Build with:  pyinstaller fritzbox_viewer.spec

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[
        # Jinja2 templates — must mirror the path used by app/main.py
        ('app/templates', 'app/templates'),
        # Standalone HTML documentation
        ('ANLEITUNG.html', '.'),
    ],
    hiddenimports=[
        # uvicorn uses dynamic imports for its protocol/loop backends
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'uvicorn.main',
        # APScheduler trigger/executor backends
        'apscheduler.triggers.interval',
        'apscheduler.triggers.date',
        'apscheduler.triggers.cron',
        'apscheduler.schedulers.background',
        'apscheduler.executors.default',
        'apscheduler.jobstores.memory',
        # SQLAlchemy SQLite dialect
        'sqlalchemy.dialects.sqlite',
        'sqlalchemy.dialects.sqlite.pysqlite',
        # fritzconnection internals
        'fritzconnection',
        'fritzconnection.core.fritzconnection',
        'fritzconnection.core.devices',
        'fritzconnection.core.soaper',
        'fritzconnection.core.logger',
        # anthropic / HTTP stack
        'anthropic',
        'httpx',
        'httpcore',
        'anyio',
        'anyio._backends._asyncio',
        # misc
        'multipart',
        'starlette.routing',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # strip test frameworks to reduce size
        'pytest',
        'unittest',
        'tkinter',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='FritzBox-Viewer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,   # keep console window so the startup banner is visible
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='FritzBox-Viewer',
)
