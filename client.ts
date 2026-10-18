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

  write(spaceId: string, content: string | unknown[], sourceModel = "client", meta?: object) {
    return this.req("POST", "/memory/write", {
      space_id: spaceId,
      content,
      source_model: sourceModel,
      meta,
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

  unit(unitId: string) {
    return this.req("GET", `/memory/unit/${unitId}`);
  }

  deleteUnit(unitId: string) {
    return this.req("DELETE", `/memory/unit/${unitId}`);
  }
}
