#!/bin/bash
# CR 1 · the demo's controls in ONE command each, from the founder's Mac. Sets itself up the first time (a Python
# environment under ~/.cache, the Railway link); the production secrets stay in Railway and are never printed.
#
#   bash ~/Developer/Sasha-travel-/backend/scripts/cr1_demo.sh reset            # before the demo: YOUR account, both products
#   bash ~/Developer/Sasha-travel-/backend/scripts/cr1_demo.sh reset campus     # just CampusMe (or: relocation)
#   bash ~/Developer/Sasha-travel-/backend/scripts/cr1_demo.sh reset all --vault   # also forget the saved student details
#   bash ~/Developer/Sasha-travel-/backend/scripts/cr1_demo.sh rehearse         # the whole demo, WhatsApp captured, timed
#   bash ~/Developer/Sasha-travel-/backend/scripts/cr1_demo.sh health
set -e
BACKEND="$(cd "$(dirname "$0")/.." && pwd)"
HOME_DIR="$HOME/.cache/kanoe-cr1"
VENV="$HOME_DIR/venv"
LINK="$HOME_DIR/railway-link"
UV="$(command -v uv || echo "$HOME/.local/bin/uv")"
mkdir -p "$HOME_DIR" "$LINK"
if [ ! -x "$VENV/bin/python" ]; then
  echo "First run: setting up (about a minute)…"
  "$UV" venv -q -p 3.12 "$VENV"
  "$UV" pip install -q -p "$VENV/bin/python" -r "$BACKEND/requirements.txt"
fi
cd "$LINK"
if ! npx -y @railway/cli@latest status >/dev/null 2>&1; then
  npx -y @railway/cli@latest link --project 57e316de-0181-40e2-8d7b-68c8db13b513 \
    --service 6b2d42a0-f786-44e1-b7fb-d32328292bda --environment production >/dev/null
fi
npx -y @railway/cli@latest run -- env PYTHONPATH="$BACKEND" "$VENV/bin/python" -m scripts.cr1_demo "$@" 2>&1 \
  | grep -v "npm warn\|signing key unusable\|static demo cache"
