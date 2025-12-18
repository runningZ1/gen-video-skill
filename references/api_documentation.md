# Tuzi / Sora-2 API 速览（供脚本实现参考）

> 上游 API 可能迭代；以平台最新文档为准。本文件提供脚本实现所需的最小速查表。

## 基本信息

- Base URL：`https://api.tu-zi.com`
- 鉴权：`Authorization: Bearer $TUZI_API_KEY`

## 核心端点

| 能力 | Method | Path | 说明 |
|---|---|---|---|
| 创建视频任务（文生/图生/故事板/角色相关） | POST | `/v1/videos` | 推荐 `multipart/form-data` |
| 查询任务状态 | GET | `/v1/videos/{id}` | 返回 `status/progress/video_url` 等 |
| 下载视频内容 | GET | `/v1/videos/{id}/content` | 返回二进制内容 |
| Remix 编辑 | POST | `/v1/videos/{id}/remix` | JSON：`{ "prompt": "..." }` |
| Chat（可选） | POST | `/v1/chat/completions` | JSON：`model/messages/stream` |

## `/v1/videos`（multipart）常用字段

- `model`：`sora-2` / `sora-2-pro`
- `prompt`：文本提示词（也可使用 Storyboard 模板）
- `seconds`：10/15/25（25 仅 pro）
- `size`：`1280x720` / `720x1280` / `1792x1024` / `1024x1792`（高清仅 pro）
- `input_reference`：参考图（URL / file / Base64）（官方限制通常为 1 张）
- `watermark`：`true/false`
- `private`：`true/false`（`private=false` 通常才能 remix）
- `character_url`：角色引用（客串一致性）
- `character_from_task`：从任务提取角色（与 `character_timestamps` 配合）
- `character_timestamps`：`start,end`（且 `end-start` ∈ [1,3] 秒）
- `character_create`：是否自动创建角色（如上游支持）
- `metadata`：建议传 JSON 字符串（便于追踪，注意去敏）

## 轮询与重试（建议默认口径）

- 轮询间隔：3→8 秒递增（3/4/5/6/7/8...）
- 轮询超时：8 分钟
- 重试：仅网络错误/5xx 自动重试 1 次（指数退避 2→4 秒）

