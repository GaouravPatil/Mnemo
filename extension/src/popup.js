const $ = (id) => document.getElementById(id);

function setStatus(text) {
  $("status").textContent = text;
}

function setOutput(value) {
  $("output").textContent =
    typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

async function saveConfig() {
  const baseUrl = $("baseUrl").value.trim().replace(/\/$/, "") || "http://127.0.0.1:8000";
  const apiKey = $("apiKey").value.trim();
  const space = $("space").value.trim() || "default";
  const autoCapture = $("autoCapture").checked;
  const translateToEnglish = $("translateToEnglish").checked;
  await chrome.storage.sync.set({ baseUrl, apiKey, space, autoCapture, translateToEnglish });

  try {
    const origin = new URL(baseUrl).origin + "/*";
    const isLocal = ["http://127.0.0.1:8000", "http://localhost:8000"].includes(
      new URL(baseUrl).origin,
    );
    if (!isLocal) {
      await chrome.permissions.request({ origins: [origin] }).catch(() => false);
    }
  } catch {
    setStatus("invalid server URL");
    return { baseUrl, apiKey, space };
  }
  return { baseUrl, apiKey, space };
}

async function send(msg) {
  return chrome.runtime.sendMessage(msg);
}

async function withConfig(fn) {
  const { space } = await saveConfig();
  const res = await fn(space);
  if (!res || !res.ok) {
    setStatus("error: " + (res ? res.error : "no response"));
    setOutput("");
    return null;
  }
  setStatus("");
  return res.data;
}

async function loadConfig() {
  const { baseUrl, apiKey, space, autoCapture, translateToEnglish } =
    await chrome.storage.sync.get({
      baseUrl: "http://127.0.0.1:8000",
      apiKey: "mnemo-dev-key",
      space: "default",
      autoCapture: true,
      translateToEnglish: true,
    });
  $("baseUrl").value = baseUrl;
  $("apiKey").value = apiKey;
  $("space").value = space;
  $("autoCapture").checked = autoCapture !== false;
  $("translateToEnglish").checked = translateToEnglish !== false;
}

$("save").addEventListener("click", async () => {
  await saveConfig();
  setStatus("saved");
});

$("test").addEventListener("click", async () => {
  const data = await withConfig((space) =>
    send({ type: "read", space, query: "health check", maxTokens: 16 }),
  );
  if (data) {
    setStatus("connected (tokenizer: " + data.tokenizer + ")");
    setOutput(data.context || "(empty space)");
  }
});

$("write").addEventListener("click", async () => {
  const content = $("writeText").value.trim();
  if (!content) {
    setStatus("nothing to write");
    return;
  }
  const language = $("translateToEnglish").checked ? "English" : undefined;
  const data = await withConfig((space) =>
    send({ type: "write", space, content, language }),
  );
  if (data) {
    setOutput(data.written);
    $("writeText").value = "";
    setStatus(`stored ${data.written.length} unit(s)`);
  }
});

$("read").addEventListener("click", async () => {
  const data = await withConfig((space) =>
    send({
      type: "read",
      space,
      query: $("query").value.trim() || undefined,
      maxTokens: 400,
    }),
  );
  if (data) {
    setOutput(data.context);
    setStatus(`${data.tokens} tokens, ${data.stats.units_included}/${data.stats.units_total} units`);
  }
});

loadConfig();
