from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

JsonObject = dict[str, Any]

_DOTENV_LOADED = False


@dataclass(frozen=True)
class SkillError(Exception):
    code: str
    message: str
    details: Optional[JsonObject] = None

    def to_json(self) -> JsonObject:
        payload: JsonObject = {"code": self.code, "message": self.message}
        if self.details is not None:
            payload["details"] = self.details
        return payload


def configure_stdout_utf8() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        return


def build_arg_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--input-json", type=str, help="Input payload JSON string")
    parser.add_argument("--input-file", type=str, help="Input payload JSON file path")
    return parser


def _read_all_stdin() -> str:
    try:
        data = sys.stdin.read()
    except Exception as exc:
        raise SkillError(code="stdin_read_failed", message="Failed to read stdin", details={"error": str(exc)})
    return data


def load_input_payload(args: argparse.Namespace) -> JsonObject:
    if args.input_json:
        return _parse_json(args.input_json)

    if args.input_file:
        path = Path(args.input_file)
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="utf-8-sig")
        except Exception as exc:
            raise SkillError(
                code="input_file_read_failed",
                message="Failed to read input file",
                details={"path": str(path), "error": str(exc)},
            )
        return _parse_json(content)

    stdin = _read_all_stdin().strip()
    if not stdin:
        raise SkillError(
            code="missing_input",
            message="Provide --input-json / --input-file or stdin JSON",
        )
    return _parse_json(stdin)


def _parse_json(text: str) -> JsonObject:
    text = text.lstrip("\ufeff")
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SkillError(code="invalid_json", message="Invalid JSON input", details={"error": str(exc)})
    if not isinstance(value, dict):
        raise SkillError(code="invalid_json", message="JSON input must be an object", details={"type": type(value).__name__})
    return value


def get_env_required(name: str) -> str:
    ensure_dotenv_loaded()
    value = os.environ.get(name)
    if value:
        return value
    raise SkillError(code="missing_env", message=f"Missing required env var: {name}")


def get_env_optional(name: str, default: str) -> str:
    ensure_dotenv_loaded()
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


def ensure_dotenv_loaded() -> None:
    global _DOTENV_LOADED
    if _DOTENV_LOADED:
        return
    _DOTENV_LOADED = True

    dotenv_path = Path(__file__).resolve().parent.parent / ".env"
    if not dotenv_path.exists() or not dotenv_path.is_file():
        return

    try:
        content = dotenv_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = dotenv_path.read_text(encoding="utf-8-sig")
    except Exception:
        return

    load_dotenv_text(content, override=False)


def load_dotenv_text(text: str, *, override: bool) -> None:
    """
    Minimal .env parser:
    - Supports KEY=VALUE (optionally with quotes)
    - Ignores blank lines and comments (#)
    - Supports leading 'export '
    - Convenience: if a line has no '=' and looks like an API key (starts with 'sk-'),
      it will be treated as TUZI_API_KEY when TUZI_API_KEY is not set yet.
    """

    assignments: dict[str, str] = {}
    bare_tokens: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.lower().startswith("export "):
            line = line[7:].strip()
            if not line:
                continue

        if "=" not in line:
            bare_tokens.append(line)
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue

        value = value.strip()
        if value.startswith(("'", '"')) and value.endswith(("'", '"')) and len(value) >= 2:
            value = value[1:-1]

        assignments[key] = value

    if not assignments and bare_tokens:
        candidate = bare_tokens[0].strip()
        if candidate.startswith("sk-") and not os.environ.get("TUZI_API_KEY"):
            assignments["TUZI_API_KEY"] = candidate

    for key, value in assignments.items():
        if override:
            os.environ[key] = value
        else:
            os.environ.setdefault(key, value)


def print_ok(payload: JsonObject) -> None:
    configure_stdout_utf8()
    out: JsonObject = {"ok": True, **payload}
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    sys.stdout.write("\n")


def print_error(err: SkillError) -> None:
    configure_stdout_utf8()
    out: JsonObject = {"ok": False, "error": err.to_json()}
    sys.stdout.write(json.dumps(out, ensure_ascii=False))
    sys.stdout.write("\n")
