# Mnemo for Antigravity

A VS Code-compatible extension for Google Antigravity (and Antigravity IDE) that
turns Mnemo into a shared memory and usage ledger for AI coding sessions.

It captures user/assistant turns from local Antigravity conversations, writes
them to Mnemo, reports exact per-request token usage, and shows a dashboard with
memory quality metrics. The same memory space can then be recalled from
ChatGPT, Claude, Gemini, or another Antigravity workspace through the Mnemo
Chrome extension, the TypeScript client, or the HTTP API.

## Why this shape

Antigravity runs a local language server that exposes the active conversation
and token metadata over ConnectRPC on `127.0.0.1`. The extension discovers that
process and reads:

- `GetCascadeTrajectory` for decoded user/assistant steps
- `GetCascadeTrajectoryGeneratorMetadata` for input, output, cache-read, and
  reasoning token counts

No conversation content leaves the machine except to the Mnemo server you
configure.

## Install

### Option A: copy into the extension directory

```bash
cp -r antigravity-extension "$HOME/.antigravity-ide/extensions/mnemo-antigravity-0.1.0"
```

On the standalone Antigravity app use `$HOME/.antigravity/extensions` instead.
Restart Antigravity, open the command palette, and run
**Mnemo: Test server connection**. For other VS Code-family editors use that
editor's extension directory.

### Option B: build a VSIX

```bash
cd antigravity-extension
npx @vscode/vsce package
```

Then install the generated `.vsix` from the Extensions view. The extension uses
only the stable VS Code API and no runtime dependencies.

## Start the server

```bash
.venv/bin/python -m mnemo
# or
docker run -d --name mnemo -p 8000:8000 \
  -e MNEMO_API_KEY=change-me -v mnemo-data:/data mnemo
```

## Settings

| setting | default | purpose |
| --- | --- | --- |
| `mnemo.baseUrl` | `http://127.0.0.1:8000` | Mnemo server |
| `mnemo.apiKey` | `mnemo-dev-key` | server API key |
| `mnemo.space` | `antigravity` | shared memory space |
| `mnemo.autoCapture` | `true` | capture new turns automatically |
| `mnemo.pollSeconds` | `20` | how often to check |
| `mnemo.translateToEnglish` | `true` | ask the server to store English |
| `mnemo.maxCaptureChars` | `20000` | max characters per capture batch |

Commands:

- **Mnemo: Capture conversation now** — force a capture
- **Mnemo: Show memory dashboard** — units, token quality, usage by model/day
- **Mnemo: Copy shared context** — paste-ready Markdown for another LLM
- **Mnemo: Test server connection**
- **Mnemo: Open settings**

## English storage

`mnemo.translateToEnglish` sends `language: "English"` to Mnemo. The server
translates non-English text before extraction only when an OpenAI-compatible
LLM is configured:

```bash
export MNEMO_LLM_BASE_URL=https://api.openai.com/v1
export MNEMO_LLM_MODEL=gpt-4o-mini
export MNEMO_LLM_API_KEY=...
```

Exact tokens (numbers, paths, versions, IDs) are validated after translation;
if the translation would introduce or drop one, the source text is kept and a
warning is logged. Without LLM settings Mnemo stores the original language and
the extension logs `language_warning`.

## Summary, precision, and accuracy

- `precision_proxy` = share of active units that contain a verbatim value
  (number, path, URL, version, ID). This is the runtime guard against lossy
  summaries.
- `dedupe_ratio` = how much paraphrase merging has happened.
- `supersede_ratio` = share of units replaced by newer values; history remains
  queryable with `GET /memory/unit/{id}`.
- `benchmark.py` remains the accuracy test: it replays conversations and
  asserts critical-fact recall, no stale leaks, and compression targets.

The dashboard shows all of these plus exact token counts by model and day. Usage
rows are deduplicated by `responseId` on the server, so restarts and repeated
polls do not double-count.

## Notes

- The Antigravity language-server RPCs are undocumented and may change. Capture
  errors are logged to the **Mnemo** output channel and never block the editor.
- Process discovery is implemented for Linux and macOS (`ps`, `lsof`/`ss`).
  Windows needs a PowerShell process adapter before the extension can find the
  language server automatically.
- Captured conversation content is sent only to `mnemo.baseUrl`.
- The extension has no build step and no third-party runtime dependencies.
