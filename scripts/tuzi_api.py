from __future__ import annotations

import base64
import json
import mimetypes
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Tuple

import httpx

from _shared import JsonObject, SkillError, get_env_optional, get_env_required

MODEL_SORA_2 = "sora-2"
MODEL_SORA_2_PRO = "sora-2-pro"

ALLOWED_MODELS = {MODEL_SORA_2, MODEL_SORA_2_PRO}
ALLOWED_SECONDS = {10, 15, 25}

SIZE_SD_LANDSCAPE = "1280x720"
SIZE_SD_PORTRAIT = "720x1280"
SIZE_HD_LANDSCAPE = "1792x1024"
SIZE_HD_PORTRAIT = "1024x1792"

PRO_SIZES = {SIZE_SD_LANDSCAPE, SIZE_SD_PORTRAIT, SIZE_HD_LANDSCAPE, SIZE_HD_PORTRAIT}
STD_SIZES = {SIZE_SD_LANDSCAPE, SIZE_SD_PORTRAIT}

TIMESTAMP_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*$")


@dataclass(frozen=True)
class TuziConfig:
    api_key: str
    base_url: str
    timeout_seconds: float

    @staticmethod
    def from_env() -> "TuziConfig":
        api_key = get_env_required("TUZI_API_KEY")
        base_url = get_env_optional("TUZI_BASE_URL", "https://api.tu-zi.com").rstrip("/")
        timeout_seconds = float(get_env_optional("TUZI_HTTP_TIMEOUT_SECONDS", "60"))
        return TuziConfig(api_key=api_key, base_url=base_url, timeout_seconds=timeout_seconds)


