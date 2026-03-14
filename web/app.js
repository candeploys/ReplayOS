const keyInput = document.getElementById("apiKey");
const saveMsg = document.getElementById("saveMsg");

const statusOut = document.getElementById("statusOut");
const alertsOut = document.getElementById("alertsOut");
const askOut = document.getElementById("askOut");
const askRefs = document.getElementById("askRefs");
const timelineOut = document.getElementById("timelineOut");
const timelineList = document.getElementById("timelineList");
const noteOut = document.getElementById("noteOut");
const actionStateOut = document.getElementById("actionStateOut");
const undoOut = document.getElementById("undoOut");
const connectorsOut = document.getElementById("connectorsOut");
const connectorRunsOut = document.getElementById("connectorRunsOut");
const connectorRunsList = document.getElementById("connectorRunsList");
const dataOut = document.getElementById("dataOut");
const metricsOut = document.getElementById("metricsOut");

const timelineSource = document.getElementById("timelineSource");
const timelineFrom = document.getElementById("timelineFrom");
const timelineTo = document.getElementById("timelineTo");

const stored = localStorage.getItem("replayos_api_key") || "";
keyInput.value = stored;

let lastActionState = {
  undo_token: null,
  rollback_token: null,
  note_path: null,
  status: "idle",
};

function setOut(el, data) {
  el.textContent = typeof data === "string" ? data : JSON.stringify(data, null, 2);
}

function setActionState(patch) {
  lastActionState = { ...lastActionState, ...patch };
  setOut(actionStateOut, lastActionState);
}

function authHeaders() {
  const key = keyInput.value.trim();
  return key ? { Authorization: `Bearer ${key}` } : {};
}

function toIsoOrEmpty(localValue) {
  const raw = String(localValue || "").trim();
  if (!raw) {
    return "";
  }
  const dt = new Date(raw);
  if (Number.isNaN(dt.getTime())) {
    return "";
  }
  return dt.toISOString();
}

function fmtTs(ts) {
  const dt = new Date(ts);
  if (Number.isNaN(dt.getTime())) {
    return String(ts || "-");
  }
  return dt.toLocaleString();
}

function createCard(title, rows = [], buttonLabel = "Open", onOpen = null) {
  const card = document.createElement("article");
  card.className = "mini-card";

  const h = document.createElement("h4");
  h.textContent = title;
  card.appendChild(h);

  rows.forEach((line) => {
    const p = document.createElement("p");
    p.textContent = line;
    card.appendChild(p);
  });

  if (onOpen) {
    const btn = document.createElement("button");
    btn.textContent = buttonLabel;
    btn.addEventListener("click", onOpen);
    card.appendChild(btn);
  }

  return card;
}

