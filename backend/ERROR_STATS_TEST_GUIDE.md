# 报错统计功能测试指南

本指南介绍如何在本地使用 Docker 部署 CatieCli 并测试报错统计功能。

## 一、快速启动

### 1. 使用 Docker Compose 启动

```bash
cd CatieCli
docker-compose up --build -d
```

### 2. 或者手动构建并运行

```bash
cd CatieCli/backend

# 构建镜像
docker build -t catiecli-backend .

# 运行容器
docker run -d \
  --name catiecli \
  -p 5001:5001 \
  -e ADMIN_USERNAME=admin \
  -e ADMIN_PASSWORD=admin123 \
  catiecli-backend
```

### 3. 访问服务

- 前端界面: http://localhost:5001
- API 文档: http://localhost:5001/docs

## 二、测试报错统计功能

### 1. 登录管理后台

1. 打开 http://localhost:5001
2. 使用管理员账号登录 (默认: admin / admin123)
3. 进入管理后台

### 2. 生成测试报错数据

#### 方法一：使用测试接口（推荐）

使用 curl 或 API 工具调用测试接口：

```bash
# 获取登录 Token
TOKEN=$(curl -s -X POST http://localhost:5001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' | jq -r '.access_token')

# 批量生成各种类型的测试报错日志
curl -X POST http://localhost:5001/api/test/simulate-errors \
  -H "Authorization: Bearer $TOKEN"
```

#### 方法二：生成单一类型的报错

```bash
# 可选类型: AUTH_ERROR, RATE_LIMIT, QUOTA_EXHAUSTED, INVALID_REQUEST, 
#          MODEL_ERROR, CONTENT_FILTER, NETWORK_ERROR, UPSTREAM_ERROR, 
#          TIMEOUT, TOKEN_ERROR, UNKNOWN

# 例如：生成认证错误
curl -X POST http://localhost:5001/api/test/simulate-error/AUTH_ERROR \
  -H "Authorization: Bearer $TOKEN"

# 生成速率限制错误
curl -X POST http://localhost:5001/api/test/simulate-error/RATE_LIMIT \
  -H "Authorization: Bearer $TOKEN"
```

### 3. 查看报错统计

#### 在管理后台查看
1. 进入管理后台 → 报错统计页面
2. 可以看到：
   - 今日报错统计
   - 最近报错详情列表
   - 点击"详情"可查看完整错误信息

#### 使用 API 查看

```bash
# 获取报错统计分析
curl -X GET "http://localhost:5001/api/admin/error-stats?days=7" \
  -H "Authorization: Bearer $TOKEN"

# 获取报错日志列表（筛选错误）
curl -X GET "http://localhost:5001/api/admin/logs?status=error&limit=20" \
  -H "Authorization: Bearer $TOKEN"

# 按错误类型筛选
curl -X GET "http://localhost:5001/api/admin/logs?error_type=AUTH_ERROR" \
  -H "Authorization: Bearer $TOKEN"

# 获取单条日志详情（假设日志ID为1）
curl -X GET "http://localhost:5001/api/admin/logs/1/detail" \
  -H "Authorization: Bearer $TOKEN"
```

### 4. 清理测试数据

```bash
# 清除所有测试生成的报错日志
curl -X DELETE http://localhost:5001/api/test/clear-test-logs \
  -H "Authorization: Bearer $TOKEN"
```

## 三、API 接口说明

### 新增/增强的接口

| 接口 | 方法 | 描述 |
|------|------|------|
| `/api/admin/error-stats` | GET | 报错统计分析（按类型、凭证、趋势） |
| `/api/admin/logs` | GET | 日志列表（新增 error_type 筛选） |
| `/api/admin/logs/{id}/detail` | GET | 日志详情（包含完整错误信息） |
| `/api/test/simulate-errors` | POST | 批量生成测试报错 |
| `/api/test/simulate-error/{type}` | POST | 生成指定类型报错 |
| `/api/test/error-types` | GET | 列出所有错误类型 |
| `/api/test/classify` | POST | 测试错误分类函数 |
| `/api/test/clear-test-logs` | DELETE | 清理测试数据 |

