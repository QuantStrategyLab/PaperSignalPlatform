"""Generic helpers for brokerless signal notifier jobs."""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

from google.cloud import storage


DEFAULT_HTTP_TIMEOUT = 30
DEFAULT_HTTP_RETRIES = 3
DEFAULT_HTTP_BACKOFF_SECONDS = 1.0


def parse_gcs_uri(uri: str) -> tuple[str, str]:
    parsed = urllib.parse.urlparse(uri)
    if parsed.scheme != "gs" or not parsed.netloc or not parsed.path.lstrip("/"):
        raise ValueError(f"Invalid GCS URI: {uri}")
    return parsed.netloc, parsed.path.lstrip("/")


def read_text_from_uri(path_or_uri: str | Path) -> str:
    raw = str(path_or_uri)
    if raw.startswith("gs://"):
        bucket_name, blob_name = parse_gcs_uri(raw)
        client = storage.Client()
        return client.bucket(bucket_name).blob(blob_name).download_as_text(encoding="utf-8")
    path = Path(path_or_uri).expanduser().resolve()
    return path.read_text(encoding="utf-8")


def write_text_to_uri(text: str, path_or_uri: str | Path, *, content_type: str) -> str:
    raw = str(path_or_uri)
    if raw.startswith("gs://"):
        bucket_name, blob_name = parse_gcs_uri(raw)
        client = storage.Client()
        client.bucket(bucket_name).blob(blob_name).upload_from_string(text, content_type=content_type)
        return raw
    path = Path(path_or_uri).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return str(path)


def fetch_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = DEFAULT_HTTP_TIMEOUT,
    retries: int = DEFAULT_HTTP_RETRIES,
    backoff_seconds: float = DEFAULT_HTTP_BACKOFF_SECONDS,
    data: bytes | None = None,
) -> Any:
    last_error: Exception | None = None
    for attempt in range(1, max(1, retries) + 1):
        request = urllib.request.Request(url, headers=headers or {}, data=data)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode())
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt >= retries:
                break
            time.sleep(backoff_seconds * attempt)
    raise RuntimeError(f"Request failed after {retries} attempts: {url}") from last_error


def read_json_snapshot(snapshot_path: str | Path) -> dict[str, Any] | None:
    raw = str(snapshot_path)
    if raw.startswith("gs://"):
        try:
            return json.loads(read_text_from_uri(raw))
        except Exception:
            return None
    path = Path(snapshot_path).expanduser().resolve()
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json_snapshot(snapshot: dict[str, Any], output_path: str | Path) -> str:
    rendered = json.dumps(snapshot, ensure_ascii=False, indent=2)
    return write_text_to_uri(
        rendered,
        output_path,
        content_type="application/json; charset=utf-8",
    )


def build_notification_identity(
    snapshot: dict[str, Any],
    *,
    extra_keys: dict[str, Any] | None = None,
) -> dict[str, Any]:
    identity = {
        "as_of": snapshot.get("as_of"),
        "ready": bool(snapshot.get("ready")),
        "side": snapshot.get("side"),
        "target_symbol": snapshot.get("target_symbol"),
        "gross_exposure": round(float(snapshot.get("gross_exposure") or 0.0), 6),
    }
    if extra_keys:
        identity.update(extra_keys)
    return identity


def should_send_notification(
    snapshot: dict[str, Any],
    previous_snapshot: dict[str, Any] | None,
    *,
    extra_keys: dict[str, Any] | None = None,
) -> bool:
    if previous_snapshot is None:
        return True
    return build_notification_identity(snapshot, extra_keys=extra_keys) != build_notification_identity(
        previous_snapshot,
        extra_keys=extra_keys,
    )


def send_telegram_message(
    message: str,
    *,
    token: str,
    chat_id: str,
    timeout: int = DEFAULT_HTTP_TIMEOUT,
) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": message,
            "disable_web_page_preview": "true",
        }
    ).encode()
    response = fetch_json(
        url,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=timeout,
        retries=DEFAULT_HTTP_RETRIES,
        backoff_seconds=DEFAULT_HTTP_BACKOFF_SECONDS,
        data=payload,
    )
    if not isinstance(response, dict) or not response.get("ok"):
        raise RuntimeError(f"Telegram send failed: {response}")
