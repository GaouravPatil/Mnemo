import hashlib
import json
import math
import re
import urllib.request

DIM = 512
_WORD_RE = re.compile(r"[a-z0-9_]+")


def _hash_feature(feature):
    h = hashlib.md5(feature.encode("utf-8")).digest()
    idx = int.from_bytes(h[:4], "big") % DIM
    sign = 1.0 if h[4] & 1 else -1.0
    return idx, sign


class LocalEmbedder:
    name = "local-hash-v1"

    def embed(self, text):
        words = _WORD_RE.findall(text.lower())
        if not words:
            return {}
        counts = {}
        for w in words:
            idx, sign = _hash_feature("w:" + w)
            counts[idx] = counts.get(idx, 0.0) + sign
        for a, b in zip(words, words[1:]):
            idx, sign = _hash_feature("b:" + a + "_" + b)
            counts[idx] = counts.get(idx, 0.0) + 0.5 * sign
        norm = math.sqrt(sum(v * v for v in counts.values()))
        if norm == 0:
            return {}
        return {i: v / norm for i, v in counts.items()}


class ApiEmbedder:
    def __init__(self, base_url, api_key, model):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.name = f"api:{model}"
        self._fallback = LocalEmbedder()

    def embed(self, text):
        body = json.dumps({"model": self.model, "input": [text]}).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/embeddings",
            data=body,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            vec = data["data"][0]["embedding"]
        except Exception:
            return self._fallback.embed(text)
        norm = math.sqrt(sum(x * x for x in vec))
        if norm == 0:
            return {}
        return {i: x / norm for i, x in enumerate(vec) if x != 0.0}


def make_embedder(cfg):
    if cfg.embedding == "openai" and cfg.embedding_base_url:
        return ApiEmbedder(cfg.embedding_base_url, cfg.embedding_api_key, cfg.embedding_model)
    return LocalEmbedder()


def serialize(vec):
    return json.dumps({"i": list(vec.keys()), "v": [round(v, 6) for v in vec.values()]})


def deserialize(s):
    if not s:
        return {}
    try:
        data = json.loads(s)
        return dict(zip(data["i"], data["v"]))
    except Exception:
        return {}


def cosine(a, b):
    if not a or not b:
        return 0.0
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(i, 0.0) for i, v in a.items())
