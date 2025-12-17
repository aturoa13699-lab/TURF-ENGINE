#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT_DIR="out/diagnostics"
mkdir -p "$OUT_DIR"

# Verify repo identity before any work
bash scripts/verify_repo_identity.sh

echo "Validating workflow YAML..."
if command -v ruby >/dev/null 2>&1; then
  ruby -ryaml -e 'Dir[".github/workflows/*.y{a,}ml"].each { |f| YAML.load_file(f) }'
  export REPO_INV_HAVE_RUBY="1"
else
  echo "WARN: ruby not available; skipping workflow YAML parse validation"
  export REPO_INV_HAVE_RUBY="0"
fi

echo "Collecting guardrail grep results..."
file_mode_hits_path="$OUT_DIR/file_mode_cli_hits.txt"
secrets_if_hits_path="$OUT_DIR/secrets_in_if_hits.txt"

grep -RIn --line-number -E 'python\s+cli/turf_cli\.py' .github/workflows >"$file_mode_hits_path" || true
grep -RIn --line-number -E 'if:.*secrets\.' .github/workflows >"$secrets_if_hits_path" || true

echo "Capturing file listings..."
git ls-files >"$OUT_DIR/git_files.txt"

TREE_TOOL="tree"
TREE_PATH="$OUT_DIR/tree.txt"
if command -v tree >/dev/null 2>&1; then
  tree -a -I '.git|__pycache__|.pytest_cache|out|site_out|public|dist|node_modules|*.egg-info' >"$TREE_PATH"
else
  TREE_TOOL="find"
  find . \
    -path './.git' -prune -o \
    -path './out' -prune -o \
    -path './site_out' -prune -o \
    -path './public' -prune -o \
    -path './dist' -prune -o \
    -path './node_modules' -prune -o \
    -path './__pycache__' -prune -o \
    -path './.pytest_cache' -prune -o \
    -path '*/*.egg-info' -prune -o \
    -print | sed 's#^\./##' | sort >"$TREE_PATH"
fi

export REPO_INV_OUT_DIR="$OUT_DIR"
export REPO_INV_TREE_TOOL="$TREE_TOOL"
export REPO_INV_GENERATED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

# Identify a diff base for changed file inventory (best effort, non-fatal)
BASE_REF=""
if git rev-parse --verify origin/main >/dev/null 2>&1; then
  BASE_REF="origin/main"
elif git rev-parse --verify main >/dev/null 2>&1; then
  BASE_REF="main"
elif git rev-parse --verify origin/master >/dev/null 2>&1; then
  BASE_REF="origin/master"
fi

BASE_MERGE=""
if [[ -n "$BASE_REF" ]]; then
  BASE_MERGE="$(git merge-base HEAD "$BASE_REF" || true)"
fi

changed_files_path="$OUT_DIR/changed_files.txt"
if [[ -n "$BASE_MERGE" ]]; then
  git diff --name-only "$BASE_MERGE"...HEAD >"$changed_files_path" || true
else
  echo "BASE_NOT_FOUND" >"$changed_files_path"
fi

export REPO_INV_BASE_REF="$BASE_REF"
export REPO_INV_BASE_MERGE="$BASE_MERGE"
export REPO_INV_CHANGED_FILES_PATH="$changed_files_path"

python <<'PY'
import json
import os
import re
import subprocess
from collections import Counter
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:
    yaml = None

HAVE_RUBY = os.environ.get("REPO_INV_HAVE_RUBY", "0") == "1"
HAVE_PYYAML = yaml is not None

OUT_DIR = Path(os.environ["REPO_INV_OUT_DIR"])
TREE_TOOL = os.environ.get("REPO_INV_TREE_TOOL", "tree")
GENERATED_AT = os.environ.get("REPO_INV_GENERATED_AT", "")
BASE_REF = os.environ.get("REPO_INV_BASE_REF", "")
BASE_MERGE = os.environ.get("REPO_INV_BASE_MERGE", "")
CHANGED_FILES_PATH = Path(os.environ.get("REPO_INV_CHANGED_FILES_PATH", OUT_DIR / "changed_files.txt"))

file_mode_hits_path = OUT_DIR / "file_mode_cli_hits.txt"
secrets_if_hits_path = OUT_DIR / "secrets_in_if_hits.txt"
git_files_path = OUT_DIR / "git_files.txt"
tree_path = OUT_DIR / "tree.txt"
md_path = OUT_DIR / "repo_inventory.md"
json_path = OUT_DIR / "repo_inventory.json"
changed_files_path = CHANGED_FILES_PATH


def cmd(args):
    try:
        return subprocess.check_output(args, text=True).strip()
    except subprocess.CalledProcessError as exc:
        return exc.output.strip()


def redact_url(text: str) -> str:
    if not text:
        return text
    return re.sub(r"//([^/@]+)@", "//***@", text)