### 报错统计接口返回示例

```json
{
  "period_days": 7,
  "today_total": 100,
  "today_errors": 15,
  "today_error_rate": 15.0,
  "by_type": [
    {"type": "RATE_LIMIT", "type_name": "速率限制", "count": 5},
    {"type": "AUTH_ERROR", "type_name": "认证失败", "count": 3}
  ],
  "by_status_code": [
    {"code": 429, "count": 5},
    {"code": 403, "count": 3}
  ],
  "by_credential": [
    {
      "credential_id": 1,
      "email": "test@example.com",
      "errors": 5,
      "successes": 95,
      "error_rate": 5.0
    }
  ],
  "daily_trend": [
    {"date": "2026-01-01", "total": 100, "errors": 15, "error_rate": 15.0}
  ],
  "error_types": {
    "AUTH_ERROR": "认证失败",
    "RATE_LIMIT": "速率限制",
    "QUOTA_EXHAUSTED": "配额用尽"
  }
}
```

## 四、错误类型说明

| 类型 | 中文名称 | 描述 | 触发场景 |
|------|----------|------|----------|
| AUTH_ERROR | 认证失败 | Token 无效或权限不足 | 401/403 响应 |
| RATE_LIMIT | 速率限制 | 请求过于频繁 | 429 (RPM/TPM 限制) |
| QUOTA_EXHAUSTED | 配额用尽 | 日配额已用完 | 429 (daily quota) |
| INVALID_REQUEST | 请求无效 | 请求参数错误 | 400 (参数错误) |
| MODEL_ERROR | 模型错误 | 模型不存在 | 404 (model not found) |
| CONTENT_FILTER | 内容过滤 | 安全过滤器阻止 | 400 (safety blocked) |
| NETWORK_ERROR | 网络错误 | 连接中断 | ECONNRESET 等 |
| UPSTREAM_ERROR | 上游错误 | Google 服务异常 | 500/502/503 |
| TIMEOUT | 请求超时 | 响应超时 | 504 / timeout |
| TOKEN_ERROR | Token错误 | 刷新失败 | refresh_token 过期 |
| UNKNOWN | 未知错误 | 无法识别 | 其他错误 |

## 五、数据库变更

本次优化新增了以下字段：

```sql
-- usage_logs 表新增字段
ALTER TABLE usage_logs ADD COLUMN error_type VARCHAR(50);
ALTER TABLE usage_logs ADD COLUMN error_code VARCHAR(100);
ALTER TABLE usage_logs ADD COLUMN credential_email VARCHAR(100);

-- 新增索引
CREATE INDEX idx_usage_logs_error_type ON usage_logs(error_type);
CREATE INDEX idx_usage_logs_date_error ON usage_logs(created_at, error_type);
```

系统会在启动时自动执行迁移。

## 六、常见问题

### Q: 测试接口报 401 错误？
A: 需要使用管理员账号登录获取 Token，测试接口仅限管理员访问。

### Q: 前端报错统计页面为空？
A: 需要先调用测试接口生成测试数据，或者等待实际请求产生报错。

### Q: 如何验证错误分类是否正确？
A: 使用 `/api/test/classify` 接口测试：
```bash
curl -X POST "http://localhost:5001/api/test/classify?status_code=429&error_message=daily%20quota%20exceeded"
```

## 七、文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `app/services/error_classifier.py` | 新增 | 错误分类服务 |
| `app/models/user.py` | 修改 | UsageLog 新增字段 |
| `app/database.py` | 修改 | 数据库迁移逻辑 |
| `app/routers/proxy.py` | 修改 | 集成错误分类 |
| `app/routers/admin.py` | 修改 | 新增统计接口 |
| `app/routers/test.py` | 新增 | 测试接口 |
| `app/main.py` | 修改 | 注册测试路由 |