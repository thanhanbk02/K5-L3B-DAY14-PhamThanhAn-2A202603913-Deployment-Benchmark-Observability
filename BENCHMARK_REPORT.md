# Benchmark & Observability Report — Day 14

> Số ở mục 1–3 lấy từ file JSON trong `06-lab-complete/benchmark-observability/develop/reports/`. Mục 4–6 là stack production, làm ở CP8.

**Họ tên:** Phạm Thanh An
**Ngày chạy:** 2026-11-26
**Môi trường:** Windows 10, Ubuntu WSL, Python 3.12. Agent develop chạy trực tiếp (không Docker). Máy AMD Ryzen 9 3900X, 24 luồng, 15.9 GB RAM.

---

## 1. SLO của agent

Ngưỡng latency và error rate là mặc định của `load_test.py`. Ngưỡng accuracy là mức quality gate của job CI ở Exercise 7.3.

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | p95 là ngưỡng 95% request phải nhanh hơn. Average bị vài request chậm kéo lệch, nên không dùng làm SLO. |
| Error rate `/ask` | < 2% | Mock mặc định lỗi upstream khoảng 1% (`MOCK_ERROR_RATE=0.01`). Ngân sách 2% chừa chỗ cho lỗi đó mà vẫn bắt được lỗi hàng loạt. |
| Accuracy trên golden dataset | ≥ 85% | Job CI chạy `run_eval.py --min-accuracy 0.85`. Dưới mức này exit code là 1, PR không merge. |

### Exercise 7.1

Sau một `POST /ask` ("Prometheus thu thập metrics như thế nào?") lên agent v2 cổng 8002, `GET /metrics` có đủ ba loại:

- Counter: `http_requests_total{method="POST",route="/ask",status="200"} 1.0`
- Gauge: `agent_in_flight_requests 0.0`
- Histogram: `http_request_duration_seconds_bucket{le="2.0",method="POST",route="/ask"} 1.0` và `agent_question_length_chars_bucket{le="50.0"} 1.0`

`agent_question_length_chars` là histogram thêm trong `app.py`, observe `len(body.question)` trước khi gọi LLM. Độ dài là số liên tục, nên để trong bucket. Nếu gắn độ dài thành label thì mỗi độ dài là một time series.

Middleware ghi label `route` bằng template (`/ask`) hoặc `unmatched`. Nếu thay bằng URL thật, bot gọi `/wp-admin`, `/.env`, `/a1b2c3`... mỗi path thành một series mới của counter và histogram. Prometheus giữ hết các series đó trong RAM.

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

Agent v2, cổng 8002, 300 request mỗi lần. SLO trong file JSON: p95 ≤ 500 ms và error rate ≤ 2%.

### 2.1 Concurrency vs latency (agent v2)

`MOCK_SLOW_RATE` để mặc định 0.03.

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 4.27 | 190.3 | 219.3 | 1690.9 | 0.67% | PASS |
| 10 | 36.54 | 189.0 | 221.0 | 1686.8 | 0.67% | PASS |
| 50 | 83.48 | 226.5 | 1115.1 | 1677.0 | 0.00% | FAIL (p95) |
| 100 | 50.32 | 974.1 | 5087.5 | 5352.8 | 0.67% | FAIL (p95) |

**Nhận xét:** RPS không tăng tuyến tính. Từ 1 lên 10 request song song, RPS tăng khoảng 8.6 lần (4.27 → 36.54), không phải 10 lần. Mức 50 đạt 83.48 req/s, cao nhất trong bốn mức. Mức 100 tụt xuống 50.32 req/s và p50 nhảy từ 226.5 ms lên 974.1 ms. Mỗi câu mock đã mất khoảng 150–220 ms. Khi số request chờ vượt quá số việc process xử lý kịp, chúng xếp hàng, nên thêm concurrency không thêm throughput.

### 2.2 Tail latency

Cùng 300 request, concurrency 20. Chỉ đổi `MOCK_SLOW_RATE` rồi bật lại v2.

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 190.6 | 221.4 | 241.4 |
| 0.03 (mặc định) | 222.2 | 224.1 | 1697.8 |
| 0.1 | 324.7 | 1673.4 | 1714.1 |

