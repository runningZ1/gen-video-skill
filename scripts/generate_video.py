from __future__ import annotations

import sys
from typing import Any

from _shared import SkillError, build_arg_parser, load_input_payload, print_error, print_ok
from tuzi_api import TuziApiClient, TuziConfig


def _pick(d: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def main() -> int:
    parser = build_arg_parser("Create a Tuzi/Sora video generation task")
    args = parser.parse_args()

    try:
        payload = load_input_payload(args)
        wait_for_completion = bool(payload.get("wait_for_completion", False))

        with TuziApiClient(TuziConfig.from_env()) as client:
            task = client.create_video_task(payload)
            task_id = _pick(task, "id", "task_id", "video_id") or payload.get("task_id")
            if not isinstance(task_id, str) or not task_id:
                raise SkillError(
                    code="missing_task_id",
                    message="Upstream response missing task id",
                    details={"upstream": task},
                )

            if wait_for_completion:
                task = client.poll_until_terminal(task_id=task_id)

        print_ok(
            {
                "task_id": task_id,
                "status": _pick(task, "status"),
                "progress": _pick(task, "progress"),
                "video_url": _pick(task, "video_url"),
                "upstream": task,
            }
        )
        return 0
    except SkillError as err:
        print_error(err)
        return 2
    except Exception as exc:
        print_error(SkillError(code="unexpected_error", message="Unexpected error", details={"error": str(exc)}))
        return 3


if __name__ == "__main__":
    sys.exit(main())

