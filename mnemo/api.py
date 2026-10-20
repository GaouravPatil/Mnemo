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
    language: str | None = None


class SummaryRequest(BaseModel):
    space_id: str = Field(min_length=1)
    query: str | None = None
    max_tokens: int = Field(default=400, ge=1)
    target_model: str | None = None


class UsageRow(BaseModel):
    space_id: str | None = None
    source_model: str = ""
    session_id: str = ""
    model: str = ""
    ts: float | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    reasoning_tokens: int = 0
    response_id: str = ""
    meta: dict | None = None


class UsageReportRequest(BaseModel):
    space_id: str = Field(min_length=1)
    rows: list[UsageRow]


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
            language=req.language,
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

    @app.post("/memory/summary", dependencies=[Depends(auth)])
    def summary(req: SummaryRequest):
        return svc.summary(
            req.space_id,
            query=req.query,
            max_tokens=req.max_tokens,
            target_model=req.target_model,
        )

    @app.post("/usage/report", dependencies=[Depends(auth)])
    def report_usage(req: UsageReportRequest):
        rows = []
        for row in req.rows:
            item = row.model_dump()
            item["space_id"] = item.get("space_id") or req.space_id
            rows.append(item)
        return svc.report_usage(rows)

    @app.get("/usage/summary", dependencies=[Depends(auth)])
    def usage_summary(space_id: str, since: float | None = None, until: float | None = None):
        return svc.usage_summary(space_id, since=since, until=until)

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
