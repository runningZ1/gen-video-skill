# gen-video-skill（Tuzi / Sora-2 视频生成）

本 Skill 采用“Python 脚本 + references 文档”的官方推荐结构：`SKILL.md` 负责定义能力与调用入口，`scripts/` 提供可执行工具脚本，`references/` 收录 API/参数/合规等参考资料。

---

## 目录结构

```text
gen-video-skill/
├── SKILL.md                    # 核心入口：能力说明 + 工具定义 + 使用示例
├── scripts/                    # 执行层：Python 脚本（stdout 输出 JSON）
│   ├── _shared.py              # 通用：输入/输出/错误封装
│   ├── tuzi_api.py             # Tuzi API Client + 参数校验
│   ├── generate_video.py       # 文生/图生/故事板/（可选）等待完成
│   ├── get_video_status.py     # 查询任务状态与进度
│   ├── remix_video.py          # Remix 编辑
│   ├── create_character.py     # 从任务提取角色（角色一致性）
│   └── download_video.py       # 下载视频（url/bytes/file）
├── references/                 # 知识层：API/策略/完整方案
└── assets/                     # 资产层：模板、图片等（可选）
```

---

## 前置配置（必读）

### 推荐配置文件：`.env`（默认读取）

在 Skill 根目录（与 `SKILL.md` 同级）创建 `.env` 文件，脚本会自动加载：

```env
TUZI_API_KEY=你的_API_KEY
TUZI_BASE_URL=https://api.tu-zi.com
TUZI_HTTP_TIMEOUT_SECONDS=60
```

也支持“仅一行 API Key”的简写形式（不推荐，但兼容）：

```text
sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

> 环境变量仍然优先：若你已经在系统里设置了 `TUZI_API_KEY`，将覆盖 `.env` 中的值。

### 必需字段

- `TUZI_API_KEY`：Tuzi API Key（Bearer Token）

### 可选字段

- `TUZI_BASE_URL`：默认 `https://api.tu-zi.com`
- `TUZI_HTTP_TIMEOUT_SECONDS`：默认 `60`

---

## 工具调用约定（非常重要）

1. **所有脚本输入/输出均为 JSON**  
   - 输入：`--input-json` / `--input-file` / STDIN（三选一）
   - 输出：stdout 为单个 JSON 对象（`ensure_ascii=false`）
2. **错误输出格式统一**：stdout 返回 `{ "ok": false, "error": { ... } }`，并以非 0 退出码退出。
3. **默认策略（与 docs 方案一致）**  
   - 默认 `model=sora-2`、`seconds=15`、`size=1280x720`  
   - 轮询建议：3→8 秒递增，总超时 8 分钟（脚本内 `wait_for_completion=true` 时使用）
4. **合规提示**：禁止真人或像真人、暴力血腥、色情、侵权内容、在世名人等；不得提供绕过审查的建议。

---

## Tools（脚本型工具）

> 下方 “Command” 为可直接执行的命令行形式；实际在 Claude 中使用时，按工具含义填入 JSON 即可。
>
> Windows PowerShell 5.1 若遇到命令行转义/编码问题，建议优先用 `--input-file` 传入 JSON（脚本已兼容 BOM）。

### Tool: `generate_video`

用于创建视频生成任务（文生/图生/故事板），默认**不阻塞等待**，返回 `task_id` 后由 `get_video_status` 轮询。

**Command**

```bash
python scripts/generate_video.py --input-json "{\"prompt\":\"...\"}"
```

**Input JSON**

- `prompt` (string, required)：视频描述或故事板文本
- `model` (string, optional)：`sora-2` | `sora-2-pro`，默认 `sora-2`
- `seconds` (integer, optional)：10/15/25（25 仅 pro），默认 15
- `size` (string, optional)：`1280x720`/`720x1280`/`1792x1024`/`1024x1792`
- `quality` (string, optional)：`sd` | `hd` | `auto`（仅用于默认 size 选择），默认 `auto`
- `orientation` (string, optional)：`landscape` | `portrait`（仅用于默认 size 选择）
- `input_reference_url` (string, optional)：参考图 URL（推荐）
- `input_reference_path` (string, optional)：参考图本地路径（可选）
- `input_reference_base64` (string, optional)：参考图 Base64（可选）
- `watermark` (boolean, optional)：默认 `false`
- `private` (boolean, optional)：默认 `false`
- `character_url` (string, optional)：角色引用（客串一致性）
- `character_timestamps` (string, optional)：`"start,end"`，且 `end-start` ∈ [1,3]
- `metadata` (object, optional)：透传元数据（脚本会 JSON 序列化后提交）
- `wait_for_completion` (boolean, optional)：是否在脚本内轮询等待完成（默认 `false`）

**Output JSON（成功）**

```json
{
  "ok": true,
  "task_id": "sora-2:task_xxx",
  "status": "queued",
  "progress": 0
}
```

---

### Tool: `get_video_status`

查询任务状态与进度。

**Command**

```bash
python scripts/get_video_status.py --input-json "{\"task_id\":\"sora-2:task_xxx\"}"
```

**Input JSON**

- `task_id` (string, required)

**Output JSON（成功）**

```json
{
  "ok": true,
  "task_id": "sora-2:task_xxx",
  "status": "in_progress",
  "progress": 42,
  "video_url": null
}
```

---

### Tool: `remix_video`

对已生成视频进行 Remix 编辑，返回新的任务 ID。

**Command**

```bash
python scripts/remix_video.py --input-json "{\"task_id\":\"sora-2:task_xxx\",\"prompt\":\"...\"}"
```

**Input JSON**

- `task_id` (string, required)
- `prompt` (string, required)：新的提示词（编辑指令）

---

### Tool: `create_character`

从已完成任务中提取角色，用于后续一致性生成（客串）。

**Command**

```bash
python scripts/create_character.py --input-json "{\"source_task_id\":\"sora-2:task_xxx\",\"character_timestamps\":\"1,3\"}"
```

**Input JSON**

- `source_task_id` (string, required)：必须为 completed 的任务
- `character_timestamps` (string, required)：`"start,end"`，且 `end-start` ∈ [1,3]
- `model` (string, optional)：默认 `sora-2`

---

### Tool: `download_video`

下载视频（默认只返回 `video_url`；如需落盘再拉取 `/content`）。

**Command**

```bash
python scripts/download_video.py --input-json "{\"task_id\":\"sora-2:task_xxx\",\"mode\":\"url\"}"
```

**Input JSON**

- `task_id` (string, required)
- `mode` (string, optional)：`url` | `bytes` | `file`，默认 `url`
- `output_path` (string, optional)：`mode=file` 时写入路径。如不指定，默认保存到 `assets/` 目录，文件名根据 task_id 自动生成

---

## References

- `references/api_documentation.md`：上游 API 速览（脚本实现最小参考）
- `references/policy.md`：合规与安全提示（对用户展示口径）
- `references/tuzi-sora2-claude-skill-complete.md`：完整整合方案（大文档，含附录与源文档收录）
> 说明：本仓库默认忽略 `docs/`（本地草稿/敏感信息可放此处，但不会提交到 GitHub）。
