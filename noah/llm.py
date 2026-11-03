"""LLM layer: Gemini Flash-Lite is the main model, Qwen (llama-server) is the backup.

* generate()        -> Result(text, engine, model)            one-shot
* generate_stream() -> yields ("delta", text) ... ("done", {engine, model})   token streaming

Order of attempts: every Gemini model id in [GEMINI_MODEL, *GEMINI_MODEL_FALLBACKS] (the next id is
only tried when Google answers 404 for the previous one), then Qwen. A circuit breaker stops us from
paying a 25 s timeout on every message while Gemini is down.
"""

import json
import logging
import re
import threading
import time
from dataclasses import dataclass

import requests

from . import config

log = logging.getLogger("noah.llm")


class LLMError(Exception):
    """Raised when neither Gemini nor Qwen could answer."""


class _Transient(Exception):
    pass


class _ModelNotFound(Exception):
    pass


class _Rejected(Exception):
    """400/401/403: key or request is wrong. Retrying immediately will not help."""


@dataclass
class Result:
    text: str
    engine: str          # "gemini" | "qwen"
    model: str


# --------------------------------------------------------------------------------------
# Circuit breaker
# --------------------------------------------------------------------------------------
class _Breaker:
    def __init__(self):
        self._lock = threading.Lock()
        self.failures = 0
        self.open_until = 0.0
        self.last_error = ""

    def allow(self):
        with self._lock:
            return time.monotonic() >= self.open_until

    def success(self):
        with self._lock:
            self.failures = 0
            self.open_until = 0.0
            self.last_error = ""

    def failure(self, error, hard=False):
        with self._lock:
            self.failures += 1
            self.last_error = str(error)[:300]
            if hard:
                self.open_until = time.monotonic() + 300
            elif self.failures >= 3:
                self.open_until = time.monotonic() + 45

    def snapshot(self):
        with self._lock:
            remaining = max(0.0, self.open_until - time.monotonic())
            return {"failures": self.failures, "open_for_s": round(remaining), "last_error": self.last_error}


gemini_breaker = _Breaker()
qwen_breaker = _Breaker()
_http = requests.Session()
_model_index = 0   # which entry of the model chain last worked


def _model_chain():
    chain = [config.GEMINI_MODEL] + [m for m in config.GEMINI_MODEL_FALLBACKS if m != config.GEMINI_MODEL]
    return chain


# --------------------------------------------------------------------------------------
# Gemini (REST, no SDK so there is nothing extra to install)
# --------------------------------------------------------------------------------------
def gemini_configured():
    return bool(config.GEMINI_API_KEY)


def _sse_lines(resp):
    """Decoded lines of a streaming response.

    Never use iter_lines(decode_unicode=True) here: for `text/event-stream` with no charset (what Gemini and llama-server send)
    `requests` assumes ISO-8859-1, which turns every Hindi/Kannada/Tamil/Malayalam/Telugu letter and the rupee sign into
    garbage like 'à¤¨à¤®'. The wire format is always UTF-8, so we decode the bytes ourselves."""
    for raw in resp.iter_lines():
        yield raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw


def _to_gemini_contents(messages):
    contents = []
    for m in messages:
        role = "model" if m["role"] in ("assistant", "model") else "user"
        text = m["content"]
        if contents and contents[-1]["role"] == role:
            contents[-1]["parts"][0]["text"] += "\n" + text
        else:
            contents.append({"role": role, "parts": [{"text": text}]})
    while contents and contents[0]["role"] != "user":
        contents.pop(0)
    return contents


def _gemini_body(system, messages, max_tokens, json_mode, temperature):
    gen = {"maxOutputTokens": max_tokens or config.GEMINI_MAX_TOKENS, "temperature": temperature}
    if json_mode:
        gen["responseMimeType"] = "application/json"
    body = {"contents": _to_gemini_contents(messages), "generationConfig": gen}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    return body


def _gemini_url(model, stream):
    verb = "streamGenerateContent?alt=sse" if stream else "generateContent"
    return f"{config.GEMINI_API_BASE}/v1beta/models/{model}:{verb}"


def _gemini_headers():
    return {"x-goog-api-key": config.GEMINI_API_KEY, "Content-Type": "application/json"}


def _text_from_gemini(payload):
    """Visible text of a generateContent response (thought parts are skipped)."""
    out = []
    for cand in payload.get("candidates") or []:
        for part in (cand.get("content") or {}).get("parts") or []:
            if part.get("thought"):
                continue
            if isinstance(part.get("text"), str):
                out.append(part["text"])
        if out:
            break
    return "".join(out)


def _classify_status(resp, model):
    code = resp.status_code
    if code == 404:
        raise _ModelNotFound(f"{model}: 404")
    if code in (400, 401, 403):
        raise _Rejected(f"{model}: HTTP {code} {resp.text[:200]}")
    if code == 429 or code >= 500:
        raise _Transient(f"{model}: HTTP {code}")
    if code >= 400:
        raise _Transient(f"{model}: HTTP {code}")


