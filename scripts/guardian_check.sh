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

if grep -RIn --line-number "<p>Mode:" .github/workflows; then
  echo "::error::Raw HTML line detected in workflow run blocks; wrap it in echo or remove (e.g., <p>Mode: ...</p>)."
  exit 1
fi

# --- Guard: reusable workflow Job summary must be echo-only (no stray HTML/text) ---
SUMMARY_WF=".github/workflows/site_build_and_deploy.yml"
if [[ -f "$SUMMARY_WF" ]]; then
  # Extract the Job summary step's run: | block (best-effort, text-based)
  summary_run="$(
    awk '
      $0 ~ /^[[:space:]]*-[[:space:]]name:[[:space:]]*Job summary[[:space:]]*$/ { in_step=1; next }
      in_step && $0 ~ /^[[:space:]]*run:[[:space:]]*\|[[:space:]]*$/ { in_run=1; next }
      in_run {
        # stop when next step starts
        if ($0 ~ /^[[:space:]]*-[[:space:]]name:/) exit
        print
      }
    ' "$SUMMARY_WF"
  )"

  if [[ -n "${summary_run//[[:space:]]/}" ]]; then
    bad_lines="$(
      printf '%s\n' "$summary_run" \
      | sed 's/^[[:space:]]*//' \
      | awk '
          NF==0 { next }
          $0 ~ /^#/ { next }
          $0 ~ /^echo[[:space:]]/ { next }
          $0 ~ /^[{}][[:space:]]*$/ { next }
          $0 ~ /^}[[:space:]]*>>/ { next }
          { print }
        '
    )"

    if [[ -n "$bad_lines" ]]; then
      echo "::error::Job summary run-block in $SUMMARY_WF contains non-echo lines (likely to break bash)."
      echo "::error::Only echo/comment/{ } lines are allowed in that run block."
      echo "$bad_lines" | sed 's/^/::error::  /'
      exit 1
    fi

    trimmed_summary=$(printf '%s\n' "$summary_run" | sed 's/^[[:space:]]*//')
    required_patterns=(
      "### TURF ENGINE Site Publish"
      "- Run date:"
      "- Mode:"
      "- Pages URL:"
    )

    missing_required=()
    for pat in "${required_patterns[@]}"; do
      if ! grep -Fq -- "$pat" <<<"$trimmed_summary"; then
        missing_required+=("$pat")
      fi
    done

    if [[ ${#missing_required[@]} -gt 0 ]]; then
      echo "::error::Job summary run-block in $SUMMARY_WF is missing required echo lines:" "${missing_required[*]}"
      exit 1
    fi
  fi
fi

ruby -ryaml -e '
  Dir[".github/workflows/*.y{a,}ml"].each do |f|
    data = YAML.load_file(f) || {}
    jobs = data.fetch("jobs", {})
    jobs.each do |job_name, job_data|
      steps = job_data.fetch("steps", []) || []
      steps.each do |step|
        run = step["run"]
        next unless run
        run.to_s.lines.each_with_index do |line, idx|
          if line.lstrip.start_with?("<p>")
            STDERR.puts "::error file=#{f},line=#{idx + 1}::Raw HTML line detected in run block (job: #{job_name}, step: #{step["name"] || "(unnamed)"}). Wrap it in echo or remove."
            exit 1
          end
        end
      end
    end
  end
'
