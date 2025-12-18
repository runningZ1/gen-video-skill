from __future__ import annotations

import sys
from typing import Any

from _shared import SkillError, build_arg_parser, load_input_payload, print_error, print_ok
from tuzi_api import MODEL_SORA_2, TuziApiClient, TuziConfig


def _pick(d: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def main() -> int:
    parser = build_arg_parser("Extract a character from a completed Tuzi/Sora task")
    args = parser.parse_args()

    try:
        payload = load_input_payload(args)
        source_task_id = payload.get("source_task_id")
        character_timestamps = payload.get("character_timestamps")
        model = payload.get("model", MODEL_SORA_2)

        if not isinstance(source_task_id, str) or not source_task_id:
            raise SkillError(code="invalid_source_task_id", message="source_task_id must be a non-empty string")
        if not isinstance(character_timestamps, str) or not character_timestamps:
            raise SkillError(code="invalid_character_timestamps", message="character_timestamps must be a non-empty string")
        if not isinstance(model, str) or not model:
            raise SkillError(code="invalid_model", message="model must be a non-empty string")

        with TuziApiClient(TuziConfig.from_env()) as client:
            result = client.create_character_from_task(
                source_task_id=source_task_id,
                character_timestamps=character_timestamps,
                model=model,
            )

        print_ok(
            {
                "source_task_id": source_task_id,
                "character_url": _pick(result, "character_url", "character", "url"),
                "character_id": _pick(result, "character_id", "id"),
                "upstream": result,
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
