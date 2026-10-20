const DEFAULT_URL = "http://127.0.0.1:8000";
const DEFAULT_KEY = "mnemo-dev-key";

export class MnemoError extends Error {}

export class Mnemo {
  constructor(
    private baseUrl: string = DEFAULT_URL,
    private apiKey: string = DEFAULT_KEY,
  ) {
    this.baseUrl = baseUrl.replace(/\/$/, "");
  }

  private async req(method: string, path: string, body?: unknown): Promise<any> {
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

  write(
    spaceId: string,
    content: string | unknown[],
    sourceModel = "client",
    meta?: object,
    language?: string,
  ) {
    return this.req("POST", "/memory/write", {
      space_id: spaceId,
      content,
      source_model: sourceModel,
      meta,
      language,
    });
  }

  read(spaceId: string, opts: { query?: string; max_tokens?: number; format?: string } = {}) {
    return this.req("POST", "/memory/read", {
      space_id: spaceId,
      query: opts.query,
      max_tokens: opts.max_tokens ?? 800,
      format: opts.format ?? "compact",
    });
  }

  async context(spaceId: string, opts: { query?: string; max_tokens?: number } = {}) {
    return (await this.read(spaceId, opts)).context as string;
  }

  summary(spaceId: string, opts: { query?: string; max_tokens?: number; target_model?: string } = {}) {
    return this.req("POST", "/memory/summary", {
      space_id: spaceId,
      query: opts.query,
      max_tokens: opts.max_tokens ?? 400,
      target_model: opts.target_model,
    });
  }

  reportUsage(spaceId: string, rows: unknown[]) {
    return this.req("POST", "/usage/report", { space_id: spaceId, rows });
  }

  usageSummary(spaceId: string, since?: number) {
    const params = new URLSearchParams({ space_id: spaceId });
    if (since !== undefined) params.set("since", String(since));
    return this.req("GET", `/usage/summary?${params.toString()}`);
  }

  unit(unitId: string) {
    return this.req("GET", `/memory/unit/${unitId}`);
  }

  deleteUnit(unitId: string) {
    return this.req("DELETE", `/memory/unit/${unitId}`);
  }
}
