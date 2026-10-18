# Mnemo

[![CI](https://github.com/GaouravPatil/Mnemo/actions/workflows/ci.yml/badge.svg)](https://github.com/GaouravPatil/Mnemo/actions/workflows/ci.yml)

Memory-as-a-service for LLMs: a model-agnostic memory layer that turns chat
history into compact, deduplicated facts and returns the smallest context a
model needs to continue a task.

- **Write path** extracts atomic units (decision, constraint, state, todo,
  fact, entity, question), compresses them, deduplicates paraphrases, and
  supersedes stale values while keeping history queryable.
- **Read path** ranks units by query relevance, recency, type priority, and
  embedding similarity, then packs them under a token budget with an omitted
  index so nothing is lost.
- **Storage** is SQLite + FTS5 (zero services). Token accounting uses
  `tiktoken` and follows the caller's target model.

## Quickstart

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m mnemo            # serves http://127.0.0.1:8000
```

The API key defaults to `mnemo-dev-key` (`MNEMO_API_KEY` to change it).
The database defaults to `data/mnemo.db` (`MNEMO_DB` to change it).

### Docker

```bash
docker build -t mnemo .
docker run -d --name mnemo -p 8000:8000 \
  -e MNEMO_API_KEY=change-me \
  -v mnemo-data:/data \
  mnemo
curl -s localhost:8000/health   # {"status":"ok"} (no auth)
```

The image is a multi-stage `python:3.13-alpine` build (~50 MB): the venv is
built in a builder stage and copied into a clean runtime with no compiler.
It runs as non-root user `mnemo`, listens on `0.0.0.0:8000`
(`MNEMO_HOST`/`MNEMO_PORT`/`MNEMO_RELOAD`), stores SQLite at
`/data/mnemo.db` (mount the `/data` volume), and ships a `HEALTHCHECK`
against `/health`.

## API

All endpoints require the `X-API-Key` header.

### `POST /memory/write`

Accepts a string or a list of conversation turns. Turns may be
`{"model": ..., "text": ...}` objects.

```bash
curl -s localhost:8000/memory/write \
  -H 'X-API-Key: mnemo-dev-key' -H 'Content-Type: application/json' \
  -d '{
    "space_id": "ledger",
    "source_model": "gpt-4o",
    "content": [
      {"model": "a", "text": "The gateway timeout is 30s."},
      {"model": "b", "text": "After the incident review the timeout was changed to 45s."}
    ]
  }'
```

### `POST /memory/read`

Returns a packed context, the units included, the omitted index, and stats.

```bash
curl -s localhost:8000/memory/read \
  -H 'X-API-Key: mnemo-dev-key' -H 'Content-Type: application/json' \
  -d '{"space_id": "ledger", "query": "what is the gateway timeout?", "max_tokens": 200}'
```

```json
{
  "context": "#MEM T=d/c/s/t/f/e/q; exact verbatim; omitted \"#id label\" GET /memory/unit/id\nf timeout 45s",
  "tokens": 31,
  "included": ["62ecbb60"],
  "omitted": [],
  "stats": {"units_total": 1, "units_included": 1, "units_omitted": 0, "superseded_excluded": 1}
}
```

Formats: `compact` (default), `json`, `markdown`. `max_tokens` is enforced by
the benchmarked tokenizer; `target_model` (e.g. `gpt-4o`, `claude-sonnet-4`)
selects the encoding. Use `include_superseded: true` to include history.

### `GET /memory/unit/{id}` and `DELETE /memory/unit/{id}`

Fetch a unit with its full replacement history (or soft-delete it). Omitted
index entries point at this endpoint.

A TypeScript client lives in [`client.ts`](client.ts):

```ts
const mnemo = new Mnemo();
await mnemo.write("ledger", "The gateway timeout is 45s.");
const ctx = await mnemo.context("ledger", { query: "timeout", max_tokens: 200 });
```

## Benchmark

`benchmark.py` replays three multi-model conversations (api incident, DB
migration, recsys research), then measures compression, budgeted recall, and
staleness:

```bash
.venv/bin/python benchmark.py
```

Latest run (`cl100k_base`, 600-token context budget, rules extractor):

| sample          | raw | stored | stored ↓ | returned | returned ↓ | critical facts | stale |
| --------------- | ---:| ------:| --------:| --------:| ----------:| --------------:| ----- |
| api-incident    | 597 |    210 |      65% |      236 |        60% |          15/15 | ok    |
| db-migration    | 858 |    306 |      64% |      332 |        61% |          14/14 | ok    |
| recsys-research | 632 |    226 |      64% |      252 |        60% |          16/16 | ok    |

At a tight 150-token budget the returned contexts are 144–150 tokens and leave
an omitted index that recovers the remainder via `GET /memory/unit/{id}`.
Ingest of the 2,087 raw tokens takes roughly 90 ms in rules mode.

Rules extraction is the default; set `MNEMO_EXTRACTOR=llm` plus
`MNEMO_LLM_BASE_URL`, `MNEMO_LLM_MODEL`, and `MNEMO_LLM_API_KEY` to use an
OpenAI-compatible endpoint. LLM output is validated against the source text
(exact values must be verbatim, content-word overlap ≥ 0.5) with fallback to
the rules extractor.

## Tests

```bash
.venv/bin/python -m pytest -q
```

44 tests cover extraction/compression, supersede and paraphrase semantics,
budget-packing invariants (including a flake-resistant omitted-index check),
the HTTP API (auth, CORS, health), and concurrent writes.

CI (`.github/workflows/ci.yml`) runs on every push/PR: pytest and the
benchmark quality gate on Python 3.12 and 3.13, plus a Docker job that builds
the image and smoke-tests `/health`, write, and read inside a live container.

## Configuration

| variable | default | purpose |
| -------- | ------- | ------- |
| `MNEMO_DB` | `data/mnemo.db` | SQLite path |
| `MNEMO_API_KEY` | `mnemo-dev-key` | API key |
| `MNEMO_EXTRACTOR` | `rules` | `rules` or `llm` |
| `MNEMO_TOKENIZER` | `cl100k_base` | default encoding |
| `MNEMO_MAX_TOKENS` | `800` | default read budget |
| `MNEMO_LLM_BASE_URL` / `MNEMO_LLM_MODEL` / `MNEMO_LLM_API_KEY` | empty | LLM extractor |
| `MNEMO_EMBEDDING` | `local` | `local` (hash) or `openai` |
| `MNEMO_SUPERSEDE_JACCARD_CUE` | `0.5` | min word Jaccard to supersede when a cue is present |
| `MNEMO_SUPERSEDE_JACCARD_EXACT` | `0.4` | min stem Jaccard to supersede on exact-key collision |
| `MNEMO_CORS_ORIGINS` | empty | comma-separated extra allowed origins |
| `MNEMO_CORS_ORIGIN_REGEX` | `^chrome-extension://[a-p]{32}$` | regex for allowed origins (Chrome extensions) |

## Layout

```
mnemo/
  api.py        FastAPI endpoints and auth
  service.py    write dedupe/merge/supersede, read ranking and packing
  extract.py    rules and LLM extractors (+validation)
  units.py      sentence splitting, compression, typing, exact-token rules
  store.py      SQLite schema, FTS5, transactions
  pack.py       compact/json/markdown context packers
  tokens.py     tiktoken token counting per target model
  embed.py      local hash embedder and OpenAI-compatible embedder
tests/          pytest suite (44 tests)
benchmark.py    compression/recall benchmark over three conversation samples
client.ts       TypeScript client
extension/      Chrome MV3 scaffold (manifest, popup, background relay, JS client)
Dockerfile      multi-stage alpine image (~50 MB, non-root, /data volume)
```

## Chrome extension

`extension/` contains an MV3 extension that uses the server as shared memory:
a popup for settings and write/read, a background service worker that relays
all API calls, and an invisible content script on ChatGPT/Claude/Gemini that
auto-captures conversations and offers a one-time "Add context" prompt when
you switch models (copies a paste-ready memory block). Load it unpacked from
`chrome://extensions`; see `extension/README.md` for setup. The server allows
`chrome-extension://` origins by default (configurable via
`MNEMO_CORS_ORIGIN_REGEX` / `MNEMO_CORS_ORIGINS`).
