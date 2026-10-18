import secrets
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import Config
from .service import MemoryService


class WriteRequest(BaseModel):
    space_id: str = Field(min_length=1)
    content: str | list
    source_model: str = "unknown"
    meta: dict | None = None
    extract: Literal["rules", "llm"] | None = None


class ReadRequest(BaseModel):
    space_id: str = Field(min_length=1)
    query: str | None = None
    max_tokens: int = Field(default=800, ge=1)
    format: Literal["compact", "json", "markdown"] = "compact"
    types: list[str] | None = None
    target_model: str | None = None
    encoding: str | None = None
    include_superseded: bool = False


def create_app(cfg=None):
    cfg = cfg or Config.from_env()
    svc = MemoryService(cfg)
    app = FastAPI(title="Mnemo", version="1.0.0")

    if cfg.cors_origins or cfg.cors_origin_regex:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(cfg.cors_origins),
            allow_origin_regex=cfg.cors_origin_regex or None,
            allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
            allow_headers=["Content-Type", "X-API-Key"],
            allow_credentials=False,
        )

    def auth(x_api_key: str = Header(default="")):
        if not secrets.compare_digest(x_api_key, cfg.api_key):
            raise HTTPException(status_code=401, detail="unauthorized")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/memory/write", dependencies=[Depends(auth)])
    def write(req: WriteRequest):
        return svc.write(
            req.space_id,
            req.content,
            source_model=req.source_model,
            meta=req.meta,
            extract=req.extract,
        )

    @app.post("/memory/read", dependencies=[Depends(auth)])
    def read(req: ReadRequest):
        return svc.read(
            req.space_id,
            query=req.query,
            max_tokens=req.max_tokens,
            format=req.format,
            types=req.types,
            target_model=req.target_model,
            encoding=req.encoding,
            include_superseded=req.include_superseded,
        )

    @app.get("/memory/unit/{unit_id}", dependencies=[Depends(auth)])
    def get_unit(unit_id: str):
        unit = svc.get_unit(unit_id)
        if unit is None:
            raise HTTPException(status_code=404, detail="unit_not_found")
        return unit

    @app.delete("/memory/unit/{unit_id}", dependencies=[Depends(auth)])
    def delete_unit(unit_id: str):
        if not svc.delete_unit(unit_id):
            raise HTTPException(status_code=404, detail="unit_not_found")
        return {"deleted": unit_id}

    return app
