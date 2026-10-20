import time

from .config import Config
from .embed import cosine, deserialize, make_embedder, serialize
from .extract import get_extractor
from .pack import compact_line, label, pack
from .store import Store
from .tokens import TokenCounter
from .translate import get_translator
from .units import (
    CHOICE_CUE,
    SUPERSEDE_CUE,
    TYPE_PRIORITY,
    attr_keys,
    content_words,
    exact_tokens,
    fingerprint,
    jaccard,
    new_unit_id,
    nonnumeric,
    split_turns,
    stems,
)

MERGEABLE = {"fact", "state", "todo", "decision", "constraint"}


class MemoryService:
    def __init__(self, cfg=None):
        self.cfg = cfg or Config.from_env()
        self.store = Store(self.cfg.db_path)
        self.embedder = make_embedder(self.cfg)

    def counter(self, target_model=None, encoding=None):
        return TokenCounter(target_model, encoding or self.cfg.default_tokenizer)

    def write(
        self,
        space_id,
        content,
        source_model="unknown",
        meta=None,
        extract=None,
        language=None,
    ):
        turns = split_turns(content)
        translator = get_translator(self.cfg, language)
        translated = 0
        if translator is not None:
            converted = []
            for model, text in turns:
                out, changed = translator.translate(text)
                translated += int(changed)
                converted.append((model, out))
            turns = converted
        raw = "\n".join(t for _, t in turns)
        mode = extract or self.cfg.extractor
        extracted = get_extractor(mode, self.cfg).extract(turns)
        now = time.time()
        results = []
        superseded = []
        with self.store.write_tx() as con:
            write_id = self.store.insert_write(con, space_id, source_model or "unknown", now, raw, meta)
            active = {u["id"]: u for u in self.store.list_active(space_id, con=con)}
            for eu in extracted:
                out = self._write_one(con, space_id, eu, source_model, write_id, now, active)
                if out is None:
                    continue
                results.append(out[0])
                superseded.extend(out[1])
            superseded.extend(self._consolidate(con, space_id, active, now))
        out = {
            "space_id": space_id,
            "write_id": write_id,
            "written": results,
            "superseded": superseded,
            "language": (translator.language if translator else None),
            "translated": translated,
        }
        if language and translator is None:
            out["language_warning"] = (
                "translation requested but MNEMO_LLM_BASE_URL/MNEMO_LLM_MODEL are not configured"
            )
        return out

    def _write_one(self, con, space_id, eu, request_model, write_id, now, active):
        text = (eu.text or "").strip()
        if len(text) < 3:
            return None
        model = eu.model or request_model or "unknown"
        ex = exact_tokens(text)
        words = content_words(text)
        nwords = nonnumeric(words)
        attr = attr_keys(text)
        fp = fingerprint(text)
        vec = serialize(self.embedder.embed(text))
        merger = eu.type in MERGEABLE

        def payload():
            return {
                "text": text,
                "fingerprint": fp,
                "keys": sorted(ex),
                "words": sorted(words),
                "attr": attr,
                "source_text": eu.source_text,
                "source_model": model,
                "updated_at": now,
                "embed_model": self.embedder.name,
                "embedding": vec,
            }

        def richer_than(cand):
            if len(ex) != len(set(cand["keys"])):
                return len(ex) > len(set(cand["keys"]))
            return len(words) > len(set(cand["words"]))

        def collisions(cand):
            return [k for k in set(attr) & set(cand["attr"]) if set(attr[k]).isdisjoint(set(cand["attr"][k]))]

        # 1. identical text: update in place or count as duplicate
        for cand in list(active.values()):
            if cand["fingerprint"] != fp:
                continue
            if richer_than(cand):
                update = payload()
                self.store.update_unit(con, cand["id"], update)
                cand.update(update)
                status = "updated"
            else:
                self.store.bump_merges(con, cand["id"])
                status = "duplicate"
            return ({"id": cand["id"], "type": cand["type"], "text": cand["text"], "status": status}, [])

        # 2. merge paraphrases that carry the same exact keys
        best_merge = None
        if merger or eu.type in ("question",):
            for cand in active.values():
                if cand["type"] not in MERGEABLE and cand["type"] != eu.type:
                    continue
                if collisions(cand):
                    continue
                ck = set(cand["keys"])
                cn = nonnumeric(set(cand["words"]))
                sn = stems(nwords)
                scn = stems(cn)
                overlap = len(sn & scn)
                if overlap < 1:
                    continue
                containment = overlap / max(1, min(len(sn), len(scn)))
                sjac = overlap / len(sn | scn)
                jac = jaccard(words, set(cand["words"]))
                upgrade = False
                if ex and ex == ck:
                    if not (
                        sjac >= 0.45
                        or overlap >= 3
                        or (overlap >= 2 and containment >= 0.3)
                        or containment >= 1.0
                    ):
                        continue
                elif not ex and ck and containment >= 1.0 and sjac >= 0.4:
                    pass
                elif ex and not ck and containment >= 1.0 and sjac >= 0.4:
                    upgrade = True
                elif ck and ck < ex and (
                    containment >= 1.0 or (containment >= 0.3 and sjac >= 0.15)
                ):
                    upgrade = True
                elif ex and ex < ck and (
                    containment >= 1.0 or (containment >= 0.3 and sjac >= 0.15)
                ):
                    pass
                elif not ex and not ck and (
                    (len(sn ^ scn) <= 1 and jac >= 0.6)
                    or (overlap >= 3 and containment >= 0.5 and sjac >= 0.4)
                    or (containment >= 1.0 and sjac >= 0.4)
                ):
                    pass
                else:
                    continue
                score = (overlap, containment, sjac)
                if best_merge is None or score > best_merge[0]:
                    best_merge = (score, cand, upgrade)
        if best_merge is not None:
            _, cand, upgrade = best_merge
            if upgrade or richer_than(cand):
                update = payload()
                self.store.update_unit(con, cand["id"], update)
                cand.update(update)
                status = "updated"
            else:
                self.store.bump_merges(con, cand["id"])
                status = "duplicate"
            absorbed = []
            tgt_keys = set(cand["keys"])
            tgt_stems = stems(nonnumeric(set(cand["words"])))
            for other in list(active.values()):
                if other["id"] == cand["id"] or other["type"] not in MERGEABLE:
                    continue
                okeys = set(other["keys"])
                owords = stems(nonnumeric(set(other["words"])))
                if okeys and okeys <= tgt_keys and owords and owords <= tgt_stems and not collisions(other):
                    self.store.supersede(con, other["id"], cand["id"], now)
                    active.pop(other["id"], None)
                    absorbed.append(other["id"])
            return ({"id": cand["id"], "type": cand["type"], "text": cand["text"], "status": status}, absorbed)

        # 3. contradiction: supersede stale units, keep history
        cue = bool(SUPERSEDE_CUE.search(text) or SUPERSEDE_CUE.search(eu.source_text or ""))
        doomed = []
        best_id, best_score = None, (-1.0, 0.0)
        if eu.type not in ("question", "entity"):
            sw = stems(nwords)
            for cand in active.values():
                if cand["type"] in ("question", "entity"):
                    continue
                cw = set(cand["words"])
                cn = nonnumeric(cw)
                shared = sw & stems(cn)
                nj = jaccard(stems(nwords), stems(cn))
                jac = jaccard(words, cw)
                col = collisions(cand)
                if col:
                    eligible = (cue and (shared or nj >= 0.2)) or nj >= self.cfg.supersede_jaccard_exact
                elif cue:
                    eligible = jac >= self.cfg.supersede_jaccard_cue or (
                        bool(CHOICE_CUE.search(text))
                        and eu.type == "decision"
                        and cand["type"] == "decision"
                        and bool(shared)
                    )
                else:
                    eligible = False
                if not eligible:
                    continue
                doomed.append(cand["id"])
                score = (jac, cand["created_at"])
                if score > best_score:
                    best_id, best_score = cand["id"], score
        if best_id is None:
            doomed = []

        uid = new_unit_id(set(active))
        unit = {
            "id": uid,
            "space_id": space_id,
            "type": eu.type,
            "text": text,
            "fingerprint": fp,
            "keys": sorted(ex),
            "words": sorted(words),
            "attr": attr,
            "source_text": eu.source_text,
            "source_model": model,
            "write_id": write_id,
            "created_at": now,
            "updated_at": now,
            "embed_model": self.embedder.name,
            "embedding": vec,
        }
        self.store.insert_unit(con, unit)
        for old_id in doomed:
            self.store.supersede(con, old_id, uid, now)
            active.pop(old_id, None)
        unit["merges"] = 0
        active[uid] = unit
        return (
            {"id": uid, "type": eu.type, "text": text, "status": "new", "supersedes": sorted(doomed)},
            sorted(doomed),
        )

    def _similar_units(self, u, v):
        au, av = u["attr"], v["attr"]
        for k in set(au) & set(av):
            if set(au[k]).isdisjoint(set(av[k])):
                return False
        uk, vk = set(u["keys"]), set(v["keys"])
        un = stems(nonnumeric(set(u["words"])))
        vn = stems(nonnumeric(set(v["words"])))
        if not un or not vn:
            return False
        overlap = len(un & vn)
        cont = overlap / max(1, min(len(un), len(vn)))
        sjac = overlap / len(un | vn)
        if uk and vk:
            if uk == vk:
                return overlap >= 3 or (overlap >= 2 and cont >= 0.4)
            if uk < vk or vk < uk:
                return cont >= 0.6 or (cont >= 0.3 and sjac >= 0.15)
            return False
        if not uk and not vk:
            if cont >= 1.0 and sjac >= 0.4:
                return True
            return overlap >= 3 and cont >= 0.6 and sjac >= 0.45
        return False

    @staticmethod
    def _pick_pair(u, v):
        uk, vk = len(set(u["keys"])), len(set(v["keys"]))
        if uk != vk:
            return (u, v) if uk < vk else (v, u)
        if len(u["words"]) != len(v["words"]):
            return (u, v) if len(u["words"]) < len(v["words"]) else (v, u)
        if u["created_at"] != v["created_at"]:
            return (u, v) if u["created_at"] < v["created_at"] else (v, u)
        return (v, u)

    def _consolidate(self, con, space_id, active, now):
        absorbed = []
        changed = True
        while changed:
            changed = False
            items = [u for u in active.values() if u["type"] in MERGEABLE]
            for i, u in enumerate(items):
                if changed:
                    break
                for v in items[i + 1 :]:
                    if u["id"] not in active or v["id"] not in active or u["type"] != v["type"]:
                        continue
                    if not self._similar_units(u, v):
                        continue
                    loser, winner = self._pick_pair(u, v)
                    if set(loser["keys"]) - set(winner["keys"]):
                        continue
                    self.store.supersede(con, loser["id"], winner["id"], now)
                    active.pop(loser["id"], None)
                    absorbed.append(loser["id"])
                    changed = True
                    break
        return absorbed

    def read(
        self,
        space_id,
        query=None,
        max_tokens=None,
        format="compact",
        types=None,
        target_model=None,
        encoding=None,
        include_superseded=False,
    ):
        budget = int(max_tokens or self.cfg.default_max_tokens)
        counter = self.counter(target_model, encoding)
        superseded_excluded = 0 if include_superseded else self.store.count_superseded(space_id)
        rows = self.store.list_active(space_id, include_superseded=include_superseded)
        if types:
            wanted = set(types)
            rows = [u for u in rows if u["type"] in wanted]
        kw = self.store.keyword_scores(space_id, query) if query else {}
        qvec = self.embedder.embed(query) if query else {}
        ranked = self._rank(rows, query, kw, qvec)
        result = pack(ranked, budget, counter, format)
        included_ids = [u["id"] for u in result.included]
        included_set = set(included_ids)
        omitted = [
            {"id": u["id"], "type": u["type"], "label": label(u)}
            for u in ranked
            if u["id"] not in included_set
        ]
        all_active = self.store.list_active(space_id)
        stored_text = "\n".join(compact_line(u) for u in all_active)
        return {
            "space_id": space_id,
            "format": format,
            "query": query,
            "context": result.context,
            "tokens": result.tokens,
            "budget": budget,
            "tokenizer": counter.name,
            "included": included_ids,
            "omitted": omitted,
            "stats": {
                "units_total": len(all_active),
                "units_included": len(included_ids),
                "units_omitted": len(omitted),
                "superseded_excluded": superseded_excluded,
                "stored_tokens": counter.count(stored_text),
                "returned_tokens": result.tokens,
                "budget": budget,
            },
        }

    def summary(self, space_id, query=None, max_tokens=400, target_model=None):
        active = self.store.list_active(space_id)
        all_rows = self.store.list_active(space_id, include_superseded=True)
        superseded = len(all_rows) - len(active)
        counts = {}
        for u in active:
            counts[u["type"]] = counts.get(u["type"], 0) + 1
        read = self.read(
            space_id,
            query=query,
            max_tokens=max_tokens,
            format="markdown",
            target_model=target_model,
        )
        stats = read["stats"]
        exact_units = sum(1 for u in active if u["keys"])
        merges = sum(int(u.get("merges") or 0) for u in active)
        now = time.time()
        newest = max((u["updated_at"] for u in active), default=None)
        quality = {
            "precision_proxy": round(exact_units / len(active), 3) if active else 0.0,
            "exact_key_coverage": round(exact_units / len(active), 3) if active else 0.0,
            "dedupe_ratio": round(merges / (merges + len(active)), 3) if active else 0.0,
            "supersede_ratio": round(superseded / (superseded + len(active)), 3)
            if active or superseded
            else 0.0,
            "avg_unit_tokens": round(stats["stored_tokens"] / len(active), 2) if active else 0.0,
            "freshness_hours": round((now - newest) / 3600, 2) if newest else None,
        }
        writes = self.store.count_writes(space_id)
        header = [
            f"# Mnemo summary: {space_id}",
            f"{len(active)} active units, {superseded} superseded, "
            f"{writes} writes.",
            "types: " + (", ".join(f"{k}={v}" for k, v in sorted(counts.items())) or "none"),
            f"stored context: {stats['stored_tokens']} tokens; "
            f"precision proxy: {quality['precision_proxy']:.0%} exact-key coverage.",
        ]
        return {
            "space_id": space_id,
            "query": query,
            "summary": "\n".join(header) + "\n\n" + read["context"],
            "writes": writes,
            "counts": counts,
            "stats": stats,
            "quality": quality,
        }

    def report_usage(self, rows):
        inserted = 0
        for row in rows:
            row = dict(row)
            if row.get("ts") is None:
                row["ts"] = time.time()
            if self.store.insert_usage(row):
                inserted += 1
        return {"received": len(rows), "inserted": inserted, "deduplicated": len(rows) - inserted}

    def usage_summary(self, space_id, since=None, until=None):
        return self.store.usage_summary(space_id, since=since, until=until)

    def _rank(self, rows, query, kw, qvec):
        now = time.time()
        vals = list(kw.values())
        kmin = min(vals) if vals else 0.0
        kmax = max(vals) if vals else 0.0
        scored = []
        for u in rows:
            if query:
                raw = kw.get(u["id"], 0.0)
                k = (raw - kmin) / (kmax - kmin) if kmax > kmin else (1.0 if raw > 0 else 0.0)
                e = 0.0
                if u.get("embed_model") == self.embedder.name:
                    e = max(0.0, cosine(qvec, deserialize(u.get("embedding", ""))))
            else:
                k = e = 0.0
            age_h = max(0.0, now - u["created_at"]) / 3600.0
            rec = 0.5 ** (age_h / self.cfg.recency_half_life_h)
            prio = TYPE_PRIORITY.get(u["type"], 0.4)
            s = (
                self.cfg.w_keyword * k
                + self.cfg.w_embedding * e
                + self.cfg.w_recency * rec
                + self.cfg.w_priority * prio
            )
            scored.append((s, u["created_at"], u))
        scored.sort(key=lambda x: (-x[0], -x[1]))
        return [u for _, _, u in scored]

    def get_unit(self, unit_id):
        u = self.store.get_unit(unit_id)
        if u is None:
            return None
        history = []
        seen = {u["id"]}
        cur = u
        while cur.get("superseded_by") and cur["superseded_by"] not in seen and len(history) < 20:
            nxt = self.store.get_unit(cur["superseded_by"], include_deleted=True)
            if nxt is None:
                break
            seen.add(nxt["id"])
            history.append({"id": nxt["id"], "text": nxt["text"], "type": nxt["type"], "relation": "replaced_by"})
            cur = nxt
        cur = u
        while len(history) < 20:
            olds = self.store.find_superseded_by(cur["id"])
            if not olds:
                break
            cur = self.store.get_unit(olds[0]["id"], include_deleted=True)
            if cur is None or cur["id"] in seen:
                break
            seen.add(cur["id"])
            history.append({"id": cur["id"], "text": cur["text"], "type": cur["type"], "relation": "replaced"})
        write = self.store.get_write(u["write_id"])
        return {
            "id": u["id"],
            "space_id": u["space_id"],
            "type": u["type"],
            "text": u["text"],
            "keys": u["keys"],
            "source_text": u["source_text"],
            "source_model": u["source_model"],
            "timestamp": u["created_at"],
            "updated_at": u["updated_at"],
            "version": u["version"],
            "superseded_by": u["superseded_by"],
            "deleted": bool(u["deleted"]),
            "history": history,
            "write": {
                "id": write["id"],
                "source_model": write["source_model"],
                "timestamp": write["ts"],
                "content": write["content"],
                "meta": write["meta"],
            }
            if write
            else None,
        }

    def delete_unit(self, unit_id):
        return self.store.soft_delete(unit_id)
