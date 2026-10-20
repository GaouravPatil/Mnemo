const http = require("http");
const https = require("https");

class MnemoError extends Error {}

class MnemoClient {
  constructor(baseUrl, apiKey, timeoutMs = 15000) {
    this.baseUrl = String(baseUrl || "http://127.0.0.1:8000").replace(/\/$/, "");
    this.apiKey = apiKey || "";
    this.timeoutMs = timeoutMs;
  }

  request(method, path, body) {
    const url = new URL(this.baseUrl + path);
    const transport = url.protocol === "https:" ? https : http;
    const payload = body === undefined ? null : JSON.stringify(body);
    const headers = { "X-API-Key": this.apiKey };
    if (payload !== null) {
      headers["Content-Type"] = "application/json";
      headers["Content-Length"] = Buffer.byteLength(payload);
    }
    return new Promise((resolve, reject) => {
      const req = transport.request(
        {
          method,
          hostname: url.hostname,
          port: url.port || (url.protocol === "https:" ? 443 : 80),
          path: url.pathname + url.search,
          headers,
          timeout: this.timeoutMs,
          rejectUnauthorized: false,
        },
        (res) => {
          const chunks = [];
          res.on("data", (chunk) => chunks.push(chunk));
          res.on("end", () => {
            const text = Buffer.concat(chunks).toString("utf8");
            if (res.statusCode < 200 || res.statusCode >= 300) {
              reject(new MnemoError(`${res.statusCode}: ${text}`));
              return;
            }
            try {
              resolve(text ? JSON.parse(text) : {});
            } catch (err) {
              reject(new MnemoError(`invalid JSON: ${err.message}`));
            }
          });
        },
      );
      req.on("timeout", () => req.destroy(new Error("request timed out")));
      req.on("error", reject);
      if (payload !== null) req.write(payload);
      req.end();
    });
  }

  health() {
    return this.request("GET", "/health");
  }

  write(space, content, sourceModel, meta, language) {
    return this.request("POST", "/memory/write", {
      space_id: space,
      content,
      source_model: sourceModel || "antigravity",
      meta,
      language,
    });
  }

  read(space, opts = {}) {
    return this.request("POST", "/memory/read", {
      space_id: space,
      query: opts.query,
      max_tokens: opts.maxTokens || 800,
      format: opts.format || "markdown",
      target_model: opts.targetModel,
    });
  }

  summary(space, opts = {}) {
    return this.request("POST", "/memory/summary", {
      space_id: space,
      query: opts.query,
      max_tokens: opts.maxTokens || 400,
      target_model: opts.targetModel,
    });
  }

  reportUsage(space, rows) {
    return this.request("POST", "/usage/report", { space_id: space, rows });
  }

  usageSummary(space, since) {
    const params = new URLSearchParams({ space_id: space });
    if (since !== undefined && since !== null) params.set("since", String(since));
    return this.request("GET", `/usage/summary?${params.toString()}`);
  }
}

module.exports = { MnemoClient, MnemoError };
