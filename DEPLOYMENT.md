# Deployment Information

## Public URL
https://day14-agent-w8dm.onrender.com

## Platform
Render (Blueprint `day14-agent`, commit `3dbdd8b`)

Web service Docker plan free, tên `day14-agent`. Redis là Key Value `day14-redis` cùng Blueprint. Instance free ngủ khi không có request, lần gọi đầu có thể chờ khoảng 50 giây.

## Test Commands

Đặt `BASE` và `AGENT_API_KEY` trong terminal. Không dán key vào file này.

```bash
BASE=https://day14-agent-w8dm.onrender.com
```

### Health Check

```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"
# 200  {"status":"ok"}
```

### Readiness

```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"
# 200  {"ready":true}
```

### API Test (missing key)

```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
  -H "Content-Type: application/json" \
  -d '{"question":"Hello"}'
# 401
```

### API Test (with authentication)

```bash
curl -sS -X POST "$BASE/ask" \
  -H "X-API-Key: $AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question":"Hello"}'
# 200
# {"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","cost_usd":7.95e-06}
```

Đã chạy ngày 2026-11-26: `/health` 200, `/ready` 200, `/ask` thiếu key 401, `/ask` đúng key 200.

## Environment Variables Set

- `AGENT_API_KEY` — Render `generateValue`, không commit
- `REDIS_URL` — connection string của Key Value `day14-redis`
- `RATE_LIMIT_PER_MINUTE` — `30`
- `DAILY_BUDGET_USD` — `1`
- `ENVIRONMENT` — `staging`
- `PORT` — Render cấp lúc chạy container

## Screenshots

- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
