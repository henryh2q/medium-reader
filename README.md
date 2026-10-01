# Đọc gì hôm nay: dịch bài đọc tiếng Việt (MVP)

Bạn tự chọn bài muốn đọc (qua extension trình duyệt), app dịch sang tiếng Việt bằng
Claude và cho bôi đen để giải thích thuật ngữ. Không tự động lấy/chấm điểm bài nào —
chỉ xử lý bài bạn chủ động đưa vào.

## Cài đặt

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # điền ANTHROPIC_API_KEY và IMPORT_TOKEN
```

## Chạy

```bash
uvicorn app:app --reload      # mở http://127.0.0.1:8000
```

Đọc trên điện thoại cùng mạng LAN: `uvicorn app:app --host 0.0.0.0`, rồi mở `http://<ip-máy>:8000`.

## Cấu trúc

| File | Vai trò |
|---|---|
| `config.py` | Model dùng để dịch/giải thích, token xác thực extension |
| `fetcher.py` | HTML (từ extension) -> Markdown |
| `llm.py` | Tóm tắt, dịch (theo đoạn, giữ nguyên code), giải thích thuật ngữ |
| `app.py` | FastAPI: danh sách bài, trang đọc, `POST /admin/import`, dịch 1 bài/hàng loạt |
| `static/translate.js` | Icon dịch cạnh từng bài + nút nổi mở modal "Dịch hàng loạt" (chọn tất cả) |
| `static/reader.js` | Bôi đen -> nút "Giải thích thuật ngữ" -> panel; chuyển VI/EN |
| `static/logo.svg` | Logo gốc (SVG) — nguồn sinh favicon và icon extension |
| `extension/` | Extension Chrome/Edge: đưa bài bạn đang đọc vào app |

## Đưa bài vào app (extension)

Mở bài bạn muốn đọc trên trình duyệt (đăng nhập tài khoản member nếu cần), bấm
extension để gửi **nội dung đã render trên trang** về app — không có bot nào tự động
truy cập trang nguồn thay bạn.

1. Đặt `IMPORT_TOKEN` (chuỗi ngẫu nhiên dài, khác `BASIC_AUTH_PASS`) trong `.env` hoặc
   biến môi trường Railway.
2. Chrome/Edge → `chrome://extensions` → bật **Developer mode** → **Load unpacked** →
   chọn thư mục `extension/`.
3. Mở bài viết, đọc đến hết trang (để nội dung render đầy đủ).
4. Bấm icon extension → điền địa chỉ app và `IMPORT_TOKEN` → **Đưa bài đang mở vào app**.
5. Bài hiện ngay trên trang chủ kèm tóm tắt tiếng Anh (tự sinh lúc import).

**Lưu ý:** Chrome trên di động (Android/iOS) không hỗ trợ cài extension bên thứ ba —
đây là giới hạn của Chrome mobile, không phải của extension này. Chỉ dùng được trên
Chrome/Edge desktop.

## Dịch bài

- **Từng bài:** bấm icon ⇄ cạnh tiêu đề bài trong danh sách.
- **Hàng loạt:** bấm nút nổi ⇄ ở góc dưới phải → chọn các bài cần dịch (có checkbox
  "Chọn tất cả bài chưa dịch") → "Dịch các bài đã chọn". Mỗi bài dịch trong một thread
  nền riêng, không chặn lẫn nhau; bài đang dịch hoặc đã dịch tự động không xuất hiện
  trong danh sách chọn.

Bài đã dịch hiện tiêu đề và tóm tắt bằng tiếng Việt, không còn icon dịch (trạng thái
"đã dịch" thể hiện qua chính tiêu đề tiếng Việt, không cần nhãn riêng). Mỗi bài đã dịch
có ghi nguồn (link bài gốc + tác giả) ở cuối trang đọc, cùng dòng nhắc đây là bản dịch
không chính thức — bản quyền nội dung thuộc về tác giả gốc.

## Thêm vào màn hình chính (mobile)

- **iOS (Safari):** Share → "Add to Home Screen". Icon và tên app lấy từ thẻ
  `apple-touch-icon`/`apple-mobile-web-app-title` trong `templates/base.html`.
- **Android (Chrome):** menu ⋮ → "Add to Home screen", dùng `static/manifest.json`.
- Vì dùng Basic Auth, mỗi lần mở app từ màn hình chính (chế độ standalone) trình duyệt
  sẽ hỏi lại mật khẩu — đây là giới hạn của Basic Auth trong WebKit/Chrome standalone,
  không có cách bỏ qua nếu vẫn giữ Basic Auth (cách khắc phục là chuyển sang đăng nhập
  bằng cookie session, chưa áp dụng).

## Giới hạn đã biết

- Dùng cho cá nhân. Không public bản dịch vì nội dung thuộc bản quyền tác giả.
- Bôi đen cắt ngang nhiều định dạng (vd. nửa chữ đậm) vẫn giải thích được, chỉ là không tô vệt dạ quang.
- Trạng thái "đang dịch" lưu trong bộ nhớ process — chạy nhiều worker/instance cùng lúc
  có thể dịch trùng một bài (xem `Dockerfile`, cố định 1 worker).

## Deploy lên Railway

1. Đẩy code lên GitHub (file `.env` và thư mục `data/` đã nằm trong `.gitignore`).
2. Railway → New Project → Deploy from GitHub repo. Railway tự nhận `Dockerfile` và `railway.json`.
3. Chuột phải vào service → **Attach volume**, mount path `/data`.
4. Tab **Variables**:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   BASIC_AUTH_USER=haihq
   BASIC_AUTH_PASS=<mật khẩu dài, ngẫu nhiên>
   IMPORT_TOKEN=<chuỗi ngẫu nhiên dài khác, cho extension>
   DB_PATH=/data/reader.db
   ```
5. Settings → Networking → **Generate Domain**.
6. Settings → giữ **1 replica** (trạng thái dịch lưu in-memory, nhiều replica sẽ không
   đồng bộ với nhau).
7. Mở domain, đăng nhập, cài extension trỏ về domain này.

Bảo mật:
- Trên Railway, nếu thiếu `BASIC_AUTH_USER`/`BASIC_AUTH_PASS` thì app trả về 503 thay vì mở toang.
- Request POST từ domain khác bị chặn (chống CSRF).
- `/healthz` và `/admin/import` không qua Basic Auth; `/admin/import` tự xác thực bằng
  header `X-Import-Token` riêng (không đặt `IMPORT_TOKEN` thì endpoint từ chối phục vụ).
- Nên bật **Usage limit** trong phần billing của Railway, và đặt giới hạn chi tiêu ở Anthropic Console.
