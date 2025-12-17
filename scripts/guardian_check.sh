#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

bash "$SCRIPT_DIR/verify_repo_identity.sh"

ruby -ryaml -e 'Dir[".github/workflows/*.y{a,}ml"].each { |f| YAML.load_file(f) }'

if grep -RIn --line-number -E 'python\s+cli/turf_cli\.py' .github/workflows; then
  echo "::error::File-mode CLI invocation found in workflows. Use: python -m cli.turf_cli"
  exit 1
fi

if grep -RIn --line-number -E 'if:.*secrets\.' .github/workflows; then
  echo "::error::secrets.* used inside if: expression. Map secrets to env and gate on env.*"
  exit 1
fi
