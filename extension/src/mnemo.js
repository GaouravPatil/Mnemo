const DEFAULT_URL = "http://127.0.0.1:8000";

export class MnemoError extends Error {}

export class Mnemo {
  constructor(baseUrl = DEFAULT_URL, apiKey = "") {
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.apiKey = apiKey;
  }

  async req(method, path, body) {
    const res = await fetch(this.baseUrl + path, {
      method,
      headers: { "Content-Type": "application/json", "X-API-Key": this.apiKey },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!res.ok) throw new MnemoError(`${res.status}: ${await res.text()}`);
    const text = await res.text();
    return text ? JSON.parse(text) : {};
  }

  health() {
    return this.req("GET", "/health");
  }

  write(spaceId, content, sourceModel = "chrome-extension", meta) {
    return this.req("POST", "/memory/write", {
      space_id: spaceId,
      content,
      source_model: sourceModel,
      meta,
    });
  }

  read(spaceId, opts = {}) {
    return this.req("POST", "/memory/read", {
      space_id: spaceId,
      query: opts.query,
      max_tokens: opts.maxTokens ?? 800,
      format: opts.format ?? "compact",
    });
  }

  async context(spaceId, opts = {}) {
    return (await this.read(spaceId, opts)).context;
  }

  unit(unitId) {
    return this.req("GET", `/memory/unit/${unitId}`);
  }

  deleteUnit(unitId) {
    return this.req("DELETE", `/memory/unit/${unitId}`);
  }
}
