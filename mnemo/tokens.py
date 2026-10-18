import functools
import re

try:
    import tiktoken
except ImportError:
    tiktoken = None

MODEL_ENCODINGS = [
    (re.compile(r"^(gpt-4o|gpt-4\.1|gpt-5|o1|o3|o4)", re.I), "o200k_base"),
    (re.compile(r"^(gpt-3\.5|gpt-4|gpt-35|gpt-4-|text-davinci|codex)", re.I), "cl100k_base"),
    (re.compile(r"^(text-embedding)", re.I), "cl100k_base"),
    (re.compile(r"^(claude|gemini|llama|mistral|qwen|deepseek|grok)", re.I), "cl100k_base"),
]


def resolve_encoding(target_model=None, default="cl100k_base"):
    if not target_model:
        return default
    for pattern, enc in MODEL_ENCODINGS:
        if pattern.search(target_model):
            return enc
    return default


@functools.lru_cache(maxsize=16)
def _load_encoder(name):
    if tiktoken is None:
        return None
    try:
        return tiktoken.get_encoding(name)
    except Exception:
        return None


_TOKEN_RE = re.compile(r"\w+|[^\w\s]")


class TokenCounter:
    def __init__(self, target_model=None, default="cl100k_base"):
        self.encoding = resolve_encoding(target_model, default)
        self.model = target_model
        self._enc = _load_encoder(self.encoding)

    @property
    def name(self):
        return self.encoding if self._enc is not None else "regex-fallback"

    def count(self, text):
        if not text:
            return 0
        if self._enc is not None:
            return len(self._enc.encode(text, disallowed_special=()))
        return len(_TOKEN_RE.findall(text))
