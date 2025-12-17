#!/usr/bin/env bash
set -euo pipefail

EXPECTED_SUBSTRINGS=(
  "github.com/aturoa13699-lab/TURF-ENGINE"
  "github.com:aturoa13699-lab/TURF-ENGINE"
)

if [[ -n "${ALLOWED_REPO_SUBSTRINGS:-}" ]]; then
  # Append space-separated extra allowed substrings
  # shellcheck disable=SC2206
  EXTRA_SUBSTRINGS=(${ALLOWED_REPO_SUBSTRINGS})
  EXPECTED_SUBSTRINGS+=("${EXTRA_SUBSTRINGS[@]}")
fi

mapfile -t REMOTE_URLS < <(git remote -v | awk '{print $2}' | sort -u)

echo "Remotes:"
if [[ ${#REMOTE_URLS[@]} -eq 0 ]]; then
  echo "- <none>"
else
  for url in "${REMOTE_URLS[@]}"; do
    echo "- $url"
  done
fi

current_branch="$(git rev-parse --abbrev-ref HEAD)"
current_head="$(git rev-parse HEAD)"

echo "Branch: $current_branch"
echo "HEAD:   $current_head"

ok="false"
matched=""
for url in "${REMOTE_URLS[@]}"; do
  for expected in "${EXPECTED_SUBSTRINGS[@]}"; do
    if [[ -n "$url" && "$url" == *"$expected"* ]]; then
      ok="true"
      matched="$url"
      break 2
    fi
  done
done

if [[ "$ok" != "true" ]]; then
  echo "::error::No allowed repository remote detected."
  echo "::error::Expected at least one remote URL to contain:"
  for expected in "${EXPECTED_SUBSTRINGS[@]}"; do
    echo "::error:: - $expected"
  done
  echo "::error::Tip: set origin with 'git remote add origin https://github.com/aturoa13699-lab/TURF-ENGINE.git' or pass ALLOWED_REPO_SUBSTRINGS for forks."
  exit 1
fi

echo "✅ Repo identity OK (matched: $matched)"
