#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PARENT_DIR="$(cd "$ROOT_DIR/.." && pwd)"
OUT_FILE="$PARENT_DIR/replayos-github-ready.zip"

rm -f "$OUT_FILE"
(
  cd "$PARENT_DIR"
  zip -r "$OUT_FILE" "replayos" \
    -x "replayos/.git/*" \
    -x "*/__pycache__/*" \
    -x "*.pyc" \
    -x "replayos/.env" \
    -x "replayos/config/replayos.toml" \
    -x "replayos/data/*" \
    -x "replayos/notes/*" \
    -x "replayos/backups/*" \
    -x "replayos/captures/*" \
    -x "replayos/data/replayos.log" \
    -x "replayos/data/replayos.pid" \
    -x "replayos/*.zip"
)

echo "Created: $OUT_FILE"
