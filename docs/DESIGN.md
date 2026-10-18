# Mnemo design note

## Goal

Give any model a shared, durable memory that is **small enough to fit a prompt**
and **precise enough to act on**: exact values (versions, paths, IDs, dates)
survive verbatim, stale values disappear, and everything omitted is still
discoverable.

Non-goals: being a chat log store, a vector database, or a summarizer that
rewrites facts. Mnemo never invents values; compression only removes words
around them.

## Data model

Memory is a set of small units, each with a type (`decision`, `constraint`,
`state`, `todo`, `fact`, `entity`, `question`), the compressed text, a source
sentence, keys (exact values), words (for similarity), attribute values (for
supersede keys), an embedding, and timestamps. Units are append-only from the
caller's perspective: replacement marks the old unit `superseded_by` and keeps
it for `GET /memory/unit/{id}` history.

## Write path

1. **Split** input into sentences and turns; drop chatter, acknowledgements,
   and meta narration ("I will remember...", recap preambles) unless the
   sentence carries an exact token — value-bearing text is never dropped.
2. **Compress** each sentence with deterministic rewrites (filler, copula,
   article, report leads, contractions). A guard reverts compression if any
   exact token or a negation disappears.
3. **Split atomically** on `,`/`;`/`and` only when at least one part is
   "rich" (contains an exact token, a capitalized name, a constraint, or a
   question) and no part is a bare word. Single-token values like URLs are
   allowed to split. Short qualifier tails ("hard constraint from legal") are
   appended to the preceding part instead of becoming orphan units.
4. **Classify** with priority: question > constraint > decision > todo >
   state > entity > fact.
5. **Deduplicate and merge** within the space: exact keys first, then subset
   keys, then paraphrase similarity using symmetric stem Jaccard and
   containment. Empty-key units merge only when containment is high. Merges
   never drop a key the candidate lacked; the richer text wins.
6. **Supersede** stale values: a cue ("changed to", "instead") or an
   attribute collision (same key, disjoint value) replaces the old unit,
   provided similarity or a shared key supports it. Decision-vs-decision
   replacement additionally requires a genuine choice word, so a related
   config fact cannot erase a decision. A final consolidation sweep merges
   leftover near-duplicates that were hidden by write ordering.

## Read path

1. Rank active units by normalized FTS5 keyword score, cosine similarity
   (local hash embedder or OpenAI-compatible), recency half-life, and type
   priority.
2. Pack under `max_tokens` with the tokenizer that matches the target model
   (`cl100k_base`, `o200k_base`). The compact format costs one prefix character
   per unit and a single dense header line.
3. If units do not fit, emit an omitted index (`#id label`) that points at
   `GET /memory/unit/{id}`. The packer pops included units before ever
   dropping the index, and the index degrades to IDs and then to a count so
   the budget is always respected.

## Key trade-offs

- **Rules-first extraction**: deterministic, fast (~90 ms for 2k tokens),
  works offline. An OpenAI-compatible LLM extractor is optional and validated
  against the source (exact tokens verbatim, ≥50% content-word overlap) with
  fallback to rules.
- **SQLite + FTS5**: no external services; single-file backup; the schema is
  simple enough to audit.
- **Aggressive dedupe, conservative information loss**: paraphrases merge,
  but history remains queryable and exact values/negations are guarded at
  every compression step.
- **Fixed budgets, honest metrics**: the benchmark asserts 100% critical-fact
  recall, no stale leaks, and ≥60% returned-context reduction; the latest run
  reaches 60–61% while keeping 45/45 critical facts across three samples.

Known limits: the local embedder is lexical, so semantic recall beyond shared
words relies on FTS/ranking; cross-space memory sharing and per-user retention
policies are not implemented; consolidation is O(n²) per write and suited to
spaces of hundreds of units, not millions.
