const keyInput = document.getElementById("apiKey");
const saveMsg = document.getElementById("saveMsg");

const statusOut = document.getElementById("statusOut");
const alertsOut = document.getElementById("alertsOut");
const askOut = document.getElementById("askOut");
const timelineOut = document.getElementById("timelineOut");
const noteOut = document.getElementById("noteOut");
const undoOut = document.getElementById("undoOut");
const connectorsOut = document.getElementById("connectorsOut");
const dataOut = document.getElementById("dataOut");
const metricsOut = document.getElementById("metricsOut");

const stored = localStorage.getItem("replayos_api_key") || "";
keyInput.value = stored;

function setOut(el, data) {
  el.textContent = typeof data === "string" ? data : JSON.stringify(data, null, 2);
}

function authHeaders() {
  const key = keyInput.value.trim();
  return key ? { Authorization: `Bearer ${key}` } : {};
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

document.getElementById("saveKeyBtn").addEventListener("click", () => {
  localStorage.setItem("replayos_api_key", keyInput.value.trim());
  saveMsg.textContent = "Saved.";
});

document.getElementById("refreshStatusBtn").addEventListener("click", async () => {
  try {
    const data = await api("/health");
    setOut(statusOut, data);
  } catch (err) {
    setOut(statusOut, String(err));
  }
});

document.getElementById("refreshAlertsBtn").addEventListener("click", async () => {
  try {
    const data = await api("/api/admin/alerts");
    setOut(alertsOut, data);
  } catch (err) {
    setOut(alertsOut, String(err));
  }
});

document.getElementById("askBtn").addEventListener("click", async () => {
  try {
    const q = document.getElementById("askInput").value.trim();
    const data = await api("/api/ask", {
      method: "POST",
      body: JSON.stringify({ question: q, top_k: 5 }),
    });
    setOut(askOut, data);
  } catch (err) {
    setOut(askOut, String(err));
  }
});

document.getElementById("refreshTimelineBtn").addEventListener("click", async () => {
  try {
    const data = await api("/api/events/recent?limit=25");
    setOut(timelineOut, data);
  } catch (err) {
    setOut(timelineOut, String(err));
  }
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
  } catch (err) {
    setOut(noteOut, String(err));
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
  } catch (err) {
    setOut(noteOut, String(err));
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
  } catch (err) {
    setOut(undoOut, String(err));
  }
});

document.getElementById("listConnectorsBtn").addEventListener("click", async () => {
  try {
    const data = await api("/api/connectors");
    setOut(connectorsOut, data);
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
  document.getElementById("refreshStatusBtn").click();
  document.getElementById("refreshTimelineBtn").click();
  document.getElementById("refreshAlertsBtn").click();
})();
