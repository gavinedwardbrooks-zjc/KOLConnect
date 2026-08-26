# SQLite Runtime Asset

KOLConnect Windows packages use `windows-x64/sqlite3.dll` to avoid the WAL-reset
defect affecting the Python 3.14.3 bundled SQLite 3.50.4 runtime.

- SQLite engine: 3.53.1
- Architecture: Windows x86-64
- Source runtime: bundled CPython 3.12.13 dependency runtime
- SHA256: `09435aa9de52c533f69fc3f6a23337e0276ad54567c808b80db64923c871257e`
- SQLite license: public domain

`scripts/check_sqlite_runtime.py` verifies both the engine policy and this digest.
Windows PyInstaller collection replaces its automatically discovered `sqlite3.dll`
with this pinned asset. macOS builds must supply a Python runtime whose bundled
SQLite independently passes the same engine-version gate.
