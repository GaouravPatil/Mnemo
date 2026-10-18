FROM python:3.13-alpine AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python:3.13-alpine

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    MNEMO_DB=/data/mnemo.db \
    MNEMO_HOST=0.0.0.0 \
    MNEMO_PORT=8000 \
    MNEMO_RELOAD=0

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY mnemo/ ./mnemo/

RUN adduser -D -H -u 1000 mnemo \
    && mkdir -p /data \
    && chown -R mnemo:mnemo /data /app

USER mnemo

EXPOSE 8000
VOLUME ["/data"]

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request, sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

CMD ["python", "-m", "mnemo"]