class TuziApiClient:
    def __init__(self, config: TuziConfig) -> None:
        self._config = config
        self._client = httpx.Client(
            base_url=self._config.base_url,
            headers={"Authorization": f"Bearer {self._config.api_key}"},
            timeout=httpx.Timeout(self._config.timeout_seconds),
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "TuziApiClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def create_video_task(self, payload: JsonObject) -> JsonObject:
        normalized = normalize_generate_payload(payload)
        files: Optional[dict[str, Tuple[str, Any, str]]] = None

        input_reference_path = normalized.pop("_input_reference_path", None)
        if input_reference_path:
            path = Path(str(input_reference_path))
            if not path.exists() or not path.is_file():
                raise SkillError(
                    code="invalid_input_reference_path",
                    message="input_reference_path does not exist or is not a file",
                    details={"path": str(path)},
                )
            mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
            with path.open("rb") as f:
                files = {"input_reference": (path.name, f, mime)}
                return self._post_multipart("/v1/videos", data=normalized, files=files)

        return self._post_multipart("/v1/videos", data=normalized, files=files)

    def create_character_from_task(self, source_task_id: str, character_timestamps: str, model: str) -> JsonObject:
        validate_model(model)
        validate_character_timestamps(character_timestamps)
        data = {
            "model": model,
            "character_from_task": source_task_id,
            "character_timestamps": character_timestamps,
        }
        return self._post_multipart("/v1/videos", data=data, files=None)

    def get_video_task(self, task_id: str) -> JsonObject:
        return self._get_json(f"/v1/videos/{task_id}")

    def remix_video(self, task_id: str, prompt: str) -> JsonObject:
        if not isinstance(prompt, str) or not prompt.strip():
            raise SkillError(code="invalid_prompt", message="prompt must be a non-empty string")
        return self._post_json(f"/v1/videos/{task_id}/remix", json_body={"prompt": prompt})

    def download_video_content(self, task_id: str) -> bytes:
        try:
            resp = self._client.get(f"/v1/videos/{task_id}/content")
        except httpx.RequestError as exc:
            raise SkillError(code="network_error", message="Network error", details={"error": str(exc)})
        if resp.status_code >= 400:
            raise SkillError(
                code="upstream_error",
                message="Upstream error",
                details={"status_code": resp.status_code, "body": safe_text(resp)},
            )
        return resp.content

    def poll_until_terminal(
        self,
        task_id: str,
        timeout_seconds: int = 480,
        schedule_seconds: Optional[list[int]] = None,
        max_interval_seconds: int = 8,
    ) -> JsonObject:
        schedule = schedule_seconds or [3, 4, 5, 6, 7]
        elapsed = 0
        attempt = 0

        while elapsed < timeout_seconds:
            task = self.get_video_task(task_id)
            status = str(task.get("status", "")).lower()
            if status in {"completed", "failed"}:
                return task

            interval = schedule[attempt] if attempt < len(schedule) else max_interval_seconds
            time.sleep(interval)
            elapsed += interval
            attempt += 1

        raise SkillError(
            code="polling_timeout",
            message="Polling timed out",
            details={"task_id": task_id, "timeout_seconds": timeout_seconds},
        )

    def _get_json(self, path: str) -> JsonObject:
        try:
            resp = self._client.get(path)
        except httpx.RequestError as exc:
            raise SkillError(code="network_error", message="Network error", details={"error": str(exc)})

        if resp.status_code >= 400:
            raise SkillError(
                code="upstream_error",
                message="Upstream error",
                details={"status_code": resp.status_code, "body": safe_text(resp)},
            )
        return parse_json_response(resp)

    def _post_json(self, path: str, json_body: JsonObject) -> JsonObject:
        try:
            resp = self._client.post(path, json=json_body)
        except httpx.RequestError as exc:
            raise SkillError(code="network_error", message="Network error", details={"error": str(exc)})
        if resp.status_code >= 400:
            raise SkillError(
                code="upstream_error",
                message="Upstream error",
                details={"status_code": resp.status_code, "body": safe_text(resp)},
            )
        return parse_json_response(resp)

    def _post_multipart(
        self,
        path: str,
        data: JsonObject,
        files: Optional[dict[str, Tuple[str, Any, str]]],
    ) -> JsonObject:
        form = {k: stringify_form_value(v) for k, v in data.items() if v is not None}
        # Tuzi / Sora-2 upstream expects multipart/form-data for /v1/videos even
        # when there are no file parts. In httpx, passing `data=` produces
        # application/x-www-form-urlencoded, so we force multipart by sending
        # *all* fields via `files={field: (None, value)}` and then merging
        # actual file parts when present.
        multipart: dict[str, Any] = {k: (None, v) for k, v in form.items()}
        if files:
            for field_name, (filename, file_obj, content_type) in files.items():
                multipart[field_name] = (filename, file_obj, content_type)
        try:
            resp = self._client.post(path, files=multipart)
        except httpx.RequestError as exc:
            raise SkillError(code="network_error", message="Network error", details={"error": str(exc)})
        if resp.status_code >= 400:
            raise SkillError(
                code="upstream_error",
                message="Upstream error",
                details={"status_code": resp.status_code, "body": safe_text(resp)},
            )
        return parse_json_response(resp)


def normalize_generate_payload(payload: JsonObject) -> JsonObject:
    prompt = payload.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise SkillError(code="invalid_prompt", message="prompt must be a non-empty string")

    model = payload.get("model", MODEL_SORA_2)
    validate_model(model)

    seconds = payload.get("seconds", 15)
    seconds = coerce_int(seconds, "seconds")
    validate_seconds(model, seconds)

    size = payload.get("size")
    quality = payload.get("quality", "auto")
    orientation = payload.get("orientation")

    normalized_size = choose_size(model=model, size=size, quality=quality, orientation=orientation)

    watermark = coerce_bool(payload.get("watermark", False), "watermark")
    private = coerce_bool(payload.get("private", False), "private")

    character_url = payload.get("character_url")
    character_timestamps = payload.get("character_timestamps")
    if character_timestamps is not None:
        if not isinstance(character_timestamps, str):
            raise SkillError(code="invalid_character_timestamps", message="character_timestamps must be a string")
        validate_character_timestamps(character_timestamps)

    metadata = payload.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        raise SkillError(code="invalid_metadata", message="metadata must be an object")

    input_reference_url = payload.get("input_reference_url")
    input_reference_path = payload.get("input_reference_path")
    input_reference_base64 = payload.get("input_reference_base64")
    input_ref_count = sum(1 for v in [input_reference_url, input_reference_path, input_reference_base64] if v)
    if input_ref_count > 1:
        raise SkillError(
            code="invalid_input_reference",
            message="Provide at most one of input_reference_url/input_reference_path/input_reference_base64",
        )

    out: JsonObject = {
        "model": model,
        "prompt": prompt,
        "seconds": seconds,
        "size": normalized_size,
        "watermark": watermark,
        "private": private,
    }

    if character_url is not None:
        if not isinstance(character_url, str):
            raise SkillError(code="invalid_character_url", message="character_url must be a string")
        out["character_url"] = character_url
    if character_timestamps is not None:
        out["character_timestamps"] = character_timestamps

    if input_reference_url is not None:
        if not isinstance(input_reference_url, str):
            raise SkillError(code="invalid_input_reference_url", message="input_reference_url must be a string")
        out["input_reference"] = input_reference_url
    elif input_reference_base64 is not None:
        if not isinstance(input_reference_base64, str):
            raise SkillError(code="invalid_input_reference_base64", message="input_reference_base64 must be a string")
        validate_base64(input_reference_base64)
        out["input_reference"] = input_reference_base64
    elif input_reference_path is not None:
        if not isinstance(input_reference_path, str):
            raise SkillError(code="invalid_input_reference_path", message="input_reference_path must be a string")
        out["_input_reference_path"] = input_reference_path

    if metadata is not None:
        out["metadata"] = json.dumps(metadata, ensure_ascii=False)

    character_create = payload.get("character_create")
    if character_create is not None:
        out["character_create"] = coerce_bool(character_create, "character_create")

    character_from_task = payload.get("character_from_task")
    if character_from_task is not None:
        if not isinstance(character_from_task, str):
            raise SkillError(code="invalid_character_from_task", message="character_from_task must be a string")
        out["character_from_task"] = character_from_task

    return out


def choose_size(model: str, size: Any, quality: Any, orientation: Any) -> str:
    is_pro = model == MODEL_SORA_2_PRO
    allowed_sizes = PRO_SIZES if is_pro else STD_SIZES

    if size is not None:
        if not isinstance(size, str):
            raise SkillError(code="invalid_size", message="size must be a string")
        if size not in allowed_sizes:
            raise SkillError(
                code="invalid_size",
                message="size is not supported by the selected model",
                details={"model": model, "size": size, "allowed_sizes": sorted(allowed_sizes)},
            )
        return size

    orient = normalize_orientation(orientation)
    q = normalize_quality(quality)

    if q == "hd" and is_pro:
        return SIZE_HD_PORTRAIT if orient == "portrait" else SIZE_HD_LANDSCAPE

    return SIZE_SD_PORTRAIT if orient == "portrait" else SIZE_SD_LANDSCAPE


def normalize_orientation(value: Any) -> str:
    if value is None:
        return "landscape"
    if not isinstance(value, str):
        raise SkillError(code="invalid_orientation", message="orientation must be a string")
    v = value.strip().lower()
    if v in {"portrait", "vertical", "9:16"}:
        return "portrait"
    if v in {"landscape", "horizontal", "16:9"}:
        return "landscape"
    raise SkillError(code="invalid_orientation", message="Invalid orientation", details={"value": value})


def normalize_quality(value: Any) -> str:
    if value is None:
        return "auto"
    if not isinstance(value, str):
        raise SkillError(code="invalid_quality", message="quality must be a string")
    v = value.strip().lower()
    if v in {"auto", "sd", "hd"}:
        return v
    raise SkillError(code="invalid_quality", message="Invalid quality", details={"value": value})


def validate_model(model: Any) -> None:
    if not isinstance(model, str) or model not in ALLOWED_MODELS:
        raise SkillError(code="invalid_model", message="model must be 'sora-2' or 'sora-2-pro'")


def validate_seconds(model: str, seconds: int) -> None:
    if seconds not in ALLOWED_SECONDS:
        raise SkillError(code="invalid_seconds", message="seconds must be 10, 15, or 25")
    if seconds == 25 and model != MODEL_SORA_2_PRO:
        raise SkillError(code="invalid_seconds", message="seconds=25 requires model 'sora-2-pro'")


def validate_character_timestamps(value: str) -> None:
    match = TIMESTAMP_RE.match(value)
    if not match:
        raise SkillError(code="invalid_character_timestamps", message="character_timestamps must be 'start,end'")
    start = float(match.group(1))
    end = float(match.group(2))
    if end <= start:
        raise SkillError(code="invalid_character_timestamps", message="end must be greater than start")
    duration = end - start
    if duration < 1 or duration > 3:
        raise SkillError(
            code="invalid_character_timestamps",
            message="character clip duration must be within [1,3] seconds",
            details={"start": start, "end": end, "duration": duration},
        )


def validate_base64(value: str) -> None:
    try:
        base64.b64decode(value, validate=True)
    except Exception:
        raise SkillError(code="invalid_base64", message="input_reference_base64 is not valid base64")


def coerce_int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise SkillError(code=f"invalid_{name}", message=f"{name} must be an integer")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    raise SkillError(code=f"invalid_{name}", message=f"{name} must be an integer")


def coerce_bool(value: Any, name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in {"true", "1", "yes"}:
            return True
        if v in {"false", "0", "no"}:
            return False
    raise SkillError(code=f"invalid_{name}", message=f"{name} must be a boolean")


def stringify_form_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def parse_json_response(resp: httpx.Response) -> JsonObject:
    try:
        value = resp.json()
    except Exception:
        raise SkillError(
            code="invalid_upstream_json",
            message="Upstream returned non-JSON response",
            details={"status_code": resp.status_code, "body": safe_text(resp)},
        )
    if not isinstance(value, dict):
        raise SkillError(
            code="invalid_upstream_json",
            message="Upstream JSON is not an object",
            details={"status_code": resp.status_code, "type": type(value).__name__},
        )
    return value


def safe_text(resp: httpx.Response) -> str:
    try:
        return resp.text
    except Exception:
        return "<unreadable>"
