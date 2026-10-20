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

  write(spaceId, content, sourceModel = "chrome-extension", meta, language) {
    return this.req("POST", "/memory/write", {
      space_id: spaceId,
      content,
      source_model: sourceModel,
      meta,
      language,
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

  summary(spaceId, opts = {}) {
    return this.req("POST", "/memory/summary", {
      space_id: spaceId,
      query: opts.query,
      max_tokens: opts.maxTokens ?? 400,
      target_model: opts.targetModel,
    });
  }

  reportUsage(spaceId, rows) {
    return this.req("POST", "/usage/report", { space_id: spaceId, rows });
  }

  usageSummary(spaceId, since, until) {
    const params = new URLSearchParams({ space_id: spaceId });
    if (since !== undefined) params.set("since", String(since));
    if (until !== undefined) params.set("until", String(until));
    return this.req("GET", `/usage/summary?${params.toString()}`);
  }

  unit(unitId) {
    return this.req("GET", `/memory/unit/${unitId}`);
  }

  deleteUnit(unitId) {
    return this.req("DELETE", `/memory/unit/${unitId}`);
  }
}
