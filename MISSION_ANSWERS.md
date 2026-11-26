# Day 14 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found

Đọc `01-localhost-vs-production/develop/app.py`. Bản develop chạy được trên laptop, nhưng chưa sẵn sàng cho production. Có ít nhất 8 vấn đề:

1. **Secret hardcode trong source.** `OPENAI_API_KEY` và mật khẩu database nằm thẳng trong file. Push repo public là lộ key ngay, kể cả sau khi xóa ở commit sau vì secret vẫn còn trong lịch sử git.

```python
# develop/app.py, dòng 17–18
OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"
DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"
```

2. **Không có config management.** `DEBUG` và `MAX_TOKENS` gán cứng. Đổi môi trường (dev / staging / production) thì phải sửa code rồi deploy lại.

```python
# develop/app.py, dòng 21–22
DEBUG = True
MAX_TOKENS = 500
```

3. **`print()` thay cho logging, và in luôn secret.** Log aggregator không parse được dòng chữ tự do. Dòng in key còn làm secret xuất hiện ở stdout, nơi platform thường thu thập log.

```python
# develop/app.py, dòng 33–34
print(f"[DEBUG] Got question: {question}")
print(f"[DEBUG] Using key: {OPENAI_API_KEY}")  # log ra secret
```

4. **Không có health check.** Không có `GET /health` hay `GET /ready`. Platform không có cách nào biết process còn sống hoặc đã sẵn sàng nhận traffic, nên không restart đúng lúc và cũng không rút instance hỏng khỏi load balancer.

5. **Không xử lý tắt an toàn.** Không có handler `SIGTERM` và không có lifespan shutdown. Railway/Render/Docker gửi `SIGTERM` trước khi giết process. Không bắt tín hiệu này thì request đang xử lý bị cắt giữa chừng.

6. **Port cố định 8000.** Cloud inject cổng qua biến `PORT`. App không đọc biến đó thì platform báo app không lắng nghe đúng cổng và health check fail.

```python
# develop/app.py, dòng 49–53
uvicorn.run(
    "app:app",
    host="localhost",   # chỉ chạy được trên local
    port=8000,          # cứng port
    reload=True         # debug reload trong production
)
```

7. **Bind `localhost`.** Trong container, process chỉ nghe trên loopback của chính container. Nginx hoặc platform ở network khác không kết nối được. Production phải bind `0.0.0.0`.

8. **`reload=True` luôn bật.** Reloader là công cụ lúc sửa code. Trên production nó tốn CPU, theo dõi file, và restart ngoài ý muốn.

### Exercise 1.2: Chạy bản develop

Đã cài `01-localhost-vs-production/develop/requirements.txt` và chạy `python app.py`. Uvicorn báo `Uvicorn running on http://localhost:8000`.

Lớp K5: bản develop nhận `question` qua query string. Lệnh JSON trong `CODE_LAB.md` trả 422.

```text
curl.exe -sS -i -X POST "http://localhost:8000/ask?question=Hello"
```

```text
HTTP/1.1 200 OK
content-type: application/json

{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

Cùng lúc, console của server in secret ra:

```text
[DEBUG] Got question: Hello
[DEBUG] Using key: sk-hardcoded-fake-key-never-do-this
[DEBUG] Response: Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.
```

Gửi JSON như `CODE_LAB.md` thì thiếu query `question`:

```text
HTTP/1.1 422 Unprocessable Content

{"detail":[{"type":"missing","loc":["query","question"],"msg":"Field required","input":null}]}
```

`GET /health` và `GET /ready` đều `404 Not Found`. App trả lời được câu hỏi, nhưng platform không kiểm tra sức khỏe được, và mỗi request làm secret xuất hiện trên log. Đó chưa phải production-ready.

### Exercise 1.3: So sánh với bản production

Đã copy `.env.example` thành `.env` trong `01-localhost-vs-production/production/`, nạp biến môi trường rồi chạy `python app.py`. Process bind `0.0.0.0:8000` (đọc từ `HOST` và `PORT`). Log khởi động: `OPENAI_API_KEY not set — using mock LLM` (cảnh báo, không crash, vì lab dùng mock).

`POST /ask` của bản production nhận JSON body, không nhận query:

```text
curl.exe -sS -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" --data-binary "@ask.json"
```

Nội dung `ask.json`: `{"question":"Hello"}`

```text
HTTP/1.1 200 OK

