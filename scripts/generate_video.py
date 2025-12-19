from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path
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

        # 记录开始时间
        start_time = time.time()
        task_create_time = None
        poll_start_time = None
        poll_end_time = None

        with TuziApiClient(TuziConfig.from_env()) as client:
            task = client.create_video_task(payload)
            task_create_time = time.time()

            task_id = _pick(task, "id", "task_id", "video_id") or payload.get("task_id")
            if not isinstance(task_id, str) or not task_id:
                raise SkillError(
                    code="missing_task_id",
                    message="Upstream response missing task id",
                    details={"upstream": task},
                )

            # 保存输入配置到temp目录
            _save_input_config(payload, task_id)

            if wait_for_completion:
                poll_start_time = time.time()
                task = client.poll_until_terminal(task_id=task_id)
                poll_end_time = time.time()

        end_time = time.time()

        # 计算各个阶段的耗时
        total_time = end_time - start_time
        create_time = task_create_time - start_time if task_create_time else None
        polling_time = (poll_end_time - poll_start_time) if (poll_start_time and poll_end_time) else None

        result = {
            "task_id": task_id,
            "status": _pick(task, "status"),
            "progress": _pick(task, "progress"),
            "video_url": _pick(task, "video_url"),
            "upstream": task,
        }

        # 添加时间统计信息
        if wait_for_completion:
            result["timing"] = {
                "total_seconds": round(total_time, 2),
                "create_seconds": round(create_time, 2) if create_time else None,
                "polling_seconds": round(polling_time, 2) if polling_time else None,
                "human_readable": _format_duration(total_time),
            }

        print_ok(result)
        return 0
    except SkillError as err:
        print_error(err)
        return 2
    except Exception as exc:
        print_error(SkillError(code="unexpected_error", message="Unexpected error", details={"error": str(exc)}))
        return 3


def _save_input_config(payload: dict[str, Any], task_id: str) -> None:
    """将输入配置保存到temp目录,文件名包含时间戳"""
    try:
        # 获取脚本所在目录的父目录（项目根目录）
        script_dir = Path(__file__).parent
        project_root = script_dir.parent
        temp_dir = project_root / "temp"

        # 确保temp目录存在
        temp_dir.mkdir(exist_ok=True)

        # 生成文件名：input_YYYYMMDD_HHMMSS.json
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"input_{timestamp}.json"
        filepath = temp_dir / filename

        # 保存配置（包含task_id信息）
        config_to_save = {
            "task_id": task_id,
            "created_at": datetime.now().isoformat(),
            "input": payload
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(config_to_save, f, ensure_ascii=False, indent=2)
    except Exception:
        # 保存失败不影响主流程，静默忽略
        pass


def _format_duration(seconds: float) -> str:
    """将秒数格式化为人类可读的时长字符串"""
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)

    if hours > 0:
        return f"{hours}小时{minutes}分{secs}秒"
    elif minutes > 0:
        return f"{minutes}分{secs}秒"
    else:
        return f"{secs}秒"


if __name__ == "__main__":
    sys.exit(main())

