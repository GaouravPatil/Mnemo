import os
from dataclasses import dataclass, field


def _f(name, default):
    v = os.environ.get(name)
    return float(v) if v is not None else default


def _s(name, default):
    return os.environ.get(name, default)


@dataclass
class Config:
    db_path: str = "data/mnemo.db"
    api_key: str = "mnemo-dev-key"

    extractor: str = "rules"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    output_language: str = "English"

    embedding: str = "local"
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"

    default_tokenizer: str = "cl100k_base"
    default_max_tokens: int = 800

    recency_half_life_h: float = 72.0
    w_keyword: float = 0.45
    w_embedding: float = 0.25
    w_recency: float = 0.15
    w_priority: float = 0.15

    supersede_jaccard_cue: float = 0.5
    supersede_jaccard_exact: float = 0.4

    cors_origins: tuple[str, ...] = ()
    cors_origin_regex: str = r"^chrome-extension://[a-p]{32}$"

    @classmethod
    def from_env(cls, **overrides):
        cfg = cls(
            db_path=_s("MNEMO_DB", "data/mnemo.db"),
            api_key=_s("MNEMO_API_KEY", "mnemo-dev-key"),
            extractor=_s("MNEMO_EXTRACTOR", "rules"),
            llm_base_url=_s("MNEMO_LLM_BASE_URL", ""),
            llm_api_key=_s("MNEMO_LLM_API_KEY", ""),
            llm_model=_s("MNEMO_LLM_MODEL", ""),
            output_language=_s("MNEMO_OUTPUT_LANGUAGE", "English"),
            embedding=_s("MNEMO_EMBEDDING", "local"),
            embedding_base_url=_s("MNEMO_EMBEDDING_BASE_URL", ""),
            embedding_api_key=_s("MNEMO_EMBEDDING_API_KEY", ""),
            embedding_model=_s("MNEMO_EMBEDDING_MODEL", "text-embedding-3-small"),
            default_tokenizer=_s("MNEMO_TOKENIZER", "cl100k_base"),
            default_max_tokens=int(_s("MNEMO_MAX_TOKENS", "800")),
            recency_half_life_h=_f("MNEMO_RECENCY_HALF_LIFE_H", 72.0),
            supersede_jaccard_cue=_f("MNEMO_SUPERSEDE_JACCARD_CUE", 0.5),
            supersede_jaccard_exact=_f("MNEMO_SUPERSEDE_JACCARD_EXACT", 0.4),
            cors_origins=tuple(
                o.strip() for o in _s("MNEMO_CORS_ORIGINS", "").split(",") if o.strip()
            ),
            cors_origin_regex=_s("MNEMO_CORS_ORIGIN_REGEX", r"^chrome-extension://[a-p]{32}$"),
        )
        for k, v in overrides.items():
            if hasattr(cfg, k):
                setattr(cfg, k, v)
            else:
                raise ValueError(f"unknown config key: {k}")
        return cfg
