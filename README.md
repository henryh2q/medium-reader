# Đọc gì hôm nay: Engineering blog reader tiếng Việt (MVP)

Lấy bài từ các engineering blog qua RSS, dùng Claude chấm điểm "đáng đọc", dịch bài
tốt nhất sang tiếng Việt, và giải thích thuật ngữ khi bôi đen text.

## Cài đặt

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # điền ANTHROPIC_API_KEY
```

## Chạy

```bash
python pipeline.py            # lấy RSS -> chấm điểm -> dịch (tối đa 3 bài/lần)
uvicorn app:app --reload      # mở http://127.0.0.1:8000
```

Đọc trên điện thoại cùng mạng LAN: `uvicorn app:app --host 0.0.0.0`, rồi mở `http://<ip-máy>:8000`.

Chạy pipeline tự động mỗi sáng 7h (crontab):

```
0 7 * * * cd /path/to/medium-reader && .venv/bin/python pipeline.py >> data/pipeline.log 2>&1
```

## Cấu trúc

| File | Vai trò |
|---|---|
| `config.py` | Danh sách feed, mô tả sở thích, model, ngưỡng điểm |
| `fetcher.py` | Đọc RSS, HTML -> Markdown, phát hiện bài member-only |
| `llm.py` | 3 prompt: chấm điểm, dịch (theo đoạn, giữ nguyên code), giải thích thuật ngữ |
| `pipeline.py` | `fetch` -> `score` -> `translate`, chạy từng bước được |
| `app.py` | FastAPI: danh sách bài, trang đọc, `POST /api/explain` (có cache SQLite) |
| `static/reader.js` | Bôi đen -> nút "Giải thích thuật ngữ" -> panel; chuyển VI/EN |

## Tinh chỉnh

- **Feed:** sửa `FEEDS` trong `config.py`, điền RSS của các engineering blog bạn muốn theo dõi.
- **Gu đọc:** sửa `INTERESTS`, tăng hoặc giảm `SCORE_THRESHOLD` (mặc định 7).
- **Chi phí:** chấm điểm dùng Haiku (chỉ gửi 3.000 ký tự đầu). Dịch và giải thích dùng Sonnet.
  Giải thích được cache theo thuật ngữ + bài, nên tra lại không tốn thêm token.

## Giới hạn đã biết

- Bài member-only: RSS chỉ có đoạn đầu, nên bị bỏ qua trước bước chấm điểm (không tốn
  token) và app chỉ hiển thị tóm tắt kèm link bài gốc nếu đã có điểm từ trước.
- Dùng cho cá nhân. Không public bản dịch vì nội dung thuộc bản quyền tác giả.
- Bôi đen cắt ngang nhiều định dạng (vd. nửa chữ đậm) vẫn giải thích được, chỉ là không tô vệt dạ quang.

## Deploy lên Railway

App chạy thành **một service duy nhất**: web + pipeline hằng ngày trong cùng process.
Lý do: volume trên Railway chỉ gắn được vào một service, nên một cron service tách riêng
sẽ không đọc/ghi được file SQLite.

1. Đẩy code lên GitHub (file `.env` và thư mục `data/` đã nằm trong `.gitignore`).
2. Railway → New Project → Deploy from GitHub repo. Railway tự nhận `Dockerfile` và `railway.json`.
3. Chuột phải vào service → **Attach volume**, mount path `/data`.
4. Tab **Variables**:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   BASIC_AUTH_USER=haihq
   BASIC_AUTH_PASS=<mật khẩu dài, ngẫu nhiên>
   DB_PATH=/data/reader.db
   PIPELINE_HOUR=7
   ```
5. Settings → Networking → **Generate Domain**.
6. Settings → giữ **1 replica** và **tắt Serverless** (app sleeping). Nếu app ngủ, lịch chạy hằng ngày sẽ không chạy.
7. Mở domain, đăng nhập, bấm **Lấy bài mới ngay** cho lượt đầu tiên.

Bảo mật:
- Trên Railway, nếu thiếu `BASIC_AUTH_USER`/`BASIC_AUTH_PASS` thì app trả về 503 thay vì mở toang.
- Request POST từ domain khác bị chặn (chống CSRF).
- `/healthz` không cần đăng nhập, dành cho health check.
- Nên bật **Usage limit** trong phần billing của Railway, và đặt giới hạn chi tiêu ở Anthropic Console.
