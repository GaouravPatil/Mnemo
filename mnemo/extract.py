import json
import re
import urllib.request

from .units import (
    CUE_ONLY,
    UNIT_TYPES,
    ExtractedUnit,
    classify,
    compress,
    content_words,
    exact_tokens,
    is_noise,
    is_open_question,
    is_tail_fragment,
    normalize,
    split_atomic,
    split_sentences,
)

LLM_PROMPT = """Extract atomic memory units from the text below.
Return ONLY a JSON array. Each item: {"type": "...", "text": "..."}.
type is one of: decision, fact, constraint, state, todo, entity, question.
text is one short dense statement that uses ONLY words from the source text.
Preserve every number, ID, path, version, date and code identifier verbatim.
Never invent facts. Merge duplicates. Max 40 units.

TEXT:
"""


def validate_llm_unit(text, source):
    text = (text or "").strip()
    if len(text) < 3:
        return False
    src_exact = exact_tokens(source)
    if not exact_tokens(text) <= src_exact:
        return False
    tw = content_words(text)
    if not tw:
        return False
    sw = content_words(source)
    overlap = len(tw & sw) / len(tw)
    return overlap >= 0.5


class RuleExtractor:
    name = "rules"

    def extract(self, turns):
        out = []
        for model, text in turns:
            for sentence in split_sentences(text):
                s = normalize(sentence)
                if len(s) < 3:
                    continue
                if is_noise(s):
                    continue
                type_ = classify(s)
                unit_text = compress(s, type_)
                if is_noise(unit_text):
                    continue
                carry = ""
                for part in split_atomic(unit_text):
                    part_type = classify(part)
                    if part_type == "fact" and type_ != "fact":
                        part_type = type_
                    cleaned = compress(part, part_type)
                    if CUE_ONLY.match(cleaned) and not exact_tokens(cleaned):
                        carry = (carry + " " + cleaned).strip()
                        continue
                    if carry:
                        cleaned = (carry + " " + cleaned).strip()
                        carry = ""
                    if is_noise(cleaned):
                        continue
                    if part_type == "question" and not is_open_question(cleaned):
                        continue
                    if is_tail_fragment(cleaned) and out and out[-1].source_text == s:
                        prev = out[-1]
                        out[-1] = ExtractedUnit(
                            type=prev.type,
                            text=f"{prev.text}, {cleaned}",
                            source_text=prev.source_text,
                            model=prev.model,
                        )
                        continue
                    out.append(ExtractedUnit(type=part_type, text=cleaned, source_text=s, model=model))
        return out


class LLMExtractor:
    def __init__(self, base_url, api_key, model, fallback=None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.fallback = fallback or RuleExtractor()
        self.name = f"llm:{model}"

    def extract(self, turns):
        chunks = []
        current = []
        size = 0
        for model, text in turns:
            if size + len(text) > 3000 and current:
                chunks.append(current)
                current = []
                size = 0
            current.append((model, text))
            size += len(text)
        if current:
            chunks.append(current)

        out = []
        for chunk in chunks:
            source = "\n".join(t for _, t in chunk)
            model = chunk[0][0]
            units = self._call_llm(source)
            valid = []
            for item in units:
                if not isinstance(item, dict):
                    continue
                type_ = str(item.get("type", "")).lower().strip()
                text = str(item.get("text", "")).strip()
                if type_ not in UNIT_TYPES or not validate_llm_unit(text, source):
                    continue
                valid.append(ExtractedUnit(type=type_, text=compress(text, type_), source_text=source, model=model))
            if valid:
                out.extend(valid)
            else:
                out.extend(self.fallback.extract(chunk))
        return out

    def _call_llm(self, source):
        body = json.dumps(
            {
                "model": self.model,
                "temperature": 0,
                "messages": [{"role": "user", "content": LLM_PROMPT + source}],
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
        except Exception:
            return []
        m = re.search(r"\[.*\]", content, re.S)
        if not m:
            return []
        try:
            return json.loads(m.group(0))
        except Exception:
            return []


def get_extractor(mode, cfg):
    if mode == "llm" and cfg.llm_base_url and cfg.llm_model:
        return LLMExtractor(cfg.llm_base_url, cfg.llm_api_key, cfg.llm_model)
    return RuleExtractor()
