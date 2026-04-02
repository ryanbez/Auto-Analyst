#!/usr/bin/env bash
set -euo pipefail

python -m py_compile app_marimo.py

echo "[OK] Python syntax compile passed"

if command -v marimo >/dev/null 2>&1; then
  timeout 12s marimo run app_marimo.py >/tmp/marimo_smoke.log 2>&1 || true
  if rg -n "Traceback|Error|Exception" /tmp/marimo_smoke.log >/dev/null 2>&1; then
    echo "[WARN] marimo startup log contains error-like output"
    cat /tmp/marimo_smoke.log
    exit 1
  fi
  echo "[OK] marimo startup smoke test executed (timeout expected)"
else
  echo "[WARN] marimo command not found; install with: pip install -r requirements-marimo.txt"
fi
