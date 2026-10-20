const {
  conversationFiles,
  discoverServers,
  getGeneratorMetadata,
  getTrajectory,
} = require("./antigravityRpc");

const MAX_MESSAGE_CHARS = 8000;
const USAGE_SCAN_LIMIT = 100;
let languageWarningLogged = false;

function textOf(value) {
  if (typeof value === "string") return value.trim();
  if (Array.isArray(value)) {
    return value
      .map((item) => (item && typeof item === "object" ? item.text || "" : String(item || "")))
      .filter(Boolean)
      .join("\n")
      .trim();
  }
  return "";
}

function stepText(step) {
  if (!step || !step.type) return null;
  if (step.type === "CORTEX_STEP_TYPE_USER_INPUT") {
    const input = step.userInput || {};
    const text = textOf(input.userResponse) || textOf(input.items);
    return text ? { role: "user", text } : null;
  }
  if (step.type === "CORTEX_STEP_TYPE_PLANNER_RESPONSE") {
    const planner = step.plannerResponse || {};
    const text = textOf(planner.response) || textOf(planner.modifiedResponse);
    return text ? { role: "assistant", text } : null;
  }
  return null;
}

function modelMap(metadata) {
  const map = new Map();
  for (const entry of metadata || []) {
    const model = entry.responseModel || entry.chatModel?.model || "";
    for (const index of entry.stepIndices || []) map.set(index, model);
  }
  return map;
}

function extractMessages(steps, offset, maxChars, models) {
  const messages = [];
  const seen = new Set();
  let used = 0;
  let index = Math.max(0, offset || 0);
  for (; index < steps.length; index += 1) {
    const step = steps[index];
    const found = stepText(step);
    if (!found) continue;
    const text = found.text.slice(0, Math.max(1, Math.min(MAX_MESSAGE_CHARS, maxChars - used)));
    if (!text) continue;
    if (used + text.length > maxChars) break;
    const key = found.role + "\n" + text;
    if (seen.has(key)) continue;
    seen.add(key);
    used += text.length;
    const model = found.role === "user" ? "antigravity:user" : `antigravity:${models.get(index) || "assistant"}`;
    messages.push({ model, text });
  }
  return { messages, nextOffset: index };
}

function toInt(value) {
  const n = Number.parseInt(String(value ?? "0"), 10);
  return Number.isFinite(n) ? n : 0;
}

function usageRows(cascadeId, metadata, sourceModel) {
  const rows = [];
  const seen = new Set();
  for (const entry of (metadata || []).slice(-USAGE_SCAN_LIMIT)) {
    const chat = entry.chatModel || entry;
    const model = entry.responseModel || chat.responseModel || chat.model || chat.usage?.model || "unknown";
    const usages = [];
    if (chat.usage) usages.push(chat.usage);
    for (const retry of chat.retryInfos || []) {
      if (retry && retry.usage) usages.push(retry.usage);
    }
    for (const usage of usages) {
      const responseId = String(usage.responseId || "");
      const input = toInt(usage.inputTokens);
      const output = toInt(usage.outputTokens);
      const cacheRead = toInt(usage.cacheReadTokens);
      const reasoning = toInt(usage.thinkingOutputTokens);
      if (!input && !output && !cacheRead && !reasoning) continue;
      const fallbackId = `${cascadeId}:${model}:${input}:${output}:${cacheRead}:${reasoning}`;
      const id = responseId || fallbackId;
      if (seen.has(id)) continue;
      seen.add(id);
      const rawTs = usage.createdAt || chat.chatStartMetadata?.createdAt;
      const parsed = rawTs ? Date.parse(rawTs) : NaN;
      rows.push({
        source_model: sourceModel,
        session_id: cascadeId,
        model,
        ts: Number.isFinite(parsed) ? parsed / 1000 : undefined,
        input_tokens: input,
        output_tokens: output,
        cache_read_tokens: cacheRead,
        cache_write_tokens: 0,
        reasoning_tokens: reasoning,
        response_id: id,
        meta: { api_provider: usage.apiProvider || "", cascade_id: cascadeId },
      });
    }
  }
  return rows;
}

async function captureOnce({
  client,
  space,
  state,
  log,
  maxChars = 20000,
  language = "English",
  maxFiles = 3,
}) {
  const servers = discoverServers();
  if (!servers.length) return { skipped: "Antigravity language server is not running" };
  const files = conversationFiles(servers[0], maxFiles);
  if (!files.length) return { skipped: "no Antigravity conversation files found" };

  let messages = 0;
  let units = 0;
  let usage = 0;
  let conversations = 0;

  for (const file of files) {
    const offsetKey = `capture.offset.${file.cascadeId}`;
    const mtimeKey = `capture.mtime.${file.cascadeId}`;
    const stepsKey = `capture.steps.${file.cascadeId}`;
    let offset = state.get(offsetKey, 0);
    if (typeof offset !== "number") offset = 0;
    if (file.mtime === state.get(mtimeKey, 0) && offset >= state.get(stepsKey, 0)) continue;

    const trajectory = await getTrajectory(file.cascadeId, servers);
    if (!trajectory) continue;
    const steps = trajectory.result.trajectory.steps || [];
    if (offset > steps.length) offset = 0;
    const metadataResult = await getGeneratorMetadata(file.cascadeId, servers);
    const metadata = metadataResult ? metadataResult.result.generatorMetadata || [] : [];
    const models = modelMap(metadata);
    const extracted = extractMessages(steps, offset, maxChars, models);
    if (extracted.messages.length) {
      const sourceModel = `antigravity:${trajectory.server.appDataDir}`;
      const result = await client.write(
        space,
        extracted.messages,
        sourceModel,
        {
          source: "antigravity",
          cascade_id: file.cascadeId,
          workspace_id: trajectory.server.workspaceId || "",
          step_count: steps.length,
          captured_at: new Date().toISOString(),
        },
        language,
      );
      messages += extracted.messages.length;
      units += (result.written || []).length;
      conversations += 1;
      if (result.language_warning && log && !languageWarningLogged) {
        log(`Mnemo language warning: ${result.language_warning}`);
        languageWarningLogged = true;
      }
    }
    if (extracted.nextOffset !== offset) {
      await state.update(offsetKey, extracted.nextOffset);
    }
    await state.update(stepsKey, steps.length);
    await state.update(mtimeKey, file.mtime);

    if (metadata.length) {
      const rows = usageRows(file.cascadeId, metadata, trajectory.server.appDataDir);
      if (rows.length) {
        await client.reportUsage(space, rows);
        usage += rows.length;
      }
    }
  }

  return { messages, units, usage, conversations };
}

module.exports = { captureOnce, extractMessages, usageRows, stepText };