def _gemini_once(model, body):
    try:
        resp = _http.post(_gemini_url(model, False), headers=_gemini_headers(), json=body,
                          timeout=(5, config.GEMINI_TIMEOUT))
    except requests.RequestException as exc:
        raise _Transient(f"{model}: {exc.__class__.__name__}") from exc
    _classify_status(resp, model)
    try:
        payload = resp.json()
    except ValueError as exc:
        raise _Transient(f"{model}: bad JSON") from exc
    text = _text_from_gemini(payload).strip()
    if not text:
        block = (payload.get("promptFeedback") or {}).get("blockReason")
        finish = ((payload.get("candidates") or [{}])[0]).get("finishReason")
        raise _Transient(f"{model}: empty reply (block={block}, finish={finish})")
    return text


def _gemini_generate(system, messages, max_tokens, json_mode, temperature):
    global _model_index
    body = _gemini_body(system, messages, max_tokens, json_mode, temperature)
    chain = _model_chain()
    last = None
    for idx in range(_model_index, len(chain)):
        model = chain[idx]
        try:
            text = _gemini_once(model, body)
            _model_index = idx
            gemini_breaker.success()
            return Result(text, "gemini", model)
        except _ModelNotFound as exc:
            log.warning("Gemini model not found: %s", exc)
            last = exc
            continue
        except _Rejected as exc:
            gemini_breaker.failure(exc, hard=True)
            raise
        except _Transient as exc:
            gemini_breaker.failure(exc)
            raise
    gemini_breaker.failure(last or "no usable model", hard=True)
    raise _Rejected(str(last or "no usable Gemini model"))


def _gemini_stream(system, messages, max_tokens, temperature):
    """Yield text deltas. Raises before the first yield if the request failed outright."""
    global _model_index
    body = _gemini_body(system, messages, max_tokens, False, temperature)
    chain = _model_chain()
    last = None
    for idx in range(_model_index, len(chain)):
        model = chain[idx]
        try:
            resp = _http.post(_gemini_url(model, True), headers=_gemini_headers(), json=body,
                              timeout=(5, config.GEMINI_TIMEOUT), stream=True)
        except requests.RequestException as exc:
            gemini_breaker.failure(exc)
            raise _Transient(f"{model}: {exc.__class__.__name__}") from exc
        try:
            _classify_status(resp, model)
        except _ModelNotFound as exc:
            resp.close()
            last = exc
            continue
        except _Rejected as exc:
            resp.close()
            gemini_breaker.failure(exc, hard=True)
            raise
        except _Transient as exc:
            resp.close()
            gemini_breaker.failure(exc)
            raise
        yielded = False
        try:
            for raw in _sse_lines(resp):
                if not raw or not raw.startswith("data:"):
                    continue
                chunk = raw[5:].strip()
                if not chunk or chunk == "[DONE]":
                    continue
                try:
                    payload = json.loads(chunk)
                except ValueError:
                    continue
                text = _text_from_gemini(payload)
                if text:
                    yielded = True
                    yield text
        except requests.RequestException as exc:
            gemini_breaker.failure(exc)
            if not yielded:
                raise _Transient(f"{model}: stream broke") from exc
            raise
        finally:
            resp.close()
        if not yielded:
            gemini_breaker.failure("empty stream")
            raise _Transient(f"{model}: empty stream")
        _model_index = idx
        gemini_breaker.success()
        return
    gemini_breaker.failure(last or "no usable model", hard=True)
    raise _Rejected(str(last or "no usable Gemini model"))


