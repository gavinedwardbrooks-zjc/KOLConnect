# Test Runtime

Python tests run inside a disposable workspace-local runtime. The sandbox is
installed before unittest imports application or test modules, so APPDATA,
LOCALAPPDATA, XDG data, TEMP, locks, backups, settings, and workbook defaults do
not resolve to the user's KOLConnect data.

## Commands

Full Python regression:

```powershell
python scripts/run_python_tests.py
```

One Python test file:

```powershell
python scripts/run_python_tests.py --pattern "test_m7_2_api_contract.py" --verbosity 2
```

Unified frontend regression:

```powershell
node tests/run_extension_tests.js
```

## Safety Contract

Each run uses `.test_runtime/<suite>_<unique-id>/` with isolated `appdata`,
`localappdata`, `temp`, `KOLConnect/locks`, and `KOLConnect/backups` paths.
Production AppData and the production Creator workbook are rejected by focused
guards before mutation. Tests must create synthetic workbooks and settings and
must inject fake Feishu/mail configuration; they must not read real credentials.

Nested sandboxes restore the outer environment, and the outer sandbox restores
the original process environment. Set `KOLCONNECT_TEST_KEEP_RUNTIME=1` to retain
a run for debugging. Otherwise cleanup is best effort: a retained directory
after successful assertions is an environment cleanup warning, while an open
workbook or lock that breaks an assertion is a real failure.
