# Tuzi / Sora-2 API 快速参考

> **用途**: 脚本实现时的速查表
> **注意**: 上游 API 可能迭代，以平台最新文档为准

---

## 1. 基本信息

- **Base URL**: `https://api.tu-zi.com`
- **鉴权方式**: `Authorization: Bearer $TUZI_API_KEY`
- **推荐格式**: multipart/form-data (生成接口)

---

## 2. 核心端点

| 能力 | Method | Path | Content-Type |
|------|--------|------|-------------|
| 创建视频任务 | POST | `/v1/videos` | multipart/form-data |
| 查询任务状态 | GET | `/v1/videos/{id}` | - |
| 下载视频内容 | GET | `/v1/videos/{id}/content` | - |
| Remix 编辑 | POST | `/v1/videos/{id}/remix` | application/json |
| Chat (可选) | POST | `/v1/chat/completions` | application/json |

---

## 3. 请求字段说明

### 3.1 POST /v1/videos (multipart)

#### 必填字段
| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| model | string | 模型选择 | `sora-2` / `sora-2-pro` |
| prompt | string | 文本提示词 | "15秒横屏:海边日落..." |

#### 可选字段
| 字段 | 类型 | 默认值 | 说明 | 约束 |
|------|------|--------|------|------|
| seconds | integer | 15 | 视频时长 | 10/15/25（25仅pro） |
| size | string | 1280x720 | 视频尺寸 | 见尺寸支持矩阵 |
| input_reference | string/file | - | 参考图(URL/Base64) | 限1张 |
| watermark | boolean | false | 是否添加水印 | - |
| private | boolean | false | 是否私有 | true时可能无法remix |
| character_url | string | - | 角色引用URL | 需配合timestamps |
| character_from_task | string | - | 从任务提取角色 | 任务须completed |
| character_timestamps | string | - | 角色片段时间 | 格式: "start,end"<br>差值∈[1,3]秒 |
| character_create | boolean | false | 自动创建角色 | - |
| metadata | string | - | 透传元数据(JSON) | 注意去敏 |

---

## 4. 响应格式

### 4.1 创建任务成功 (POST /v1/videos)

```json
{
  "id": "sora-2:task_abc123def456",
  "status": "queued",
  "progress": 0,
  "created_at": 1703001234567
}
```

### 4.2 查询状态 (GET /v1/videos/{id})

**排队中**:
```json
{
  "id": "sora-2:task_abc123def456",
  "status": "queued",
  "progress": 0,
  "created_at": 1703001234567
}
```

**生成中**:
```json
{
  "id": "sora-2:task_abc123def456",
  "status": "in_progress",
  "progress": 67,
  "created_at": 1703001234567
}
```

**已完成**:
```json
{
  "id": "sora-2:task_abc123def456",
  "status": "completed",
  "progress": 100,
  "video_url": "https://cdn.tu-zi.com/videos/xxxxx.mp4",
  "created_at": 1703001234567,
  "completed_at": 1703001456789
}
```

**失败**:
```json
{
  "id": "sora-2:task_abc123def456",
  "status": "failed",
  "progress": 0,
  "error": {
    "code": "content_policy_violation",
    "message": "内容审核未通过：检测到真人形象"
  },
  "created_at": 1703001234567,
  "failed_at": 1703001456789
}
```

### 4.3 Remix (POST /v1/videos/{id}/remix)

**请求**:
```json
{
  "prompt": "改成白天、色彩更明亮"
}
```

**响应**:
```json
{
  "id": "sora-2:task_new123def456",
  "status": "queued",
  "progress": 0,
  "parent_task_id": "sora-2:task_abc123def456"
}
```

---

## 5. 错误处理

### 5.1 HTTP 错误码

| 状态码 | 含义 | 常见原因 | 处理方式 |
|--------|------|---------|---------|
| 400 | Bad Request | 参数错误/格式不正确 | 检查参数，参考错误详情 |
| 401 | Unauthorized | API Key 无效或未提供 | 检查 TUZI_API_KEY |
| 403 | Forbidden | 无权限访问 | 联系服务方确认权限 |
| 404 | Not Found | 任务不存在或已过期 | 确认 task_id 正确 |
| 429 | Too Many Requests | 请求频率过高 | 延长轮询间隔 |
| 500 | Internal Server Error | 服务器内部错误 | 重试1次 (2秒后) |
| 503 | Service Unavailable | 服务暂时不可用 | 重试1次 (4秒后) |

### 5.2 错误响应格式

```json
{
  "error": {
    "code": "invalid_parameter",
    "message": "参数 'seconds' 无效：sora-2 不支持 25 秒",
    "field": "seconds",
    "valid_values": ["10", "15"]
  }
}
```

### 5.3 常见错误码

