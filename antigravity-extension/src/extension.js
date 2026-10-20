const vscode = require("vscode");
const { captureOnce } = require("./capture");
const { MnemoClient } = require("./mnemoClient");

let output;
let statusItem;
let timer;
let capturing = false;

function config() {
  const c = vscode.workspace.getConfiguration("mnemo");
  return {
    baseUrl: c.get("baseUrl", "http://127.0.0.1:8000"),
    apiKey: c.get("apiKey", "mnemo-dev-key"),
    space: c.get("space", "antigravity"),
    autoCapture: c.get("autoCapture", true),
    pollSeconds: Math.max(5, Number(c.get("pollSeconds", 20)) || 20),
    translateToEnglish: c.get("translateToEnglish", true),
    maxCaptureChars: Math.max(1000, Number(c.get("maxCaptureChars", 20000)) || 20000),
  };
}

function client() {
  const cfg = config();
  return { cfg, api: new MnemoClient(cfg.baseUrl, cfg.apiKey) };
}

function log(message) {
  if (output) output.appendLine(`[${new Date().toLocaleTimeString()}] ${message}`);
}

function formatTokens(value) {
  const n = Number(value) || 0;
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

async function refreshStatus() {
  if (!statusItem) return;
  const { cfg, api } = client();
  try {
    const summary = await api.summary(cfg.space, { maxTokens: 120 });
    const units = summary.stats?.units_total || 0;
    const tokens = summary.stats?.stored_tokens || 0;
    statusItem.text = `$(book) Mnemo ${units}u / ${formatTokens(tokens)} tok`;
    statusItem.tooltip = `Space ${cfg.space}: ${units} active units, ${formatTokens(tokens)} stored tokens\nClick for the Mnemo dashboard.`;
    statusItem.show();
  } catch {
    statusItem.text = "$(book) Mnemo offline";
    statusItem.tooltip = `Cannot reach ${cfg.baseUrl}`;
    statusItem.show();
  }
}

async function runCapture(showResult = true) {
  if (capturing) return null;
  capturing = true;
  const { cfg, api } = client();
  try {
    const result = await captureOnce({
      client: api,
      space: cfg.space,
      state: {
        get: (key, fallback) => apiState.get(key, fallback),
        update: (key, value) => apiState.update(key, value),
      },
      log,
      maxChars: cfg.maxCaptureChars,
      language: cfg.translateToEnglish ? "English" : undefined,
    });
    if (result.skipped) {
      if (showResult) {
        log(`capture skipped: ${result.skipped}`);
        vscode.window.showWarningMessage(`Mnemo: ${result.skipped}`);
      }
    } else {
      const text = `captured ${result.messages} turns, ${result.units} units, ${result.usage} usage rows from ${result.conversations} conversation(s)`;
      log(text);
      if (showResult) vscode.window.showInformationMessage(`Mnemo ${text}.`);
    }
    await refreshStatus();
    return result;
  } catch (err) {
    log(`capture failed: ${err.message}`);
    if (showResult) vscode.window.showErrorMessage(`Mnemo capture failed: ${err.message}`);
    return null;
  } finally {
    capturing = false;
  }
}

let apiState;

function startTimer() {
  if (timer) clearInterval(timer);
  const cfg = config();
  if (!cfg.autoCapture) return;
  timer = setInterval(() => runCapture(false), cfg.pollSeconds * 1000);
}

function card(label, value, hint = "") {
  return `<div class="card"><div class="label">${escapeHtml(label)}</div>
    <div class="value">${escapeHtml(value)}</div>
    <div class="hint">${escapeHtml(hint)}</div></div>`;
}

function dashboardHtml(summary, usage) {
  const quality = summary.quality || {};
  const stats = summary.stats || {};
  const totals = usage.totals || {};
  const models = usage.by_model || [];
  const days = usage.by_day || [];
  const counts = summary.counts || {};
  const typeList = Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .map(([k, v]) => `<span class="pill">${escapeHtml(k)} ${v}</span>`)
    .join("");
  const modelRows = models
    .map(
      (m) => `<tr><td>${escapeHtml(m.model)}</td><td>${m.calls}</td>
      <td>${formatTokens(m.input_tokens)}</td><td>${formatTokens(m.output_tokens)}</td>
      <td>${formatTokens(m.cache_read_tokens)}</td><td>${formatTokens(m.reasoning_tokens)}</td></tr>`,
    )
    .join("");
  const dayRows = days
    .map(
      (d) => `<tr><td>${escapeHtml(d.day)}</td><td>${d.calls}</td>
      <td>${formatTokens(d.input_tokens)}</td><td>${formatTokens(d.output_tokens)}</td>
      <td>${formatTokens(d.cache_read_tokens)}</td></tr>`,
    )
    .join("");
  return `<!doctype html>
<html><head><meta charset="utf-8">
<style>
  body { font-family: var(--vscode-font-family); color: var(--vscode-foreground);
         background: var(--vscode-editor-background); padding: 18px; }
  h1 { font-size: 20px; margin: 0 0 4px; }
  h2 { font-size: 14px; margin: 24px 0 8px; text-transform: uppercase; letter-spacing: .08em; opacity: .7; }
  .muted { opacity: .65; font-size: 12px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }
  .card { border: 1px solid var(--vscode-panel-border); border-radius: 8px; padding: 12px; }
  .label { font-size: 11px; opacity: .65; text-transform: uppercase; letter-spacing: .05em; }
  .value { font-size: 22px; font-weight: 600; margin-top: 4px; }
  .hint { font-size: 11px; opacity: .6; margin-top: 2px; }
  .pill { display: inline-block; border: 1px solid var(--vscode-panel-border);
          border-radius: 999px; padding: 2px 8px; margin: 2px; font-size: 11px; }
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--vscode-panel-border); }
  th { opacity: .65; font-weight: 500; }
  pre { white-space: pre-wrap; font-family: var(--vscode-editor-font-family);
        background: var(--vscode-textCodeBlock-background); padding: 12px; border-radius: 8px;
        font-size: 12px; }
  button { background: var(--vscode-button-background); color: var(--vscode-button-foreground);
           border: none; border-radius: 4px; padding: 6px 12px; cursor: pointer; }
  button:hover { background: var(--vscode-button-hoverBackground); }
</style></head>
<body>
  <h1>Mnemo memory dashboard</h1>
  <div class="muted">space <b>${escapeHtml(summary.space_id)}</b> · precision and usage are measured locally from stored units</div>
  <h2>Memory</h2>
  <div class="grid">
    ${card("Active units", stats.units_total ?? 0, "deduplicated facts")}
    ${card("Stored tokens", formatTokens(stats.stored_tokens), "compact memory")}
    ${card("Writes", summary.writes ?? "—", "capture batches")}
    ${card("Precision proxy", `${Math.round((quality.precision_proxy || 0) * 100)}%`, "units with exact values")}
    ${card("Dedupe ratio", `${Math.round((quality.dedupe_ratio || 0) * 100)}%`, "paraphrases merged")}
    ${card("Superseded", `${Math.round((quality.supersede_ratio || 0) * 100)}%`, "stale values kept as history")}
  </div>
  <div style="margin-top:10px">${typeList || '<span class="muted">no units yet</span>'}</div>
  <div class="muted" style="margin-top:8px">Accuracy is validated by benchmark.py: the quality gate requires full critical-fact recall and no stale leaks.</div>
  <h2>AI usage</h2>
  <div class="grid">
    ${card("Calls", totals.calls ?? 0)}
    ${card("Input tokens", formatTokens(totals.input_tokens))}
    ${card("Output tokens", formatTokens(totals.output_tokens))}
    ${card("Cache read", formatTokens(totals.cache_read_tokens))}
    ${card("Reasoning", formatTokens(totals.reasoning_tokens))}
    ${card("Total tokens", formatTokens(totals.total_tokens))}
  </div>
  <h2>By model</h2>
  <table><thead><tr><th>Model</th><th>Calls</th><th>Input</th><th>Output</th><th>Cache</th><th>Reasoning</th></tr></thead>
  <tbody>${modelRows || '<tr><td colspan="6" class="muted">No usage captured yet.</td></tr>'}</tbody></table>
  <h2>Last 7 days</h2>
  <table><thead><tr><th>Day</th><th>Calls</th><th>Input</th><th>Output</th><th>Cache</th></tr></thead>
  <tbody>${dayRows || '<tr><td colspan="5" class="muted">No usage captured yet.</td></tr>'}</tbody></table>
  <h2>Summary</h2>
  <pre>${escapeHtml(summary.summary || "")}</pre>
  <p><button onclick="acquireVsCodeApi().postMessage({type:'refresh'})">Refresh</button></p>
</body></html>`;
}

async function showDashboard() {
  const { cfg, api } = client();
  const panel = vscode.window.createWebviewPanel(
    "mnemoDashboard",
    "Mnemo",
    vscode.ViewColumn.One,
    { enableScripts: true },
  );
  const load = async () => {
    panel.webview.html = `<html><body style="font-family:sans-serif;padding:20px">Loading Mnemo…</body></html>`;
    try {
      const since = Math.floor(Date.now() / 1000) - 7 * 24 * 60 * 60;
      const [summary, usage] = await Promise.all([
        api.summary(cfg.space, { maxTokens: 500 }),
        api.usageSummary(cfg.space, since),
      ]);
      panel.webview.html = dashboardHtml(summary, usage);
    } catch (err) {
      panel.webview.html = `<html><body style="font-family:sans-serif;padding:20px">
        <h3>Mnemo is unreachable</h3><p>${escapeHtml(err.message)}</p>
        <p>Check <code>mnemo.baseUrl</code> and start the server with <code>python -m mnemo</code>.</p>
      </body></html>`;
    }
  };
  panel.webview.onDidReceiveMessage(async (msg) => {
    if (msg && msg.type === "refresh") await load();
  });
  await load();
}

async function copyContext() {
  const { cfg, api } = client();
  const query = await vscode.window.showInputBox({
    title: "Mnemo: copy shared context",
    prompt: "Optional query to rank memory (leave empty for the most important context)",
    placeHolder: "e.g. deployment constraints",
  });
  try {
    const data = await api.read(cfg.space, {
      query: query || undefined,
      maxTokens: 800,
      format: "markdown",
    });
    const text =
      "Here is shared memory from this user's previous sessions across AI tools. " +
      "Treat it as established context and use it when answering:\n\n" +
      data.context;
    await vscode.env.clipboard.writeText(text);
    vscode.window.showInformationMessage(
      `Mnemo copied ${data.stats.units_included}/${data.stats.units_total} units (${data.tokens} tokens) to the clipboard.`,
    );
  } catch (err) {
    vscode.window.showErrorMessage(`Mnemo copy failed: ${err.message}`);
  }
}

async function testConnection() {
  const { cfg, api } = client();
  try {
    const health = await api.health();
    const summary = await api.summary(cfg.space, { maxTokens: 80 });
    vscode.window.showInformationMessage(
      `Mnemo connected (${health.status}). Space ${cfg.space}: ${summary.stats.units_total} units, ${summary.stats.stored_tokens} tokens.`,
    );
  } catch (err) {
    vscode.window.showErrorMessage(`Mnemo connection failed: ${err.message}`);
  }
}

function activate(context) {
  apiState = context.globalState;
  output = vscode.window.createOutputChannel("Mnemo");
  statusItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
  statusItem.command = "mnemo.showSummary";

  context.subscriptions.push(output, statusItem);
  context.subscriptions.push(
    vscode.commands.registerCommand("mnemo.captureNow", () => runCapture(true)),
    vscode.commands.registerCommand("mnemo.showSummary", showDashboard),
    vscode.commands.registerCommand("mnemo.copyContext", copyContext),
    vscode.commands.registerCommand("mnemo.testConnection", testConnection),
    vscode.commands.registerCommand("mnemo.openSettings", () =>
      vscode.commands.executeCommand("workbench.action.openSettings", "mnemo"),
    ),
  );

  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (event.affectsConfiguration("mnemo")) {
        startTimer();
        refreshStatus();
      }
    }),
  );

  log("Mnemo extension activated");
  refreshStatus();
  startTimer();
  setTimeout(() => runCapture(false), 5000);
}

function deactivate() {
  if (timer) clearInterval(timer);
  timer = undefined;
}

module.exports = { activate, deactivate };
