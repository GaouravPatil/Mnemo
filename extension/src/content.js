(() => {
  if (window.__mnemoInjected) return;
  window.__mnemoInjected = true;

  const SITE_DEFS = [
    { host: "chatgpt.com", name: "chatgpt", selectors: ["[data-message-author-role]"] },
    { host: "chat.openai.com", name: "chatgpt", selectors: ["[data-message-author-role]"] },
    {
      host: "claude.ai",
      name: "claude",
      selectors: [
        '[data-testid="user-message"]',
        '[data-testid="assistant-message"]',
        ".font-claude-message",
      ],
    },
    { host: "gemini.google.com", name: "gemini", selectors: ["user-query", "model-response"] },
  ];

  const site = SITE_DEFS.find(
    (s) => location.hostname === s.host || location.hostname.endsWith("." + s.host),
  );
  if (!site) return;

  const MAX_TURNS = 24;
  const MAX_CHARS = 4000;
  const CAPTURE_DEBOUNCE_MS = 12000;
  const MIN_SAVE_GAP_MS = 15000;
  const PROMPT_TIMEOUT_MS = 45000;
  const FRAMING =
    "Here is shared memory from this user's previous sessions across AI tools. " +
    "Treat it as established context and use it when answering:\n\n";

  const getCfg = () => chrome.storage.sync.get({ space: "default", autoCapture: true });

  function collectMessages() {
    const nodes = [];
    for (const sel of site.selectors) nodes.push(...document.querySelectorAll(sel));
    const unique = [...new Set(nodes)].sort((a, b) =>
      a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1,
    );
    const texts = [];
    const seen = new Set();
    for (const node of unique) {
      const text = (node.innerText || "").trim();
      if (text.length < 2) continue;
      const key = text.slice(0, 120);
      if (seen.has(key)) continue;
      seen.add(key);
      texts.push(text.slice(0, MAX_CHARS));
    }
    return texts.slice(-MAX_TURNS);
  }

  async function send(msg) {
    try {
      return await chrome.runtime.sendMessage(msg);
    } catch {
      return { ok: false, error: "background unavailable" };
    }
  }

  let observer = null;
  let debounceTimer = 0;
  let lastSentCount = 0;
  let lastSaveAt = 0;

  async function autoSave() {
    const { space, autoCapture } = await getCfg();
    if (autoCapture === false) return;
    const content = collectMessages();
    if (content.length < 2 || content.length <= lastSentCount) return;
    const now = Date.now();
    if (now - lastSaveAt < MIN_SAVE_GAP_MS) return;
    lastSaveAt = now;
    lastSentCount = content.length;
    await send({ type: "write", space, content, sourceModel: site.name + "-web" });
  }

  function scheduleAutoSave() {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(autoSave, CAPTURE_DEBOUNCE_MS);
  }

  function setCapture(enabled) {
    if (enabled && !observer) {
      observer = new MutationObserver(scheduleAutoSave);
      observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    } else if (!enabled && observer) {
      observer.disconnect();
      observer = null;
      clearTimeout(debounceTimer);
    }
  }

  let promptRoot = null;
  let statusEl = null;

  function removePrompt() {
    if (promptRoot) {
      promptRoot.remove();
      promptRoot = null;
      statusEl = null;
    }
  }

  function dismissPrompt() {
    sessionStorage.setItem("mnemoPromptDismissed", "1");
    removePrompt();
  }

  async function addContext(button) {
    const { space } = await getCfg();
    button.disabled = true;
    const res = await send({ type: "read", space, maxTokens: 500, format: "markdown" });
    if (!res || !res.ok) {
      statusEl.textContent = "error: " + (res ? res.error : "no response");
      button.disabled = false;
      return;
    }
    try {
      await navigator.clipboard.writeText(FRAMING + res.data.context);
      statusEl.textContent = "Copied. Paste it into the chat (Ctrl+V).";
      setTimeout(removePrompt, 6000);
    } catch {
      statusEl.textContent = "Clipboard blocked. Use the extension popup instead.";
      button.disabled = false;
    }
  }

  function renderPrompt() {
    promptRoot = document.createElement("div");
    promptRoot.id = "mnemo-prompt-root";
    const shadow = promptRoot.attachShadow({ mode: "open" });
    shadow.innerHTML = `
      <style>
        .box { position: fixed; right: 16px; bottom: 16px; z-index: 2147483647;
               font: 12px/1.4 system-ui, sans-serif; background: #fff; color: #222;
               border: 1px solid #d0d0d0; border-radius: 10px; padding: 10px; width: 230px;
               box-shadow: 0 4px 16px rgba(0,0,0,.15); }
        .msg { margin-bottom: 8px; }
        .row { display: flex; gap: 6px; }
        button { flex: 1; padding: 5px; border: 1px solid #c8c8c8; background: #f7f7f7;
                 border-radius: 6px; cursor: pointer; font: inherit; }
        button:hover { background: #eee; }
        button:disabled { opacity: .6; cursor: default; }
        .status { margin-top: 6px; color: #666; min-height: 14px; }
      </style>
      <div class="box">
        <div class="msg">Mnemo: memory from your other AI chats is available.</div>
        <div class="row">
          <button class="add">Add context</button>
          <button class="dismiss">Not now</button>
        </div>
        <div class="status"></div>
      </div>`;
    document.documentElement.appendChild(promptRoot);
    statusEl = shadow.querySelector(".status");
    const addBtn = shadow.querySelector(".add");
    addBtn.addEventListener("click", () => addContext(addBtn));
    shadow.querySelector(".dismiss").addEventListener("click", dismissPrompt);
    setTimeout(() => removePrompt(), PROMPT_TIMEOUT_MS);
  }

  async function maybePrompt() {
    if (sessionStorage.getItem("mnemoPromptDismissed")) return;
    const { space } = await getCfg();
    const res = await send({ type: "read", space, maxTokens: 60 });
    if (!res || !res.ok) return;
    if (((res.data.stats || {}).units_total || 0) === 0) return;
    renderPrompt();
  }

  getCfg().then(({ autoCapture }) => setCapture(autoCapture !== false));
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area === "sync" && changes.autoCapture) {
      setCapture(changes.autoCapture.newValue !== false);
    }
  });
  maybePrompt();
})();
