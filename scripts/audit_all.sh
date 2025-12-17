#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

bash "$SCRIPT_DIR/verify_repo_identity.sh"

PYTHONPATH=. python -m pytest -q
PYTHONPATH=. python -m cli.turf_cli demo-run --date 2025-12-15 --out /tmp/turf_cards

bash "$SCRIPT_DIR/guardian_check.sh"