| 错误码 | 说明 | 解决方案 |
|--------|------|---------|
| `invalid_parameter` | 参数验证失败 | 参考 valid_values 修正 |
| `content_policy_violation` | 内容审查未通过 | 修改素材或提示词 |
| `insufficient_credits` | 余额不足 | 充值 |
| `rate_limit_exceeded` | 超过频率限制 | 降低请求频率 |
| `task_not_found` | 任务不存在 | 确认 task_id |
| `invalid_model_for_duration` | 模型不支持该时长 | sora-2 不支持 25 秒 |
| `invalid_model_for_size` | 模型不支持该尺寸 | 高清尺寸需 sora-2-pro |

---

## 6. 轮询与重试策略

### 6.1 推荐轮询策略

| 轮询次数 | 等待间隔 | 说明 |
|----------|---------|------|
| 1 | 3秒 | 任务创建后首次查询 |
| 2 | 3秒 | - |
| 3 | 4秒 | 开始递增 |
| 4 | 5秒 | - |
| 5 | 6秒 | - |
| 6 | 7秒 | - |
| 7+ | 8秒 | 固定最大间隔 |

**超时**: 8分钟无响应则停止轮询，返回 task_id 供用户稍后查询

### 6.2 重试策略

**可重试错误** (仅重试1次):
- 网络超时 (Timeout)
- 连接失败 (ConnectionError)
- 5xx 服务器错误

**退避策略**:
- 第1次重试: 2秒后
- 第2次重试: 4秒后 (指数退避)

**不可重试错误**:
- 4xx 客户端错误 (参数错误、认证失败等)
- 429 频率限制 (应延长轮询间隔而非重试)
- 审查失败 (content_policy_violation)

---

## 7. 参数约束速查

### 7.1 尺寸支持矩阵

| size | 方向 | sora-2 | sora-2-pro |
|------|------|--------|-----------|
| 1280x720 | 横屏标清 | ✅ | ✅ |
| 720x1280 | 竖屏标清 | ✅ | ✅ |
| 1792x1024 | 横屏高清 | ❌ | ✅ |
| 1024x1792 | 竖屏高清 | ❌ | ✅ |

### 7.2 时长支持矩阵

| seconds | sora-2 | sora-2-pro |
|---------|--------|-----------|
| 10 | ✅ 标清 | ✅ 高清 |
| 15 | ✅ 标清 | ✅ 高清 |
| 25 | ❌ | ✅ 标清 |

### 7.3 字段格式约束

| 字段 | 格式 | 示例 | 校验规则 |
|------|------|------|---------|
| character_timestamps | "start,end" | "1,3" | end-start ∈ [1,3] |
| input_reference | URL 或 Base64 | "https://..." | 仅支持1张 |
| metadata | JSON字符串 | '{"user_id":"123"}' | 注意转义 |
| prompt | 文本 | "15秒横屏..." | 避免过长 |

---

## 8. 调试建议

### 8.1 参数验证检查清单

- [ ] model 是否为 `sora-2` 或 `sora-2-pro`
- [ ] seconds=25 时 model 必须是 `sora-2-pro`
- [ ] 高清尺寸时 model 必须是 `sora-2-pro`
- [ ] character_timestamps 格式正确且时长在 1-3 秒
- [ ] character_url 和 character_timestamps 同时提供
- [ ] API Key 已正确设置在环境变量

### 8.2 日志记录建议

**应记录**:
- ✅ 请求 ID / task_id
- ✅ 请求时间戳
- ✅ 模型和主要参数 (model, seconds, size)
- ✅ 响应状态和进度
- ✅ 错误码和错误信息
- ✅ 轮询次数和总耗时

**不应记录**:
- ❌ 完整 API Key (仅记录前8位)
- ❌ 完整 prompt (可记录哈希或长度)
- ❌ Base64 图片数据
- ❌ video_url 中的签名参数

---

## 9. 快速示例

### 9.1 最简单的文生视频

```bash
curl -X POST "https://api.tu-zi.com/v1/videos" \
  -H "Authorization: Bearer $TUZI_API_KEY" \
  -F "model=sora-2-pro" \
  -F "prompt=15秒横屏:海边日落"
```

### 9.2 图生视频

```bash
curl -X POST "https://api.tu-zi.com/v1/videos" \
  -H "Authorization: Bearer $TUZI_API_KEY" \
  -F "model=sora-2-pro" \
  -F "prompt=让猫跑起来" \
  -F "input_reference=https://example.com/cat.png"
```

### 9.3 查询状态

```bash
curl -X GET "https://api.tu-zi.com/v1/videos/sora-2:task_xxxxx" \
  -H "Authorization: Bearer $TUZI_API_KEY"
```

### 9.4 Remix

```bash
curl -X POST "https://api.tu-zi.com/v1/videos/sora-2:task_xxxxx/remix" \
  -H "Authorization: Bearer $TUZI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "改成白天"}'
```

---

**文档结束** - 完整 API 文档: https://api.tu-zi.com/docs