async function api(path, options = {}) {
  const headers = { ...authHeaders(), ...(options.headers || {}) };
  if (options.body) {
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(path, { ...options, headers });
  const text = await res.text();

  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch {
    parsed = text;
  }

  if (!res.ok) {
    throw new Error(typeof parsed === "string" ? parsed : JSON.stringify(parsed));
  }

  return parsed;
}

async function refreshTimeline() {
  try {
    const params = new URLSearchParams();
    params.set("limit", "25");

    const source = timelineSource.value.trim();
    if (source) {
      params.set("source", source);
    }

    const fromIso = toIsoOrEmpty(timelineFrom.value);
    if (fromIso) {
      params.set("from_ts", fromIso);
    }

    const toIso = toIsoOrEmpty(timelineTo.value);
    if (toIso) {
      params.set("to_ts", toIso);
    }

    const data = await api(`/api/events/recent?${params.toString()}`);
    const items = Array.isArray(data.items) ? data.items : [];

    setOut(timelineOut, {
      count: items.length,
      filters: {
        source: source || null,
        from_ts: fromIso || null,
        to_ts: toIso || null,
      },
    });

    timelineList.innerHTML = "";
    items.forEach((item) => {
      const rows = [
        `Source: ${item.source}`,
        `Time: ${fmtTs(item.ts)}`,
        `Content: ${(item.content || "").slice(0, 220)}`,
      ];
      const card = createCard(item.title || "Event", rows, "Details", () => {
        setOut(timelineOut, item);
      });
      timelineList.appendChild(card);
    });
  } catch (err) {
    setOut(timelineOut, String(err));
    timelineList.innerHTML = "";
  }
}

async function refreshConnectorRuns() {
  try {
    const data = await api("/api/connectors/runs?limit=20");
    const runs = Array.isArray(data.runs) ? data.runs : [];
    setOut(connectorRunsOut, { total_runs: runs.length });

    connectorRunsList.innerHTML = "";
    runs.forEach((run) => {
      const rows = [
        `Connector: ${run.connector_id}`,
        `Status: ${run.status}`,
        `Synced: ${run.synced_count}`,
        `Time: ${fmtTs(run.ts)}`,
      ];
      if (run.error_message) {
        rows.push(`Error: ${run.error_message}`);
      }
      connectorRunsList.appendChild(createCard(`Run #${run.id}`, rows));
    });
  } catch (err) {
    setOut(connectorRunsOut, String(err));
    connectorRunsList.innerHTML = "";
  }
}

async function refreshConnectors() {
  try {
    const data = await api("/api/connectors");
    setOut(connectorsOut, data);
  } catch (err) {
    setOut(connectorsOut, String(err));
  }
}

async function refreshStatus() {
  try {
    const data = await api("/health");
    setOut(statusOut, data);
  } catch (err) {
    setOut(statusOut, String(err));
  }
}

async function refreshAlerts() {
  try {
    const data = await api("/api/admin/alerts");
    setOut(alertsOut, data);
  } catch (err) {
    setOut(alertsOut, String(err));
  }
}

async function askTimeline() {
  try {
    const q = document.getElementById("askInput").value.trim();
    const data = await api("/api/ask", {
      method: "POST",
      body: JSON.stringify({ question: q, top_k: 5 }),
    });

    setOut(askOut, {
      answer: data.answer,
      retrieval_mode: data.retrieval_mode,
      error: data.error || null,
      reference_count: Array.isArray(data.references) ? data.references.length : 0,
    });

    askRefs.innerHTML = "";
    const refs = Array.isArray(data.references) ? data.references : [];
    refs.forEach((ref) => {
      const rows = [`Source: ${ref.source}`, `Time: ${fmtTs(ref.ts)}`];
      const card = createCard(ref.title || `Event ${ref.id}`, rows, "Open Event", async () => {
        try {
          const detail = await api(`/api/events/by-id?id=${ref.id}`);
          setOut(askOut, detail.event || detail);
        } catch (error) {
          setOut(askOut, String(error));
        }
      });
      askRefs.appendChild(card);
    });
  } catch (err) {
    setOut(askOut, String(err));
    askRefs.innerHTML = "";
  }
}

document.getElementById("saveKeyBtn").addEventListener("click", () => {
  localStorage.setItem("replayos_api_key", keyInput.value.trim());
  saveMsg.textContent = "Saved.";
});

document.getElementById("refreshStatusBtn").addEventListener("click", refreshStatus);
document.getElementById("refreshAlertsBtn").addEventListener("click", refreshAlerts);
document.getElementById("refreshTimelineBtn").addEventListener("click", refreshTimeline);
document.getElementById("refreshConnectorRunsBtn").addEventListener("click", refreshConnectorRuns);
document.getElementById("askBtn").addEventListener("click", askTimeline);

document.getElementById("clearFiltersBtn").addEventListener("click", () => {
  timelineSource.value = "";
  timelineFrom.value = "";
  timelineTo.value = "";
  refreshTimeline();
});

document.getElementById("noteDryBtn").addEventListener("click", async () => {
  try {
    const title = document.getElementById("noteTitle").value.trim();
    const body = document.getElementById("noteBody").value.trim();
    const data = await api("/api/actions/create-note", {
      method: "POST",
      body: JSON.stringify({ title, body, dry_run: true, approved: false }),
    });
    setOut(noteOut, data);
    const preview = data.preview || {};
    setActionState({
      status: "ghost_run_ready",
      undo_token: preview.undo_token || null,
      note_path: preview.note_path || null,
    });
  } catch (err) {
    setOut(noteOut, String(err));
    setActionState({ status: "ghost_run_error" });
  }
});

document.getElementById("noteExecBtn").addEventListener("click", async () => {
  try {
    const title = document.getElementById("noteTitle").value.trim();
    const body = document.getElementById("noteBody").value.trim();
    const data = await api("/api/actions/create-note", {
      method: "POST",
      body: JSON.stringify({ title, body, approved: true }),
    });
    setOut(noteOut, data);
    setActionState({
      status: data.ok ? "executed" : "failed",
      undo_token: data.undo_token || null,
      note_path: data.note_path || null,
    });
    if (data.undo_token) {
      document.getElementById("undoToken").value = data.undo_token;
    }
  } catch (err) {
    setOut(noteOut, String(err));
    setActionState({ status: "execute_error" });
  }
});

document.getElementById("undoBtn").addEventListener("click", async () => {
  try {
    const undo_token = document.getElementById("undoToken").value.trim();
    const data = await api("/api/actions/undo", {
      method: "POST",
      body: JSON.stringify({ undo_token }),
    });
    setOut(undoOut, data);
    setActionState({
      status: data.ok ? "undone" : "undo_failed",
      rollback_token: data.rollback_token || null,
    });
  } catch (err) {
    setOut(undoOut, String(err));
    setActionState({ status: "undo_error" });
  }
});

document.getElementById("listConnectorsBtn").addEventListener("click", refreshConnectors);

document.getElementById("doctorConnectorsBtn").addEventListener("click", async () => {
  try {
    const data = await api("/api/connectors");
    const connectors = Array.isArray(data.connectors) ? data.connectors : [];
    const report = connectors.map((item) => ({
      id: item.id,
      configured: item.configured,
      missing_env_keys: item.missing_env_keys || [],
      last_run: item.last_run || null,
    }));
    setOut(connectorsOut, { ok: true, connectors: report });
  } catch (err) {
    setOut(connectorsOut, String(err));
  }
});

document.getElementById("syncConnectorsBtn").addEventListener("click", async () => {
  try {
    const data = await api("/api/connectors/sync", {
      method: "POST",
      body: JSON.stringify({ limit_per_connector: 20 }),
    });
    setOut(connectorsOut, data);
    await refreshConnectorRuns();
    await refreshTimeline();
  } catch (err) {
    setOut(connectorsOut, String(err));
  }
});

document.getElementById("exportBtn").addEventListener("click", async () => {
  try {
    const data = await api("/api/data/export?event_limit=200&action_limit=200");
    setOut(dataOut, data);
  } catch (err) {
    setOut(dataOut, String(err));
  }
});

document.getElementById("applyRetentionBtn").addEventListener("click", async () => {
  try {
    const days = Number(document.getElementById("retentionDays").value || "30");
    const data = await api("/api/data/retention/apply", {
      method: "POST",
      body: JSON.stringify({ days }),
    });
    setOut(dataOut, data);
    await refreshTimeline();
  } catch (err) {
    setOut(dataOut, String(err));
  }
});

document.getElementById("metricsBtn").addEventListener("click", async () => {
  try {
    const res = await fetch("/metrics");
    const text = await res.text();
    setOut(metricsOut, text);
  } catch (err) {
    setOut(metricsOut, String(err));
  }
});

(async function bootstrap() {
  setActionState({ status: "idle" });
  await refreshStatus();
  await refreshAlerts();
  await refreshTimeline();
  await refreshConnectors();
  await refreshConnectorRuns();
})();
