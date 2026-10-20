# Mnemo Chrome extension (MV3 scaffold)

A minimal Chrome extension that treats a local (or self-hosted) Mnemo server
as shared memory for the LLM tools you use in the browser.

## How it works

```
content script ──┐
popup  ──────────┴─chrome.runtime──▶  background service worker  ──fetch──▶  Mnemo server
                                          (single API gateway)
```

- `src/popup.html` / `src/popup.js` — settings (server URL, API key, space,
  auto-capture, store-in-English) plus write/read controls for a quick loop.
- `src/content.js` — runs invisibly on chat sites (ChatGPT, Claude, Gemini):
  - **Auto-capture**: a DOM observer silently sends the conversation to Mnemo
    ~12s after activity stops (server-side dedupe/supersede handles repeats).
  - **Context prompt**: when memory from other AI chats exists, a small
    one-time prompt appears: *Add context* copies a prompt-ready markdown
    block to the clipboard (paste with Ctrl+V), *Not now* dismisses it for
    that tab. No permanent UI on the page.
- `src/background.js` — service worker that owns all API calls. Content
  scripts and popups message it, so the page origin never talks to Mnemo
  directly.
- `src/mnemo.js` — browser-safe JS port of `client.ts` from the repo root.

The space is shared across all chat sites and models by default, so a fact
you save on ChatGPT is recalled on Claude. All captured text goes only to
your own Mnemo server.

Settings live in `chrome.storage.sync`. The API key is entered by the user,
never bundled in the extension source. **Store memory in English** sends
`language: "English"`; the server translates non-English text when
`MNEMO_LLM_BASE_URL` / `MNEMO_LLM_MODEL` / `MNEMO_LLM_API_KEY` are configured,
and keeps the source text with a warning otherwise.

## Load it

1. Start the server (either works):

   ```bash
   python -m mnemo                      # http://127.0.0.1:8000
   docker run -d -p 8000:8000 -e MNEMO_API_KEY=change-me -v mnemo-data:/data mnemo
   ```

2. Open `chrome://extensions`, enable **Developer mode**, click
   **Load unpacked**, and select this `extension/` directory.

3. Open the popup: set the server URL and API key (`mnemo-dev-key` unless you
   changed `MNEMO_API_KEY`), pick a space, press **Save**, then **Test**.
4. Chat normally on any supported site — capture is automatic. Open a
   different LLM and use the *Add context* prompt to prove the shared memory
   loop. Auto-capture can be turned off in the popup.

The ID of an unpacked extension is stable per path/machine but can differ
across developers, which is fine because the server accepts any Chrome
extension origin by default
(`MNEMO_CORS_ORIGIN_REGEX=^chrome-extension://[a-p]{32}$`). To lock it down to
one extension ID, set `MNEMO_CORS_ORIGIN_REGEX` or `MNEMO_CORS_ORIGINS`
explicitly. Non-local server URLs trigger a `chrome.permissions.request` for
that origin at save time (`optional_host_permissions`).

## Notes

- Background-service-worker fetches are covered by `host_permissions`
  (`127.0.0.1`/`localhost` by default, any http(s) origin after user grant).
  CORS on the server is still recommended for page-context calls and other
  clients.
- Next steps toward a real product: content scripts that capture the active
  chat (per-site `space_id` mapping), per-user tokens instead of one shared
  key, and an options page for space management.
