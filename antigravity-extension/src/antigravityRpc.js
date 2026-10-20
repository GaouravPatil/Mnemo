const { execFileSync } = require("child_process");
const fs = require("fs");
const http = require("http");
const https = require("https");
const os = require("os");
const path = require("path");

const SERVICE = "/exa.language_server_pb.LanguageServerService/";

function run(command, args) {
  try {
    return execFileSync(command, args, { encoding: "utf8", timeout: 8000, stdio: ["ignore", "pipe", "ignore"] });
  } catch {
    return "";
  }
}

function flag(command, name) {
  const eq = command.match(new RegExp(`${name}=([^\\s]+)`));
  if (eq) return eq[1];
  const re = new RegExp(`${name}\\s+(?:"([^"]+)"|(\\S+))`);
  const m = command.match(re);
  return m ? m[1] || m[2] : "";
}

function httpJson({ scheme, port, csrf, method, body, timeoutMs = 6000 }) {
  const transport = scheme === "https" ? https : http;
  const payload = JSON.stringify(body || {});
  return new Promise((resolve, reject) => {
    const req = transport.request(
      {
        method: "POST",
        hostname: "127.0.0.1",
        port,
        path: SERVICE + method,
        headers: {
          "Content-Type": "application/json",
          "Connect-Protocol-Version": "1",
          "X-Codeium-Csrf-Token": csrf || "",
          "Content-Length": Buffer.byteLength(payload),
        },
        timeout: timeoutMs,
        rejectUnauthorized: false,
      },
      (res) => {
        const chunks = [];
        res.on("data", (c) => chunks.push(c));
        res.on("end", () => {
          const text = Buffer.concat(chunks).toString("utf8");
          if (res.statusCode < 200 || res.statusCode >= 300) {
            reject(new Error(`${res.statusCode}: ${text.slice(0, 200)}`));
            return;
          }
          try {
            resolve(text ? JSON.parse(text) : {});
          } catch (err) {
            reject(err);
          }
        });
      },
    );
    req.on("timeout", () => req.destroy(new Error("rpc timeout")));
    req.on("error", reject);
    req.write(payload);
    req.end();
  });
}

function listeningPorts(pid) {
  const ports = new Set();
  const lsof = run("lsof", ["-nP", "-iTCP", "-sTCP:LISTEN", "-a", "-p", String(pid)]);
  for (const line of lsof.split("\n")) {
    const m = line.match(/(?:127\.0\.0\.1|\[::1\]|\*):(\d+)\s+\(LISTEN\)/);
    if (m) ports.add(Number(m[1]));
  }
  if (ports.size) return [...ports];
  const ss = run("ss", ["-ltnp"]);
  for (const line of ss.split("\n")) {
    if (!line.includes(`pid=${pid},`)) continue;
    const m = line.match(/127\.0\.0\.1:(\d+)|\[::1\]:(\d+)/);
    if (m) ports.add(Number(m[1] || m[2]));
  }
  return [...ports];
}

function discoverServers() {
  const output = run("ps", ["-ax", "-o", "pid=,command="]);
  if (!output) return [];
  const servers = [];
  for (const line of output.split("\n")) {
    const m = line.match(/^\s*(\d+)\s+(.+)$/);
    if (!m) continue;
    const pid = Number(m[1]);
    const command = m[2];
    if (!/language_server/i.test(command) || !/antigravity/i.test(command)) continue;
    const appDataDir = flag(command, "--app_data_dir") || "antigravity-ide";
    const csrf = flag(command, "--csrf_token");
    const extensionPort = Number(flag(command, "--extension_server_port")) || 0;
    const extensionCsrf = flag(command, "--extension_server_csrf_token") || csrf;
    if (!csrf && !extensionPort) continue;
    servers.push({
      pid,
      command,
      appDataDir,
      csrf,
      extensionPort,
      extensionCsrf,
      workspaceId: flag(command, "--workspace_id"),
      subclient: flag(command, "--subclient_type"),
      ports: listeningPorts(pid),
    });
  }
  return servers;
}

async function rpc(server, method, body = {}) {
  const attempts = [];
  for (const port of server.ports) {
    if (port === server.extensionPort) continue;
    attempts.push({ scheme: "https", port, csrf: server.csrf });
    attempts.push({ scheme: "http", port, csrf: server.csrf });
  }
  if (server.extensionPort) {
    attempts.push({ scheme: "http", port: server.extensionPort, csrf: server.extensionCsrf });
  }
  let lastError = null;
  for (const attempt of attempts) {
    try {
      const result = await httpJson({ ...attempt, method, body });
      return { result, endpoint: `${attempt.scheme}://127.0.0.1:${attempt.port}` };
    } catch (err) {
      lastError = err;
    }
  }
  throw lastError || new Error("no Antigravity RPC endpoint available");
}

async function callMethod(method, body, servers = discoverServers(), accept = () => true) {
  for (const server of servers) {
    try {
      const { result, endpoint } = await rpc(server, method, body);
      if (accept(result)) return { server, endpoint, result };
    } catch {
      continue;
    }
  }
  return null;
}

async function getTrajectory(cascadeId, servers) {
  return callMethod(
    "GetCascadeTrajectory",
    { cascadeId },
    servers,
    (result) => Boolean(result && result.trajectory),
  );
}

async function getGeneratorMetadata(cascadeId, servers) {
  return callMethod(
    "GetCascadeTrajectoryGeneratorMetadata",
    { cascadeId },
    servers,
    (result) => Boolean(result && Array.isArray(result.generatorMetadata)),
  );
}

function conversationDirs(server) {
  const base = path.join(os.homedir(), ".gemini");
  const names = new Set([server.appDataDir, "antigravity", "antigravity-ide", "antigravity-cli"]);
  return [...names]
    .filter(Boolean)
    .map((name) => path.join(base, name, "conversations"))
    .filter((dir) => {
      try {
        return fs.statSync(dir).isDirectory();
      } catch {
        return false;
      }
    });
}

function conversationFiles(server, limit = 4) {
  const files = [];
  for (const dir of conversationDirs(server)) {
    let names = [];
    try {
      names = fs.readdirSync(dir);
    } catch {
      continue;
    }
    for (const name of names) {
      if (!/\.(pb|db)$/.test(name)) continue;
      const full = path.join(dir, name);
      try {
        const st = fs.statSync(full);
        files.push({
          path: full,
          cascadeId: name.replace(/\.(pb|db)$/, ""),
          mtime: st.mtimeMs,
          size: st.size,
        });
      } catch {
        continue;
      }
    }
  }
  files.sort((a, b) => b.mtime - a.mtime);
  return files.slice(0, limit);
}

module.exports = {
  discoverServers,
  getTrajectory,
  getGeneratorMetadata,
  conversationFiles,
  rpc,
};