{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","model":"gpt-4o-mini"}
```

Body rỗng `{"question":""}` trả 422 với `{"detail":"question field is required"}`, không lộ stack trace.

```text
GET /health → 200
{"status":"ok","uptime_seconds":5.6,"version":"1.0.0","environment":"development","timestamp":"2026-11-26T07:36:10.290650+00:00"}

GET /ready → 200
{"ready":true}
```

| Feature | Develop | Production | Tại sao quan trọng? |
| --- | --- | --- | --- |
| Config | Gán cứng trong `app.py` (`DEBUG`, `MAX_TOKENS`, port 8000) | `config.py` đọc `os.getenv` (`PORT`, `HOST`, `DEBUG`, `MAX_TOKENS`, …) | Cloud đặt `PORT` và các biến khác lúc chạy. Đổi staging sang production không cần sửa code. |
| Secrets | `"sk-hardcoded-fake-key-never-do-this"` và password trong `DATABASE_URL` | `OPENAI_API_KEY` và `AGENT_API_KEY` lấy từ env; `.env` không được commit, chỉ có `.env.example` | Key trong git là key đã lộ. Người lạ dùng key đó gọi API tính tiền vào tài khoản của mình. `config.py` còn fail fast nếu `ENVIRONMENT=production` mà thiếu `AGENT_API_KEY`. |
| Bind address | `host="localhost"` | `host` mặc định `0.0.0.0` | Container và load balancer không nói chuyện được với process chỉ nghe loopback. |
| Health check | Không có endpoint. `GET /health` ra 404 | `GET /health` luôn 200 khi process sống (liveness); `GET /ready` trả 200 khi đã startup xong, 503 khi `is_ready` còn false | Liveness để platform restart process chết. Readiness để load balancer không gửi user vào instance đang khởi động. Gộp hai cái làm một thì Redis chậm có thể khiến platform giết nhầm process vẫn sống. |
| Logging | `print`, kèm nguyên API key | `logger`, chỉ ghi `question_length` và `response_length`, không ghi key | Log production được thu vào hệ thống tập trung. In secret ở đó là phát tán secret. Log có cấu trúc thì lọc theo event được. |
| Shutdown | Tắt là chết ngay, không handler | `lifespan` hạ `is_ready` rồi chờ request hiện tại; `handle_sigterm` nhận `SIGTERM` | Deploy mới luôn bắt đầu bằng tắt bản cũ. Cắt request giữa chừng làm user nhận lỗi 502 dù câu trả lời gần xong. |
| Reload | `reload=True` luôn | `reload=settings.debug`, mặc định `DEBUG=false` | Reloader chỉ dành cho lúc sửa code trên máy. Production cần process ổn định. |
| CORS | Không cấu hình | `ALLOWED_ORIGINS` từ env | Trình duyệt chặn hoặc mở origin tùy môi trường, không hardcode domain frontend trong code. |

Một chỗ develop sai và production đã sửa, kèm dòng code:

- Develop in secret: `develop/app.py` dòng 34, `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")`. Lần chạy trên in ra `Using key: sk-hardcoded-fake-key-never-do-this`.
- Production không đưa key vào log. `production/app.py` dòng 111–115 chỉ ghi độ dài câu hỏi và IP:

```python
# production/app.py, dòng 111–115
logger.info(json.dumps({
    "event": "agent_request",
    "question_length": len(question),
    "client_ip": request.client.host,
}))
```

Key nằm ở `production/config.py` dòng 27: `os.getenv("OPENAI_API_KEY", "")`.

**Vì sao hardcode secret nguy hiểm.** Repo lab để public để nộp bài. Secret trong source đi theo mọi bản clone, mọi fork, và cả commit cũ. Thu hồi key trên dashboard chưa xóa được bản copy đã bị kéo về máy người khác.

**Vì sao cần health check.** Platform không đọc được ý định của process. Nó chỉ gọi một URL. Không có URL đó thì nó không biết nên restart, và load balancer không biết nên ngừng gửi request.

**Graceful shutdown là gì.** Khi nhận `SIGTERM`, app ngừng nhận request mới (`is_ready = False`), chờ request đang chạy trả xong, đóng kết nối, rồi thoát mã 0. `docker stop` và rolling deploy đều dựa vào khoảng chờ này. Không xử lý thì process bị `SIGKILL` sau timeout và user đang chờ câu trả lời bị đứt.

Ghi chú lần chạy: log JSON của app (`event: startup`, `agent_request`) không xuất hiện trên console. `config.py` gọi `logging.warning` lúc import, trước `logging.basicConfig` trong `app.py`, rồi `uvicorn.run` cấu hình lại logging. Hành vi API vẫn đúng như bảng trên; định dạng log nhìn thấy ở code, không thấy thêm dòng JSON application trên stdout lần này.

## Part 2: Docker

Build từ gốc repo, vì Dockerfile `COPY` theo đường dẫn tính từ gốc. Không cần API key: cả hai image dùng mock LLM. File `02-docker/production/.env.local` để trống thì Compose vẫn lên được.

### Exercise 2.1: Dockerfile cơ bản

Đọc `02-docker/develop/Dockerfile`.

1. **Base image:** `python:3.11` (bản full, không phải slim). Image này đã có Python 3.11 và nhiều gói hệ thống, nên nặng.
2. **Working directory:** `/app`. Mọi lệnh `COPY`, `RUN`, `CMD` phía sau chạy trong thư mục này.
3. **Vì sao `COPY requirements.txt` đứng trước `COPY` code:** Docker cache theo từng layer. Layer `pip install` chỉ bị làm lại khi `requirements.txt` đổi. Sửa `app.py` thì build dùng lại layer đã cài thư viện. Nếu copy cả source trước rồi mới `pip install`, mỗi lần sửa một dòng code phải cài lại toàn bộ dependency.
4. **CMD và ENTRYPOINT:** `CMD` là lệnh mặc định khi container start, và bị thay hết nếu `docker run` thêm lệnh khác (`docker run my-agent:develop sh`). `ENTRYPOINT` là chương trình luôn chạy; phần thêm trên `docker run` được nối vào làm tham số. Dockerfile này chỉ có `CMD ["python", "app.py"]`, không đặt `ENTRYPOINT`.

### Exercise 2.2: Build và chạy image develop

```text
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .
docker run -d --name k5-cp2-develop -p 8000:8000 my-agent:develop
```

`docker images` báo `my-agent:develop` nặng **1.67GB**.

Bản develop trong container cũng nhận `question` qua query. JSON bị 422.

```text
GET /health → 200
{"status":"ok","uptime_seconds":9.2,"container":true}

POST /ask?question=What%20is%20Docker → 200
{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}

POST /ask với JSON {"question":"What is Docker?"} → 422
{"detail":[{"type":"missing","loc":["query","question"],"msg":"Field required","input":null}]}
```

Log container: `Uvicorn running on http://0.0.0.0:8000`. Cùng một image chạy được mà không cần cài Python trên máy.

### Exercise 2.3: Multi-stage và kích thước

Đọc `02-docker/production/Dockerfile`.

- **Stage 1, tên `builder`:** từ `python:3.11-slim`, cài `gcc` và `libpq-dev` để biên dịch dependency, rồi `pip install --user` vào `/root/.local`. Stage này không được deploy.
- **Stage 2, tên `runtime`:** bắt đầu lại từ `python:3.11-slim` sạch, tạo user `appuser` không phải root, chỉ `COPY --from=builder` thư mục `/root/.local`, copy `main.py` và `utils/mock_llm.py`, thêm `HEALTHCHECK`, chạy `uvicorn` bằng user thường.

Image nhỏ hơn vì bản develop đứng trên `python:3.11` full (compiler, tài liệu, gói hệ thống không cần lúc chạy). Bản production bỏ cả stage builder: `gcc`, `libpq-dev` và cache apt không đi vào image cuối. Image cuối chỉ còn runtime slim cộng site-packages và source.

```text
docker build -f 02-docker/production/Dockerfile -t my-agent:advanced .
docker images my-agent
```

```text
my-agent:develop    1.67GB
my-agent:advanced   240MB
```

Quy 1.67GB về MB theo đơn vị `docker images` in ra (1 GB = 1000 MB): 1670 MB. Phần production nhỏ hơn `(1670 − 240) / 1670 = 85.6%`.

### Exercise 2.4: Docker Compose

Đọc `02-docker/production/docker-compose.yml`. Chạy với tên project riêng để không đụng image `production-agent` của bài sau:

```text
docker compose -p k5-day14-docker up -d --build
```

`docker compose ps` thấy 4 service, mỗi service một container:

| Service | Image | Cổng trên máy | Trạng thái lúc test |
| --- | --- | --- | --- |
| nginx | nginx:alpine | 80 và 443 | Up |
| agent | build từ Dockerfile production | không mở ra máy, chỉ 8000 trong mạng Docker | healthy |
| redis | redis:7-alpine | không mở ra máy | healthy |
| qdrant | qdrant/qdrant:v1.9.0 | không mở ra máy | healthy |

File comment nói agent có 2 replica, nhưng compose không đặt `scale`. Lần chạy này là 1 agent. Nginx upstream cũng chỉ có `server agent:8000`.

```text
Client
  │  http://localhost:80
  ▼
Nginx (reverse proxy, limit 10 request/giây)
  │  mạng Docker "internal", tên DNS agent:8000
  ▼
Agent (uvicorn, PORT=8000)
  ├── REDIS_URL=redis://redis:6379/0
  └── QDRANT_URL=http://qdrant:6333
```

Agent chỉ start sau khi Redis và Qdrant healthy (`depends_on` + healthcheck). Nginx không publish cổng của agent: client chỉ vào được qua cổng 80. Ba service nói chuyện bằng tên service trên network `internal`, không cần IP.

Test qua Nginx (bản production nhận JSON, không nhận query):

```text
GET http://localhost/health → 200
Server: nginx
{"status":"ok","uptime_seconds":12.6,"version":"2.0.0","timestamp":"2026-11-26T07:48:35.744126"}

GET http://localhost/ready → 200
{"ready":true}

POST http://localhost/ask
Content-Type: application/json
{"question":"Explain microservices"}
→ 200
{"answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận."}
```

Header phản hồi có `Server: nginx` và `X-Frame-Options: DENY`, tức request đi qua Nginx rồi mới tới agent.

Sau khi test: `docker compose -p k5-day14-docker down`.

## Part 3: Cloud Deployment

Nền tảng chính là Render. Agent Part 6 chạy tại `https://day14-agent-w8dm.onrender.com`, Blueprint `day14-agent`, commit `3dbdd8b`. Service Docker plan free, trạng thái Live. Redis là Key Value `day14-redis` cùng Blueprint. `AGENT_API_KEY` do Render sinh, không ghi vào repo.

Bốn lệnh tự kiểm, chỉ lấy mã HTTP:

```text
GET /health                         → 200  {"status":"ok"}
GET /ready                          → 200  {"ready":true}
POST /ask  không có X-API-Key       → 401
POST /ask  đúng X-API-Key           → 200
{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","cost_usd":7.95e-06}
```

`/ready` trả 200 nghĩa là web service đã nối được Redis trên Render.

### So sánh railway.toml và render.yaml

`railway.toml` chỉ nói cách build và cách kiểm sức khỏe của một service: `builder = DOCKERFILE`, `healthcheckPath = /health`. File không tạo Redis. Muốn có `REDIS_URL` và `AGENT_API_KEY` thì phải tạo trên dashboard Railway rồi gắn vào service.

`render.yaml` mô tả cả stack. Một Blueprint tạo web service Docker và Key Value, nối `REDIS_URL` bằng `fromService` / `connectionString`, và `AGENT_API_KEY` dùng `generateValue` nên secret không nằm trong git. File nằm trong `06-lab-complete/`, nên lúc tạo Blueprint phải điền path `06-lab-complete/render.yaml`. Service web có `rootDir: 06-lab-complete` để Docker build đúng thư mục đó, không build gốc repo.

Hai file cùng trỏ health check vào `/health`. Khác nhau ở chỗ Railway để người dùng ráp Redis và secret trên dashboard, còn Render khai hết trong một file.

### Exercise 3.3: Cloud Run

`cloudbuild.yaml` chạy khi push lên `main`. Pipeline có bốn bước nối nhau: chạy pytest, build image gắn tag theo commit, push image lên Container Registry, rồi `gcloud run deploy`. `service.yaml` là định nghĩa service sau khi đã có image: public, giữ ít nhất 1 instance và tối đa 10, mỗi instance tối đa 80 request, health check `/health` và `/ready`. `OPENAI_API_KEY` và `AGENT_API_KEY` lấy từ Secret Manager, không ghi trong file.

## Part 4: API Security

Ba lớp chặn ba việc khác nhau. Rate limit chặn gọi quá nhanh. Cost guard chặn tiêu quá tiền. Một lớp không thay được lớp kia: 10 request/phút vẫn có thể rất đắt nếu mỗi request tốn nhiều token, và vài request rẻ vẫn có thể làm sập server nếu đến cùng một lúc.

### Exercise 4.1: API key

Đọc `04-api-gateway/develop/app.py`. Key được kiểm ở `verify_api_key` (dòng 39–54), gắn vào `POST /ask` bằng `Depends`. Giá trị đúng là biến môi trường `AGENT_API_KEY`.

- Không có header `X-API-Key` → **401**.
- Có header nhưng sai giá trị → **403**.
- Đúng key → **200**.
- `GET /` và `GET /health` không đi qua dependency này, nên platform vẫn kiểm tra sức khỏe được khi không có key.

Đổi key bằng cách đặt `AGENT_API_KEY` mới rồi tắt và bật lại process. Key không nằm trong source, nên không cần sửa code và không commit key. Key cũ hết tác dụng ngay vì process đọc env lúc khởi động.

Chạy: `AGENT_API_KEY=secret-key-123 python app.py`.

Không có key:

```text
HTTP/1.1 401 Unauthorized
content-type: application/json

{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```

Đúng key `X-API-Key: secret-key-123`:

```text
HTTP/1.1 200 OK
content-type: application/json

{"question":"Hello","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
```

Sai key trả `403` với `{"detail":"Invalid API key."}`.

### Exercise 4.2: JWT

Đọc `04-api-gateway/production/auth.py`. Luồng:

1. `POST /auth/token` nhận username và password. `authenticate_user` đối chiếu bảng demo. Đúng thì `create_token` ký JWT bằng `JWT_SECRET`, thuật toán HS256, hạn 60 phút. Payload có `sub` (username), `role`, `iat`, `exp`.
2. Client gửi `Authorization: Bearer <token>` lên `POST /ask`.
3. `verify_token` kiểm chữ ký và hạn. Hết hạn hoặc không có token → **401**. Chữ ký sai → **403**. Server không cần lưu session: user và role nằm trong token.

`CODE_LAB.md` ghi `POST /token` với `admin` / `secret`. Bản trong repo không có endpoint đó. Lấy token ở `POST /auth/token` với `student` / `demo123`. Gửi `admin` / `secret` trả **401** `{"detail":"Invalid credentials"}`.

Token nhận được dài 168 ký tự, `token_type=bearer`, `expires_in_minutes=60`. Không dán token vào bài.

Không có token:

```text
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer

{"detail":"Authentication required. Include: Authorization: Bearer <token>"}
```

Có token của `student`:

```text
HTTP/1.1 200 OK

{"question":"Explain JWT","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","usage":{"requests_remaining":9,"budget_remaining_usd":1.9e-05}}
```

`requests_remaining: 9` nghĩa là vừa dùng 1 suất trong hạn 10. Trường `budget_remaining_usd` trong response này đang nhận `usage.total_cost_usd` từ `app.py`, nên 1.9e-05 là chi phí đã ghi, không phải số tiền còn lại. Số còn lại nằm ở `/me/usage` bên dưới.

`teacher` / `teach456` là role `admin`. `student` là role `user`.

### Exercise 4.3: Rate limit

Đọc `rate_limiter.py`. Thuật toán là **sliding window**: mỗi user một hàng timestamp. Request cũ hơn 60 giây bị bỏ khỏi hàng. Số timestamp còn lại trong 60 giây mà đạt ngưỡng thì **429**, kèm `Retry-After`.

| Role | Limiter | Ngưỡng |
| --- | --- | --- |
| `user` (`student`) | `rate_limiter_user` | 10 request / 60 giây |
| `admin` (`teacher`) | `rate_limiter_admin` | 100 request / 60 giây |

Admin không được bỏ limit. Admin chỉ có ngưỡng cao hơn, vì `app.py` chọn limiter theo `role` trong token. State nằm trong RAM của process, nên restart là đếm lại từ đầu. File ghi chú bản production thật nên chuyển bộ đếm sang Redis để nhiều instance dùng chung.

Vòng lặp 20 lần với token `student` (đã che):

```text
1–10  → 200
11–20 → 429
```

Lần thứ 11 trở đi:

```text
HTTP/1.1 429 Too Many Requests
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
retry-after: 55

{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":55}}
```

Request không có token trả 401 trước khi đếm, nên không làm giảm suất của user.

### Exercise 4.4: Cost guard

`cost_guard.py` đã có logic, không cần viết thêm cho bài K5. Cách nó chặn tiền:

- Mỗi user một `UsageRecord` trong ngày (`YYYY-MM-DD`). Sang ngày mới thì record được tạo lại, tức ngân sách ngày được reset.
- `check_budget` chạy **trước** khi gọi LLM. Tổng toàn hệ thống đạt `global_daily_budget_usd` (10 USD) thì **503**. Chi phí của riêng user đạt `daily_budget_usd` (1 USD) thì **402**. Đạt 80% thì chỉ ghi warning, vẫn cho gọi.
- `record_usage` chạy **sau** khi có câu trả lời. Token đầu vào và đầu ra nhân giá `0.00015` và `0.0006` USD / 1.000 token, cộng vào record của user và vào tổng toàn cục.
- Bộ đếm đang nằm trong RAM. Ghi chú trong file nói bản chạy nhiều instance phải để Redis hoặc database, nếu không mỗi process có một ngân sách riêng và restart làm mất số đã tiêu.

Sau 10 request thành công, `GET /me/usage` (cùng user, endpoint này không bị rate limit):

```text
HTTP/1.1 200 OK

{"user_id":"student","date":"2026-11-26","requests":10,"input_tokens":40,"output_tokens":316,"cost_usd":0.000196,"budget_usd":1.0,"budget_remaining_usd":0.999804,"budget_used_pct":0.0}
```

10 request mock chỉ tốn khoảng 0.0002 USD trên ngân sách 1 USD, nhưng request thứ 11 đã bị **429**. Rate limit cắt tốc độ trước khi cost guard kịp cắt tiền. Đó là lý do phải có cả hai.

## Part 5: Scaling & Reliability

`/health` và `/ready` trả lời hai câu khác nhau. `/health` (liveness) hỏi process còn sống không. Platform thấy mã không phải 200 thì restart container. Endpoint này phải trả 200 cả khi Redis chậm, nếu không platform giết nhầm process vẫn chạy tốt. `/ready` (readiness) hỏi instance có nên nhận user mới không. Load balancer thấy 503 thì ngừng gửi traffic tới instance đó, nhưng không giết process. Trong `05-scaling-reliability/develop/app.py`, `/ready` trả 503 khi `_is_ready` còn false (đang khởi động hoặc đang tắt). Trong bản production, `/ready` còn trả 503 khi `ping` Redis thất bại, còn `/health` vẫn trả HTTP 200 và chỉ ghi `status: degraded` trong body.

State trong RAM hỏng khi có nhiều instance vì mỗi process một bộ nhớ. User nói tên ở instance 1, câu sau rơi vào instance 2 thì instance 2 không có đoạn hội thoại đó. Redis dùng chung một key `session:{id}` nên instance nào cũng đọc được.

### Exercise 5.1: Health check

Chạy `05-scaling-reliability/develop/app.py`. `POST /ask` của bản này nhận `question` trên query, và mock chờ khoảng 3 giây.

```text
GET /health → HTTP/1.1 200 OK
{"status":"degraded","uptime_seconds":38.5,"version":"1.0.0","environment":"development","timestamp":"2026-11-26T08:11:06.448729+00:00","checks":{"memory":{"status":"degraded","used_percent":94.4}}}

GET /ready → HTTP/1.1 200 OK
{"ready":true,"in_flight_requests":1}

POST /ask?question=hello → HTTP/1.1 200 OK
{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

`/health` vẫn là HTTP 200 dù body ghi `degraded`, vì RAM máy lúc đo là 94.4%, trên ngưỡng 90% trong code. Platform chỉ nhìn mã HTTP thì không restart. `in_flight_requests: 1` trên `/ready` là chính request `/ready` đang được middleware đếm.

### Exercise 5.2: Graceful shutdown

`handle_sigterm` ghi log khi nhận tín hiệu 15. Uvicorn gọi lifespan shutdown: `_is_ready = False` (từ chối request mới, `/ready` thành 503), chờ `_in_flight_requests` về 0 tối đa 30 giây, rồi thoát.

`docker stop` gửi SIGTERM tới process trong container. Request `POST /ask?question=Long%20task` đang chạy (mock khoảng 3 giây) vẫn trả xong:

```text
HTTP/1.1 200 OK
{"answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

Log container sau đó:

```text
INFO:     Shutting down
INFO:     172.17.0.1 - "POST /ask?question=Long%20task HTTP/1.1" 200 OK
INFO 🔄 Graceful shutdown initiated...
INFO ✅ Shutdown complete
INFO Received signal 15 — uvicorn will handle graceful shutdown
```

Request đang xử lý được trả 200. Process tắt sau khi request xong, không cắt giữa chừng.

### Exercise 5.3: Stateless

`05-scaling-reliability/production/app.py` không giữ hội thoại trong biến toàn cục. `save_session` / `load_session` ghi JSON vào Redis, key `session:{session_id}`, TTL 3600 giây. Không có Redis thì code rơi về dict trong RAM và tự ghi cảnh báo "not scalable". Ba container lúc chạy đều log `Connected to Redis` và `storage: redis`.

### Exercise 5.4 và 5.5: Ba instance và một session

```text
docker compose -p k5-day14-scaling up -d --build --scale agent=3
```

Stack mở cổng **8080**, không phải 80. Endpoint hội thoại là `POST /chat`, không phải `/ask`. Có file `.env.local` trống. `docker compose ps` thấy `agent-1`, `agent-2`, `agent-3`, `redis-1` (healthy), `nginx-1` map `8080->80`.

Tám lần `GET /health` qua Nginx lần lượt rơi vào ba IP và ba id: `instance-de4299`, `instance-becf1a`, `instance-507a5e`. Header `X-Served-By` đổi theo từng request. Nginx chia vòng tròn.

`python test_stateless.py` gửi 5 câu trong cùng một session rồi đọc history. Script không tắt instance nào.

```text
Session ID: 81cabef0-f675-4593-8c7c-9b17fb7f45cd

Request 1: [instance-507a5e]  What is Docker?
Request 2: [instance-de4299]  Why do we need containers?
Request 3: [instance-becf1a]  What is Kubernetes?
Request 4: [instance-507a5e]  How does load balancing work?
Request 5: [instance-de4299]  What is Redis used for?

Instances used: instance-de4299, instance-507a5e, instance-becf1a
Total messages: 10
```

Năm câu đi qua cả ba instance mà history vẫn đủ 10 dòng (5 user + 5 assistant). Nếu history nằm trong RAM của từng process, instance nhận câu 2 không thấy câu 1.

Sau script, tắt `agent-1` (`instance-507a5e`) rồi gửi thêm một câu cùng `session_id`. Nginx thử IP của instance đã tắt rồi chuyển sang instance còn sống. Header có hai địa chỉ `X-Served-By: 172.23.0.5:8000, 172.23.0.4:8000`. Câu trả lời do `instance-de4299` phục vụ, `storage` là `redis`. History tăng lên 12 dòng, gồm cả năm câu trước. Instance chết không làm mất hội thoại, và traffic sang instance khác.

Xong thì `docker compose -p k5-day14-scaling down`.

## AI log

Mỗi dòng: hỏi Cursor, kết quả nhận được, rồi tự chạy lại lệnh. Số trong bài lấy từ output đó, không chép README.

- **CP1.** So sánh develop và production. Develop `POST /ask?question=` trả 200, `GET /health` trả 404. Production `/health`, `/ready` và `POST /ask` JSON trả 200.
- **CP2.** Build hai image. `docker images` ra 1.67GB và 240MB. Request qua Nginx có header `Server: nginx`.
- **CP3.** Gọi API security. Thiếu key trả 401, đúng key trả 200, request 1–10 trả 200, request 11 trả 429. Token không dán vào bài.
- **CP4.** Health, graceful shutdown, 3 instance. `/health` vẫn 200 khi RAM 94.4%. `docker stop` để request đang chạy trả 200. History còn 10 dòng, sau khi tắt một agent còn 12.
- **CP5.** Sửa `06-lab-complete/` rồi chạy `check_production_ready.py` trong WSL. Script in `PASS 12/12`. Không sửa file chấm.
- **CP6.** Deploy Render. `https://day14-agent-w8dm.onrender.com`: `/health` 200, `/ready` 200, `/ask` thiếu key 401, có key 200. Key không ghi vào repo.
- **CP7.** Load test và eval. `eval_v2_fixed.json` đạt accuracy 1.0. Số trong `BENCHMARK_REPORT.md` mục 1–3 khớp file JSON.
- **CP8.** Stack Grafana/Jaeger/Prometheus và Locust 1 rồi 3 instance. Hai alert firing sau 96 giây và 156 giây. `trace_id` trong báo cáo có trong log. Số mục 4–5 khớp CSV.

## Part 6: Final Project

Code nằm trong `06-lab-complete/`. Bản này đã deploy lên Render tại `https://day14-agent-w8dm.onrender.com` (mục Part 3). `render.yaml` khai Redis và `healthCheckPath: /health`. `AGENT_API_KEY` dùng `generateValue`, không ghi key vào file.

`/health` luôn trả HTTP 200 khi process còn sống, kể cả khi Redis không nối được. Platform dùng endpoint này để quyết định có giết container không. Redis chết mà `/health` trả 503 thì platform restart vòng lặp một process vẫn chạy tốt. `/ready` trả 503 khi Redis không ping được, để load balancer ngừng gửi request mới, nhưng không giết process. Script chấm xác nhận đúng cặp này: Redis trỏ vào cổng đóng thì `/ready` là 503 và `/health` vẫn 200.

Rate limit là sliding window 60 giây trong Redis, key theo API key. Script đặt `RATE_LIMIT_PER_MINUTE=5` và 2 worker: quá 5 request thành công thì 429, restart process vẫn 429 vì bộ đếm không nằm trong RAM. Cost guard đọc `DAILY_BUDGET_USD`. Script đặt ngân sách `0.000001` USD thì request đầu đã 402. SIGTERM lúc đang có request: request đó vẫn 200, process thoát exit code 0. `docker stop` xong trong 0.7 giây. Image build được là 56 MB.

Chạy trong Ubuntu (WSL), `os.name=posix`, Docker server 29.7.2:

```text
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```
