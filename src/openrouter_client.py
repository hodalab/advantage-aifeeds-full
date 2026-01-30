# openrouter_client.py
# Stdlib-only OpenRouter client (Lambda-friendly).
# The API key must be injected from the outside.

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Generator, List, Optional


Json = Dict[str, Any]


class OpenRouterError(RuntimeError):
    """
    usage:
        or_client = OpenRouterClient(
            api_key=api_key,
            x_title="advantage-bai-feed-summary",
        )
        response = or_client.chat_completions(
            model=llm,
            messages=[
                # One or more system prompts
                {"role": "system", "content": system_message},
                {"role": "user", "content": json.dumps(contents)},
            ],
        temperature=0.1,
        max_tokens=MAX_TOKENS,
        )
        content=response["choices"][0]["message"]["content"]
    """
    def __init__(self, message: str, *, status: Optional[int] = None, payload: Optional[Json] = None):
        super().__init__(message)
        self.status = status
        self.payload = payload or {}


class OpenRouterClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        http_referer: Optional[str] = None,
        x_title: Optional[str] = None,
        timeout_s: float = 30.0,
        max_retries: int = 2,
        backoff_base_s: float = 0.6,
        backoff_cap_s: float = 8.0,
    ):
        if not api_key:
            raise ValueError("api_key is required.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.http_referer = http_referer
        self.x_title = x_title
        self.timeout_s = float(timeout_s)
        self.max_retries = int(max_retries)
        self.backoff_base_s = float(backoff_base_s)
        self.backoff_cap_s = float(backoff_cap_s)

    def chat_completions(self, *, model: str, messages: List[Json], **params: Any) -> Json:
        body: Json = {"model": model, "messages": messages, **params, "stream": False}
        return self._post_json("/chat/completions", body)

    def chat_completions_stream(
        self, *, model: str, messages: List[Json], **params: Any
    ) -> Generator[Json, None, None]:
        body: Json = {"model": model, "messages": messages, **params, "stream": True}
        yield from self._post_sse("/chat/completions", body)

    # ------------------------- internal -------------------------

    def _headers(self) -> Dict[str, str]:
        h = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.http_referer:
            h["HTTP-Referer"] = self.http_referer
        if self.x_title:
            h["X-Title"] = self.x_title
        return h

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path if path.startswith('/') else '/' + path}"

    def _sleep_backoff(self, attempt: int) -> None:
        # English: exponential backoff with jitter
        expo = self.backoff_base_s * (2 ** max(0, attempt))
        delay = min(self.backoff_cap_s, expo) * (0.7 + 0.6 * random.random())
        time.sleep(delay)

    def _post_json(self, path: str, body: Json) -> Json:
        url = self._url(path)
        payload = json.dumps(body).encode("utf-8")

        last_err: Optional[OpenRouterError] = None
        for attempt in range(self.max_retries + 1):
            req = urllib.request.Request(url, data=payload, headers=self._headers(), method="POST")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    raw = resp.read()
                    data = json.loads(raw.decode("utf-8")) if raw else {}
                    if isinstance(data, dict) and data.get("error"):
                        raise OpenRouterError(
                            data["error"].get("message", "OpenRouter error"),
                            status=getattr(resp, "status", None),
                            payload=data,
                        )
                    return data
            except urllib.error.HTTPError as e:
                err_payload = self._try_read_json(e)
                status = e.code
                msg = self._error_message(err_payload, fallback=str(e))
                last_err = OpenRouterError(msg, status=status, payload=err_payload)
                if attempt < self.max_retries and status in (429, 500, 502, 503, 504):
                    self._sleep_backoff(attempt)
                    continue
                raise last_err
            except urllib.error.URLError as e:
                last_err = OpenRouterError(f"Network error: {e}")
                if attempt < self.max_retries:
                    self._sleep_backoff(attempt)
                    continue
                raise last_err

        raise last_err or OpenRouterError("Unknown error")

    def _post_sse(self, path: str, body: Json) -> Generator[Json, None, None]:
        url = self._url(path)
        payload = json.dumps(body).encode("utf-8")

        last_err: Optional[OpenRouterError] = None
        for attempt in range(self.max_retries + 1):
            headers = self._headers()
            headers["Accept"] = "text/event-stream"
            req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                    data_lines: List[str] = []
                    while True:
                        bline = resp.readline()
                        if not bline:
                            break
                        line = bline.decode("utf-8", errors="replace").rstrip("\n")
                        if not line:
                            if data_lines:
                                chunk = "\n".join(data_lines).strip()
                                data_lines = []
                                if chunk == "[DONE]":
                                    return
                                try:
                                    obj = json.loads(chunk)
                                except json.JSONDecodeError:
                                    continue
                                if isinstance(obj, dict) and obj.get("error"):
                                    raise OpenRouterError(
                                        obj["error"].get("message", "OpenRouter stream error"),
                                        status=getattr(resp, "status", None),
                                        payload=obj,
                                    )
                                yield obj
                            continue
                        if line.startswith("data:"):
                            data_lines.append(line[len("data:") :].strip())
                return
            except urllib.error.HTTPError as e:
                err_payload = self._try_read_json(e)
                status = e.code
                msg = self._error_message(err_payload, fallback=str(e))
                last_err = OpenRouterError(msg, status=status, payload=err_payload)
                if attempt < self.max_retries and status in (429, 500, 502, 503, 504):
                    self._sleep_backoff(attempt)
                    continue
                raise last_err
            except urllib.error.URLError as e:
                last_err = OpenRouterError(f"Network error: {e}")
                if attempt < self.max_retries:
                    self._sleep_backoff(attempt)
                    continue
                raise last_err

        raise last_err or OpenRouterError("Unknown error")

    @staticmethod
    def _try_read_json(e: urllib.error.HTTPError) -> Json:
        try:
            raw = e.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            return {}

    @staticmethod
    def _error_message(payload: Json, *, fallback: str) -> str:
        if isinstance(payload, dict):
            if isinstance(payload.get("error"), dict):
                return payload["error"].get("message") or fallback
            if payload.get("message"):
                return str(payload["message"])
        return fallback