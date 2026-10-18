import json
from dataclasses import dataclass

from .units import TYPE_PREFIX

COMPACT_HEADER = [
    '#MEM T=d/c/s/t/f/e/q; exact verbatim; omitted "#id label" GET /memory/unit/id',
]

JSON_HEADER = "T text; d decision c constraint s state t todo f fact e entity q question; exact values verbatim"
MD_HEADER = "_MEM: T text (d decision, c constraint, s state, t todo, f fact, e entity, q question); exact values verbatim._"


@dataclass
class PackResult:
    context: str
    included: list
    tokens: int


def compact_line(u):
    return f"{TYPE_PREFIX[u['type']]} {u['text']}"


def label(u):
    words = list(u.get("words") or [])
    if not words:
        words = [w for w in (u.get("text") or "").split() if len(w) > 1]
    lbl = " ".join(words[:3])[:24]
    return lbl or u["id"]


def pack(rows, budget, counter, fmt="compact"):
    if fmt == "json":
        return _pack_json(rows, budget, counter)
    if fmt == "markdown":
        return _pack_markdown(rows, budget, counter)
    return _pack_compact(rows, budget, counter)


def _build_omit_line(room, omitted, counter):
    if room <= 0:
        return None

    def fits(s):
        return counter.count(s) + 1 <= room

    parts = []
    for u in omitted:
        part = ("" if not parts else " | ") + f"#{u['id']} {label(u)}"
        if fits("omitted:" + "".join(parts) + part):
            parts.append(part)
        else:
            break
    if parts:
        return "omitted: " + "".join(parts)

    parts = []
    for u in omitted:
        part = ("" if not parts else " ") + f"#{u['id']}"
        if fits("omitted:" + "".join(parts) + part):
            parts.append(part)
        else:
            break
    if parts:
        return "omitted: " + "".join(parts)

    fallback = f"omitted: {len(omitted)} units"
    return fallback if fits(fallback) else None


def _pack_compact(rows, budget, counter):
    header = "\n".join(COMPACT_HEADER)
    h = counter.count(header)
    if h > budget:
        minimal = "#MEM"
        if counter.count(minimal) <= budget:
            return PackResult(minimal, [], counter.count(minimal))
        return PackResult("", [], 0)

    included = []
    included_tokens = 0
    for u in rows:
        t = counter.count(compact_line(u)) + 1
        if h + included_tokens + t <= budget:
            included.append(u)
            included_tokens += t
        else:
            continue

    omit_line = None
    while True:
        included_ids = {u["id"] for u in included}
        omitted = [u for u in rows if u["id"] not in included_ids]
        if not omitted:
            break
        omit_line = _build_omit_line(budget - h - included_tokens, omitted, counter)
        if omit_line is not None or not included:
            break
        last = included.pop()
        included_tokens -= counter.count(compact_line(last)) + 1

    lines = [compact_line(u) for u in included]
    while True:
        body = COMPACT_HEADER + lines + ([omit_line] if omit_line else [])
        context = "\n".join(body)
        if counter.count(context) <= budget:
            break
        if lines:
            lines.pop()
            continue
        if omit_line:
            omit_line = None
            continue
        context = ""
        break
    kept = set(lines)
    included = [u for u in included if compact_line(u) in kept]
    return PackResult(context, included, counter.count(context))


def _pack_json(rows, budget, counter):
    def doc(included, omitted, mode="full"):
        if mode == "full":
            o = [[u["id"], label(u)] for u in omitted]
        elif mode == "ids":
            o = [[u["id"]] for u in omitted]
        else:
            o = []
        payload = {
            "v": 1,
            "h": JSON_HEADER,
            "u": [[TYPE_PREFIX[u["type"]], u["text"]] for u in included],
            "o": o,
        }
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

    included = []
    for u in rows:
        cand = doc(included + [u], [])
        if counter.count(cand) <= budget:
            included.append(u)

    while True:
        ids = {u["id"] for u in included}
        omitted = [u for u in rows if u["id"] not in ids]
        if not omitted:
            context = doc(included, [], "none")
            if counter.count(context) <= budget:
                return PackResult(context, included, counter.count(context))
        else:
            for mode in ("full", "ids"):
                context = doc(included, omitted, mode)
                if counter.count(context) <= budget:
                    return PackResult(context, included, counter.count(context))
        if not included:
            context = doc([], omitted, "none") if omitted else ""
            if counter.count(context) <= budget:
                return PackResult(context, included, counter.count(context))
            return PackResult("", [], 0)
        included.pop()


def _pack_markdown(rows, budget, counter):
    def doc(included, omitted, mode="full"):
        lines = [MD_HEADER]
        for u in included:
            lines.append(f"- **{TYPE_PREFIX[u['type']]}** {u['text']}")
        if omitted:
            if mode == "full":
                lines.append("- _omitted_: " + ", ".join(f"#{u['id']} {label(u)}" for u in omitted))
            elif mode == "ids":
                lines.append("- _omitted_: " + ", ".join(f"#{u['id']}" for u in omitted))
        return "\n".join(lines)

    included = []
    for u in rows:
        cand = doc(included + [u], [])
        if counter.count(cand) <= budget:
            included.append(u)

    while True:
        ids = {u["id"] for u in included}
        omitted = [u for u in rows if u["id"] not in ids]
        if not omitted:
            context = doc(included, [], "none")
            if counter.count(context) <= budget:
                return PackResult(context, included, counter.count(context))
        else:
            for mode in ("full", "ids"):
                context = doc(included, omitted, mode)
                if counter.count(context) <= budget:
                    return PackResult(context, included, counter.count(context))
        if not included:
            context = doc([], omitted, "none") if omitted else ""
            if counter.count(context) <= budget:
                return PackResult(context, included, counter.count(context))
            return PackResult("", [], 0)
        included.pop()
