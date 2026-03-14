# ReplayOS 60-Second Demo Pack

## One-command setup

```bash
cd replayos
./scripts/demo_one_command.sh
```

This script:
- creates local demo config/env if missing
- seeds timeline data
- starts ReplayOS in background
- prints UI URL and stop command

## 60-second live flow

1. Open `http://127.0.0.1:8787/`
2. Paste API key from `.env` into UI Auth panel
3. Click `Refresh Timeline`
4. Ask: `Summarize my timeline briefly`
5. Do `Create Note` dry-run then execute
6. Undo with token
7. Open `Metrics` and `Alerts`

## Demo storytelling angle

- "Memory + Safe Actions"
- "Fallback retrieval avoids empty-context AI answers"
- "Production controls: auth, rate limit, metrics, retention, backup"
