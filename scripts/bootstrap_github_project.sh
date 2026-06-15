#!/usr/bin/env bash
# Create/link AiPal Roadmap project and custom fields via gh CLI (Actions-friendly).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OWNER="${GITHUB_REPOSITORY_OWNER:-tfasanya79}"
REPO="${GITHUB_REPOSITORY_NAME:-aipal}"
TITLE="${AIPAL_PROJECT_TITLE:-AiPal Roadmap}"
export GH_TOKEN="${GITHUB_TOKEN:?GITHUB_TOKEN required}"

cd "$ROOT"

if ! command -v gh >/dev/null; then
  echo "ERROR: gh CLI required" >&2
  exit 1
fi

find_project_number() {
  gh project list --owner "$OWNER" --format json \
    | python3 -c "
import json, sys
title = sys.argv[1]
raw = json.load(sys.stdin)
projects = raw.get('projects', raw if isinstance(raw, list) else [])
for p in projects:
    if p.get('title') == title:
        print(p['number'])
        break
" "$TITLE" 2>/dev/null || true
}

NUM="$(find_project_number)"
if [[ -z "$NUM" ]]; then
  echo "Creating project: $TITLE"
  NUM="$(gh project create --owner "$OWNER" --title "$TITLE" --format json \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['number'])")"
fi

echo "Project number: $NUM"
gh project link "$NUM" --owner "$OWNER" --repo "$OWNER/$REPO" 2>/dev/null || true

ensure_field() {
  local name="$1"
  local options="$2"
  if gh project field-list "$NUM" --owner "$OWNER" --format json \
    | python3 -c "import json,sys; name=sys.argv[1]; data=json.load(sys.stdin); fields=data.get('fields',[]); sys.exit(0 if any(f.get('name')==name for f in fields) else 1)" "$name" 2>/dev/null; then
    echo "Field exists: $name"
  else
    echo "Creating field: $name"
    gh project field-create "$NUM" --owner "$OWNER" --name "$name" \
      --data-type SINGLE_SELECT --single-select-options "$options"
  fi
}

ensure_field "Status" "Todo,In progress,Done,Deferred"
ensure_field "Phase" "A,B,C0,C1,C2,C3a,C3b,C4"
ensure_field "Area" "mobile,api,docs,infra"

URL="$(gh project view "$NUM" --owner "$OWNER" --format json | python3 -c "import json,sys; print(json.load(sys.stdin).get('url',''))")"

mkdir -p .github
python3 - "$OWNER" "$REPO" "$TITLE" "$NUM" "$URL" <<'PY'
import json, sys
from pathlib import Path
owner, repo, title, num, url = sys.argv[1:6]
path = Path(".github/project.json")
cfg = {}
if path.exists():
    cfg = json.loads(path.read_text())
cfg.update({
    "owner": owner,
    "repo": repo,
    "project_title": title,
    "project_number": int(num),
    "project_url": url,
    "bootstrapped": True,
})
path.write_text(json.dumps(cfg, indent=2) + "\n")
print(f"Wrote {path}")
PY

# Ensure repo labels exist (best-effort)
labels=(
  "track:backlog"
  "phase:A" "phase:B" "phase:C0" "phase:C1" "phase:C2" "phase:C3a" "phase:C3b" "phase:C4"
  "area:mobile" "area:api" "area:docs" "area:infra"
)
for label in "${labels[@]}"; do
  gh label create "$label" --repo "$OWNER/$REPO" --force 2>/dev/null || true
done

echo "Bootstrap complete: $URL"