def parse_workflows():
    workflows = []
    missing_scripts = []
    reusable_missing = []
    deploy_pages_count = 0

    workflow_dir = Path(".github/workflows")
    for wf_path in sorted(workflow_dir.glob("*.y*ml")):
        text = wf_path.read_text()
        parsed_triggers = True

        if HAVE_PYYAML:
            obj = yaml.safe_load(text) or {}
        elif HAVE_RUBY:
            loaded = subprocess.check_output(
                [
                    "ruby",
                    "-ryaml",
                    "-rjson",
                    "-e",
                    "require 'yaml';require 'json'; data=YAML.safe_load(ARGF.read) || {}; puts JSON.generate(data)",
                ],
                input=text,
                text=True,
            )
            obj = json.loads(loaded)
        else:
            obj = {}
            parsed_triggers = False

        name = obj.get("name") or wf_path.stem
        on_section = obj.get("on") or obj.get(True) or {}
        if not parsed_triggers:
            triggers = {"dispatch": None, "push": None, "pr": None, "workflow_call": None}
            schedule = None
        else:
            triggers = {"dispatch": False, "push": False, "pr": False, "workflow_call": False}
            schedule = []

        def mark(trigger):
            triggers[trigger] = True

        if parsed_triggers:
            if isinstance(on_section, dict):
                for key, val in on_section.items():
                    if key == "workflow_dispatch":
                        mark("dispatch")
                    elif key == "workflow_call":
                        mark("workflow_call")
                    elif key == "push":
                        mark("push")
                    elif key in ("pull_request", "pull_request_target"):
                        mark("pr")
                    elif key == "schedule" and isinstance(val, list):
                        schedule.extend([item.get("cron", "") for item in val if isinstance(item, dict)])
            elif isinstance(on_section, list):
                for key in on_section:
                    if key == "workflow_dispatch":
                        mark("dispatch")
                    elif key == "workflow_call":
                        mark("workflow_call")
                    elif key == "push":
                        mark("push")
                    elif key in ("pull_request", "pull_request_target"):
                        mark("pr")
                    elif key == "schedule":
                        schedule.append("")

        deploys_pages = any(s in text for s in (
            "actions/deploy-pages@",
            "actions/upload-pages-artifact@",
            "peaceiris/actions-gh-pages@",
            "github-pages-deploy",
        ))
        if deploys_pages:
            deploy_pages_count += 1

        for match in re.findall(r"(?:python|bash)\s+(scripts/[^\s'\"]+)|\./(scripts/[^\s'\"]+)", text):
            path_fragment = next((m for m in match if m), None)
            if not path_fragment:
                continue
            script_path = Path(path_fragment.split()[0])
            if not script_path.exists():
                missing_scripts.append(f"{wf_path}:{path_fragment}")

        for match in re.findall(r"uses:\s*\./\.github/workflows/([^\s#]+)", text):
            target = Path(".github/workflows") / match
            if not target.exists():
                reusable_missing.append(f"{wf_path}: {target}")

        workflows.append({
            "file": str(wf_path),
            "name": name,
            "triggers": {**triggers, "schedule": schedule},
            "deploys_pages": deploys_pages,
            "parsed_triggers": parsed_triggers,
        })

    return workflows, missing_scripts, reusable_missing, deploy_pages_count


# Git data
remotes = redact_url(cmd(["git", "remote", "-v"]))
branch = cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])
head = cmd(["git", "rev-parse", "HEAD"])
status = cmd(["git", "status", "-sb"])
local_branches = cmd(["git", "branch", "-vv"])
remote_branches = cmd(["git", "branch", "-r"])
log_output = cmd(["git", "log", "--oneline", "--decorate", "--graph", "-20"])
workflow_list_output = cmd([
    "bash", "-c",
    "find .github/workflows -maxdepth 1 -type f \( -name '*.yml' -o -name '*.yaml' \) -print | sort"
])

file_mode_hits = file_mode_hits_path.read_text().strip().splitlines() if file_mode_hits_path.exists() else []
secrets_if_hits = secrets_if_hits_path.read_text().strip().splitlines() if secrets_if_hits_path.exists() else []

workflows, missing_scripts, reusable_missing, deploy_pages_count = parse_workflows()

git_files = git_files_path.read_text().splitlines() if git_files_path.exists() else []
counter = Counter()
for path in git_files:
    top = path.split("/", 1)[0] if "/" in path else "."
    counter[top] += 1

changed_files = []
if changed_files_path.exists():
    changed_files = [line for line in changed_files_path.read_text().splitlines() if line.strip()]

origin_urls = []
for line in remotes.splitlines():
    parts = line.split()
    if len(parts) >= 2:
        origin_urls.append(redact_url(parts[1]))

identity = {
    "origin_urls": origin_urls,
    "head_sha": head,
    "branch": branch,
    "status": status,
}