# --------------------------------------------------------------------------------------
# Qwen via llama-server's OpenAI-compatible endpoint
# --------------------------------------------------------------------------------------
def _qwen_payload(system, messages, max_tokens, json_mode, temperature, stream):
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    for m in messages:
        msgs.append({"role": "assistant" if m["role"] in ("assistant", "model") else "user", "content": m["content"]})
    payload = {
        "model": "local",
        "messages": msgs,
        "temperature": min(temperature, 0.4),
        "max_tokens": min(max_tokens or config.LLAMA_MAX_TOKENS, 900) if json_mode else config.LLAMA_MAX_TOKENS,
        "stream": stream,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    return payload


def qwen_available():
    return config.QWEN_ENABLED and qwen_breaker.allow()


def _qwen_generate(system, messages, max_tokens, json_mode, temperature):
    payload = _qwen_payload(system, messages, max_tokens, json_mode, temperature, False)
    try:
        resp = _http.post(config.LLAMA_URL, json=payload, timeout=(3, config.LLAMA_TIMEOUT))
        resp.raise_for_status()
        text = resp.json()["choices"][0]["message"]["content"].strip()
    except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
        qwen_breaker.failure(exc)
        raise LLMError(f"Qwen failed: {exc.__class__.__name__}") from exc
    if not text:
        qwen_breaker.failure("empty")
        raise LLMError("Qwen returned nothing")
    qwen_breaker.success()
    return Result(text, "qwen", "qwen2.5-1.5b-instruct")


def _qwen_stream(system, messages, max_tokens, temperature):
    payload = _qwen_payload(system, messages, max_tokens, False, temperature, True)
    try:
        resp = _http.post(config.LLAMA_URL, json=payload, timeout=(3, config.LLAMA_TIMEOUT), stream=True)
        resp.raise_for_status()
    except requests.RequestException as exc:
        qwen_breaker.failure(exc)
        raise LLMError(f"Qwen failed: {exc.__class__.__name__}") from exc
    yielded = False
    try:
        for raw in _sse_lines(resp):
            if not raw or not raw.startswith("data:"):
                continue
            chunk = raw[5:].strip()
            if chunk == "[DONE]":
                break
            try:
                delta = json.loads(chunk)["choices"][0].get("delta", {}).get("content")
            except (ValueError, KeyError, IndexError):
                continue
            if delta:
                yielded = True
                yield delta
    except requests.RequestException as exc:
        qwen_breaker.failure(exc)
        raise LLMError("Qwen stream broke") from exc
    finally:
        resp.close()
    if not yielded:
        qwen_breaker.failure("empty stream")
        raise LLMError("Qwen returned nothing")
    qwen_breaker.success()


# --------------------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------------------
def generate(system, messages, *, max_tokens=None, json_mode=False, temperature=0.3, allow_qwen=True):
    errors = []
    if gemini_configured() and gemini_breaker.allow():
        try:
            return _gemini_generate(system, messages, max_tokens, json_mode, temperature)
        except (_Transient, _Rejected) as exc:
            log.warning("Gemini failed (%s) - falling back to Qwen", exc)
            errors.append(str(exc))
    elif not gemini_configured():
        errors.append("GEMINI_API_KEY not set")
    else:
        errors.append("Gemini circuit open")
    if allow_qwen and qwen_available():
        return _qwen_generate(system, messages, max_tokens, json_mode, temperature)
    raise LLMError("; ".join(errors) or "no model available")


def generate_stream(system, messages, *, max_tokens=None, temperature=0.3, qwen_system=None, qwen_messages=None):
    """Yield ("delta", text) then ("done", {"engine":..., "model":...}); ("reset", None) tells the
    caller that text already sent must be discarded because we switched engine mid-answer.
    Qwen gets its own (much shorter) prompt via qwen_system / qwen_messages."""
    errors = []
    sent_any = False
    if gemini_configured() and gemini_breaker.allow():
        try:
            for piece in _gemini_stream(system, messages, max_tokens, temperature):
                sent_any = True
                yield "delta", piece
            yield "done", {"engine": "gemini", "model": _model_chain()[min(_model_index, len(_model_chain()) - 1)]}
            return
        except (_Transient, _Rejected, requests.RequestException) as exc:
            log.warning("Gemini stream failed (%s) - falling back to Qwen", exc)
            errors.append(str(exc))
            if sent_any:
                yield "reset", None
    elif not gemini_configured():
        errors.append("GEMINI_API_KEY not set")
    else:
        errors.append("Gemini circuit open")
    if qwen_available():
        for piece in _qwen_stream(qwen_system if qwen_system is not None else system,
                                  qwen_messages if qwen_messages is not None else messages, max_tokens, temperature):
            yield "delta", piece
        yield "done", {"engine": "qwen", "model": "qwen2.5-1.5b-instruct"}
        return
    raise LLMError("; ".join(errors) or "no model available")


_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I)


def parse_json(text):
    """Tolerant JSON parse for model output (code fences, stray prose around the object)."""
    cleaned = _JSON_FENCE.sub("", (text or "").strip())
    try:
        return json.loads(cleaned)
    except ValueError:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = cleaned.find(opener), cleaned.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except ValueError:
                continue
    raise ValueError("model did not return JSON")


_SERVICE_WORDS = re.compile(r"gemini[\w.\-]*|generativelanguage\.googleapis\.com|googleapis\.com", re.I)


def scrub(text):
    """Staff-facing text: the real service and model ids are replaced by the display name."""
    return _SERVICE_WORDS.sub("Rexy", str(text or ""))


def status():
    """Dashboard snapshot (never reveals the key, the service behind the main model, or its model ids)."""
    primary = gemini_breaker.snapshot()
    primary["last_error"] = scrub(primary.get("last_error"))
    return {
        "primary": {"name": config.MODEL_DISPLAY_NAME, "configured": gemini_configured(), "breaker": primary},
        "qwen": {"enabled": config.QWEN_ENABLED, "url": config.LLAMA_URL, "breaker": qwen_breaker.snapshot()},
    }


def reset_state():
    """Test helper."""
    global _model_index
    _model_index = 0
    gemini_breaker.success()
    qwen_breaker.success()
