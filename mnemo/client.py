import json
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_URL = "http://127.0.0.1:8000"
DEFAULT_KEY = "mnemo-dev-key"


class MnemoError(Exception):
    pass


class Mnemo:
    def __init__(self, base_url=DEFAULT_URL, api_key=DEFAULT_KEY, timeout=60):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _req(self, method, path, body=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers={"Content-Type": "application/json", "X-API-Key": self.api_key},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            raise MnemoError(f"{e.code}: {e.read().decode('utf-8', 'replace')}") from None
        return json.loads(raw) if raw else {}

    def write(
        self,
        space_id,
        content,
        source_model="client",
        meta=None,
        extract=None,
        language=None,
    ):
        body = {"space_id": space_id, "content": content, "source_model": source_model}
        if meta is not None:
            body["meta"] = meta
        if extract is not None:
            body["extract"] = extract
        if language is not None:
            body["language"] = language
        return self._req("POST", "/memory/write", body)

    def read(self, space_id, query=None, max_tokens=800, format="compact", **kwargs):
        body = {"space_id": space_id, "query": query, "max_tokens": max_tokens, "format": format}
        body.update(kwargs)
        return self._req("POST", "/memory/read", body)

    def context(self, space_id, **kwargs):
        return self.read(space_id, **kwargs)["context"]

    def summary(self, space_id, query=None, max_tokens=400, target_model=None):
        return self._req(
            "POST",
            "/memory/summary",
            {
                "space_id": space_id,
                "query": query,
                "max_tokens": max_tokens,
                "target_model": target_model,
            },
        )

    def report_usage(self, space_id, rows):
        return self._req("POST", "/usage/report", {"space_id": space_id, "rows": rows})

    def usage_summary(self, space_id, since=None, until=None):
        params = {"space_id": space_id}
        if since is not None:
            params["since"] = since
        if until is not None:
            params["until"] = until
        return self._req("GET", "/usage/summary?" + urllib.parse.urlencode(params))

    def unit(self, unit_id):
        return self._req("GET", f"/memory/unit/{unit_id}")

    def delete_unit(self, unit_id):
        return self._req("DELETE", f"/memory/unit/{unit_id}")
