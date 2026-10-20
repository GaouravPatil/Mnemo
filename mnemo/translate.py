import json
import re
import urllib.request

from .units import exact_tokens

TRANSLATE_PROMPT = """Translate the text below to {language}.
Preserve every number, ID, path, URL, version, date, code identifier and quoted
string exactly as written. Do not add explanations, notes or extra content.
Return only the translated text. If it is already in {language}, return it unchanged.

TEXT:
"""

_NON_ASCII = re.compile(r"[^\x00-\x7F]")
_FOREIGN_WORDS = {
    "el", "la", "los", "las", "una", "que", "para", "con", "por", "del", "como",
    "le", "les", "des", "une", "est", "dans", "pour", "avec", "pas", "sur",
    "der", "die", "das", "und", "ist", "nicht", "mit", "für", "auf", "ein",
    "il", "lo", "gli", "che", "per", "con", "non", "una", "sono",
    "não", "uma", "para", "com", "isso", "você", "ele", "ela",
    "en", "het", "een", "van", "niet", "met", "voor",
}


def needs_translation(text, language="English"):
    if not text or (language or "").lower() != "english":
        return bool(text)
    if _NON_ASCII.search(text):
        return True
    words = re.findall(r"[A-Za-zÀ-ÿ]+", text.lower())
    if not words:
        return False
    foreign = sum(1 for w in words if w in _FOREIGN_WORDS)
    return foreign >= 2 and foreign / len(words) >= 0.08


def _extract_content(data):
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return ""
    if isinstance(content, list):
        return "".join(str(p.get("text", "")) if isinstance(p, dict) else str(p) for p in content)
    return str(content or "")


class LLMTranslator:
    def __init__(self, base_url, api_key, model, language="English"):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.language = language
        self.name = f"llm:{model}"

    def translate(self, text):
        if not needs_translation(text, self.language):
            return text, False
        prompt = TRANSLATE_PROMPT.format(language=self.language)
        body = json.dumps(
            {
                "model": self.model,
                "temperature": 0,
                "messages": [{"role": "user", "content": prompt + text}],
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            out = _extract_content(data).strip()
        except Exception:
            return text, False
        if not out or not exact_tokens(out) <= exact_tokens(text):
            return text, False
        return out, True


def get_translator(cfg, language=None):
    target = (language or cfg.output_language or "").strip()
    if not target:
        return None
    if not (cfg.llm_base_url and cfg.llm_model):
        return None
    return LLMTranslator(cfg.llm_base_url, cfg.llm_api_key, cfg.llm_model, target)
