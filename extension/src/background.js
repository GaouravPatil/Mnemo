import { Mnemo } from "./mnemo.js";

async function getClient() {
  const { baseUrl, apiKey } = await chrome.storage.sync.get({
    baseUrl: "http://127.0.0.1:8000",
    apiKey: "",
  });
  return new Mnemo(baseUrl, apiKey);
}

async function handle(msg) {
  const client = await getClient();
  switch (msg.type) {
    case "health":
      return client.health();
    case "write":
      return client.write(msg.space, msg.content, msg.sourceModel, undefined, msg.language);
    case "read":
      return client.read(msg.space, {
        query: msg.query,
        maxTokens: msg.maxTokens,
        format: msg.format,
      });
    case "unit":
      return client.unit(msg.unitId);
    case "delete":
      return client.deleteUnit(msg.unitId);
    default:
      throw new Error(`unknown message type: ${msg.type}`);
  }
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  handle(msg).then(
    (data) => sendResponse({ ok: true, data }),
    (err) => sendResponse({ ok: false, error: String(err) }),
  );
  return true;
});
