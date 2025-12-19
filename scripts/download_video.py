from __future__ import annotations

import base64
import os
import re
import sys
from pathlib import Path
from typing import Any

from _shared import SkillError, build_arg_parser, load_input_payload, print_error, print_ok
from tuzi_api import TuziApiClient, TuziConfig

SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")


def _pick(d: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def _default_output_path(task_id: str) -> Path:
    safe = SAFE_NAME_RE.sub("_", task_id).strip("._-") or "video"
    # 默认输出到 assets 目录
    skill_root = Path(__file__).parent.parent
    return skill_root / "assets" / f"{safe}.mp4"


def main() -> int:
    parser = build_arg_parser("Download a Tuzi/Sora video content")
    args = parser.parse_args()

    try:
        payload = load_input_payload(args)
        task_id = payload.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            raise SkillError(code="invalid_task_id", message="task_id must be a non-empty string")

        mode = payload.get("mode", "url")
        if not isinstance(mode, str):
            raise SkillError(code="invalid_mode", message="mode must be a string")
        mode = mode.strip().lower()
        if mode not in {"url", "bytes", "file"}:
            raise SkillError(code="invalid_mode", message="mode must be one of: url, bytes, file")

        output_path = payload.get("output_path")
        if output_path is not None and not isinstance(output_path, str):
            raise SkillError(code="invalid_output_path", message="output_path must be a string")

        with TuziApiClient(TuziConfig.from_env()) as client:
            if mode == "url":
                task = client.get_video_task(task_id)
                video_url = _pick(task, "video_url")
                print_ok({"task_id": task_id, "video_url": video_url, "upstream": task})
                return 0

            content = client.download_video_content(task_id)

        if mode == "bytes":
            encoded = base64.b64encode(content).decode("ascii")
            print_ok({"task_id": task_id, "bytes_base64": encoded})
            return 0

        path = Path(output_path) if output_path else _default_output_path(task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            f.write(content)

        print_ok({"task_id": task_id, "file_path": str(path.resolve()), "size_bytes": os.path.getsize(path)})
        return 0

    except SkillError as err:
        print_error(err)
        return 2
    except Exception as exc:
        print_error(SkillError(code="unexpected_error", message="Unexpected error", details={"error": str(exc)}))
        return 3


if __name__ == "__main__":
    sys.exit(main())

