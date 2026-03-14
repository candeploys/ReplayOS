#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -m replayos.cli --config config/replayos.toml --env .env run-bg
