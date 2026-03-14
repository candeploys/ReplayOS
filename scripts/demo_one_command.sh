#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f config/replayos.toml ] || [ ! -f .env ]; then
  echo "Bootstrapping config for local demo..."
  API_KEY="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(24))
PY
)"
  cat > config/replayos.toml <<CFG
[provider]
default = "local_qwen"

[provider.local_qwen]
base_url = "http://localhost:11434"
model = "qwen2.5:7b-instruct-q4_K_M"

[provider.claude_api]
model = "claude-sonnet-4"

[provider.openai_api]
model = "gpt-5-mini"

[safety]
require_ghost_run = true
require_approval_for_high_risk = true

[server]
host = "127.0.0.1"
port = 8787

[auth]
require_api_key = true
allow_localhost_without_key = false
api_keys = []

[limits]
max_request_bytes = 1048576
default_search_limit = 10
max_search_limit = 100
default_recent_limit = 20
max_recent_limit = 200
default_top_k = 5
max_top_k = 20
rate_limit_requests = 120
rate_limit_window_seconds = 60

[observability]
log_level = "INFO"
log_json = true

[runtime]
environment = "production"
provider_timeout_seconds = 15

[alerting]
error_rate_threshold = 0.20
error_window_seconds = 300
min_requests_for_alarm = 20

[data_policy]
default_retention_days = 30
allow_full_delete = false

[plugins]
directories = ["plugins"]
CFG

  cat > .env <<ENV
REPLAYOS_API_KEYS=$API_KEY
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
REPLAYOS_ENV=production
ENV

  echo "Generated local API key: $API_KEY"
fi

python3 -m replayos.cli --config config/replayos.toml --env .env seed-demo --count 8
python3 -m replayos.cli --config config/replayos.toml --env .env run-bg

echo ""
echo "Demo is up: http://127.0.0.1:8787"
echo "Open UI:   http://127.0.0.1:8787/"
echo "Stop:      ./scripts/stop.sh"