**Nhận xét:** p99 nhạy nhất. Khi 3% request bị cộng thêm khoảng 1500 ms, avg chỉ từ 190.6 lên 222.2 ms, p95 gần như đứng yên (221.4 → 224.1), còn p99 nhảy từ 241.4 lên 1697.8 ms. Ở mức 10% request chậm, p95 cũng vọt lên 1673.4 ms trong khi avg chỉ còn 324.7 ms. Average bị số đông request nhanh kéo xuống, nên SLO đặt theo average sẽ báo xanh trong lúc một phần user đã chờ hơn 1.5 giây. SLO latency nên đặt theo p95 hoặc p99.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

23 câu trong `eval/golden_dataset.jsonl`. Cổng v1 là 8001, v2 là 8002. Quality gate mặc định của script là accuracy ≥ 80% và không regression. Lần sau khi sửa KB dùng `--min-accuracy 1.0`. Lần đo 100% bật v2 với `MOCK_ERROR_RATE=0` để một lỗi mock 503 không làm rơi câu đã trả lời đúng.

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100% (23/23) |
| Avg tokens / câu | 57.4 | 108.8 | 113.7 |
| Tổng cost (USD) | 0.000408 | 0.000758 | 0.000790 |
| Cost / câu đúng (USD) | 0.00040815 | 0.00003607 | 0.00003436 |
| Quality gate | FAIL | PASS (≥ 80%) | PASS (≥ 100%) |

File: `reports/eval_v1.json`, `reports/eval_v2.json`, `reports/eval_v2_fixed.json`. Lệnh cuối in `Quality gate (accuracy ≥ 100%, không regression): ✅ PASS`, exit code 0. Không có câu nào từ đúng thành sai so với `eval_v2.json`.

**Những câu v2 trả lời sai ban đầu và cách bạn sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| security-02 | token, hết hạn, chữ ký | Thêm mục `jwt` vào `KNOWLEDGE_BASE`: JWT là token có chữ ký và thời điểm hết hạn, khác API key cố định. |
| scaling-03 | cpu, memory, custom metrics | Thêm mục `hpa` / `kubernetes`: HPA scale pod theo CPU, memory hoặc custom metrics. |

Trước khi sửa, hai câu này nhận câu trả lời generic, score 0. Các câu v2 đã đúng vẫn đúng sau khi thêm tài liệu.

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

v2 retrieve tài liệu nên prompt dài hơn: 108.8 token/câu so với 57.4, tổng cost cả bộ 0.000758 USD so với 0.000408 USD, p95 eval 213.1 ms so với 186.0 ms. Đổi lại accuracy từ 4.3% lên 91.3%. Cost cho mỗi câu đúng giảm từ 0.00040815 USD xuống 0.00003607 USD, vì v1 tiêu tiền cho 22 câu sai. Sửa KB thêm hai mục làm cost/câu đúng giảm tiếp còn 0.00003436 USD. v2 đắt hơn và chậm hơn một chút trên mỗi câu, nhưng rẻ hơn nếu tính trên câu trả lời đúng.

Job CI nằm ở `.github/workflows/eval.yml`. Job cài dependency, bật agent v2 với `MOCK_ERROR_RATE=0`, rồi chạy `run_eval.py --min-accuracy 0.85`. Script trả exit code 1 khi accuracy thấp hơn ngưỡng hoặc có regression, nên bước đó fail và pull request không được merge.

---

## 4. Observability stack (production)

Chưa chạy. Phần này thuộc CP8.

### 4.1 Screenshot

- [ ] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals)
- [ ] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian)
- [ ] Một trace lỗi trong Jaeger (có event `exception`)
- [ ] Trang Alerts của Prometheus với ít nhất 1 alert đang **firing**

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | | | |
| B | `MOCK_SLOW_RATE=0.3` | | | |
| C | `LLM_MODEL=mock-llm-large` | | | |
| D | `docker pause` 1 instance | | | |
| E | `AGENT_VERSION=v1` | | | |

### 4.3 Debug bằng trace

Chưa có trace. Làm ở CP8.

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

Chưa chạy. Làm ở CP8.

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | | | | | |
| 3 | | | | | |

---

## 6. Kết luận

- 3 điều rút ra từ số đo local:
  1. p99 lộ request chậm mà average và đôi khi cả p95 vẫn giấu được. SLO latency phải nhìn đuôi phân phối.
  2. Thêm concurrency chỉ tăng RPS tới một điểm. Ở 100 request song song, RPS giảm và p95 vượt 5 giây.
  3. So hai phiên bản bằng cost/câu đúng, không bằng tổng cost. v2 tốn token hơn nhưng mỗi câu đúng rẻ hơn vì v1 hầu như trả lời sai.
- Metric và alert cho production thật sẽ bổ sung khi chạy stack ở CP8.