json_payload = {
    "identity": identity,
    "branches": {
        "local": local_branches.splitlines(),
        "remote": remote_branches.splitlines(),
    },
    "workflows": workflows,
    "files": {
        "count": len(git_files),
        "by_top_dir": dict(sorted(counter.items())),
        "workflows": workflow_list_output.splitlines(),
    },
    "guardrails": {
        "file_mode_cli_hits": file_mode_hits,
        "secrets_in_if_hits": secrets_if_hits,
    },
    "diff": {
        "base_ref": BASE_REF,
        "base_merge": BASE_MERGE,
        "changed_files": changed_files,
        "changed_count": len(changed_files),
    },
}

json_path.write_text(json.dumps(json_payload, indent=2))

md_lines = [
    "# Repo Inventory",
    f"Generated: {GENERATED_AT} (tool: {TREE_TOOL})",
    "",
    "## Identity",
    "```",
    f"pwd: {Path.cwd()}",
    "git remote -v:",
    remotes or "(none)",
    f"current branch: {branch}",
    f"HEAD: {head}",
    f"diff base: {BASE_REF or 'unset'} (merge-base: {BASE_MERGE or 'unset'})",
    "```",
    "",
    "## Branches",
    "### Local",
    "```",
    local_branches or "(none)",
    "```",
    "### Remote",
    "```",
    remote_branches or "(none)",
    "```",
    "",
    "## Recent History",
    "```",
    log_output or "(none)",
    "```",
    "",
    "## Workflows",
]

if not HAVE_PYYAML and not HAVE_RUBY:
    md_lines.extend([
        "",
        "⚠️ **Workflow trigger parsing skipped** (no PyYAML and no Ruby available).",
        "Only file listing and text-based signals were collected.",
        "",
    ])

for wf in workflows:
    triggers = wf["triggers"]
    schedule_values = triggers.get("schedule")
    if isinstance(schedule_values, list):
        schedules = ", ".join([s for s in schedule_values if s]) or "(none)"
    else:
        schedules = "(unknown)"
    md_lines.extend([
        f"- **{wf['name']}** ({wf['file']}): ",
        f"  - dispatch: {triggers.get('dispatch')}",
        f"  - workflow_call: {triggers.get('workflow_call')}",
        f"  - push: {triggers.get('push')}",
        f"  - pr: {triggers.get('pr')}",
        f"  - schedules: {schedules}",
        f"  - deploys Pages: {wf['deploys_pages']}",
    ])

md_lines.extend([
    "",
    "## Guardrails",
    "### File-mode CLI usage",
    "```",
    "\n".join(file_mode_hits) if file_mode_hits else "(none)",
    "```",
    "### secrets.* in if expressions",
    "```",
    "\n".join(secrets_if_hits) if secrets_if_hits else "(none)",
    "```",
    "",
    "## File Inventory",
    f"Total tracked files: {len(git_files)}",
    "", "By top-level directory:",
])

for key, count in sorted(counter.items()):
    md_lines.append(f"- {key}: {count}")

md_lines.extend([
    "",
    "Workflow files:",
    "```",
    workflow_list_output or "(none)",
    "```",
    "",
    f"Tree snapshot ({TREE_TOOL}):",
    "```",
    tree_path.read_text(),
    "```",
])

# Changed files summary (relative to diff base)
md_lines.extend([
    "",
    "## Changed files (relative to diff base)",
    f"- base: {BASE_REF or 'unset'} (merge-base: {BASE_MERGE or 'unset'})",
    f"- count: {len(changed_files)}",
])
if changed_files:
    md_lines.extend(["", "```", *changed_files, "```", ""])

quick_risks = []
if missing_scripts:
    quick_risks.append(f"Missing scripts referenced: {len(missing_scripts)}")
if reusable_missing:
    quick_risks.append(f"Missing reusable workflow targets: {len(reusable_missing)}")
if deploy_pages_count > 1:
    quick_risks.append(f"Potential duplicate Pages deployers: {deploy_pages_count}")

md_lines.extend([
    "",
    "## Quick Risks",
    "- " + "\n- ".join(quick_risks) if quick_risks else "- (none observed)",
    "",
    "## Outputs",
    f"- JSON: {json_path}",
    f"- Markdown: {md_path}",
    f"- git files: {git_files_path}",
    f"- tree snapshot: {tree_path}",
    f"- guardrail hits: {file_mode_hits_path}, {secrets_if_hits_path}",
])

md_path.write_text("\n".join(md_lines))

summary_lines = [
    f"Repo inventory generated at {GENERATED_AT}",
    f"Markdown: {md_path}",
    f"JSON: {json_path}",
    f"Workflows parsed: {len(workflows)}",
    f"Guardrail hits: file-mode={len(file_mode_hits)}, secrets-if={len(secrets_if_hits)}",
]
print("\n".join(summary_lines))

PY

printf "\nFindings:\n"
python <<'PY'
from pathlib import Path
out = Path("out/diagnostics/repo_inventory.md")
if out.exists():
    lines = [line.strip() for line in out.read_text().splitlines() if line.strip().startswith("-")]
    for line in lines[:5]:
        print(line)
else:
    print("- (inventory not generated)")
PY

printf "\nDone. Outputs in %s.\n" "$OUT_DIR"
