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
| `config.py` | Model dùng để dịch/giải thích, token/admin/email config |
| `fetcher.py` | HTML (từ extension) -> Markdown |
| `llm.py` | Tóm tắt + tag, dịch (theo đoạn, giữ nguyên code), giải thích thuật ngữ |
| `emailer.py` | Gửi email thông báo (yêu cầu token, feedback) qua Resend API |
| `app.py` | FastAPI: danh sách bài, trang đọc, import/dịch, `/submit` + `/admin/requests` (duyệt token), feedback, SEO (`/sitemap.xml`, `/robots.txt`) |
| `static/translate.js` | Icon dịch cạnh từng bài + polling `GET /api/status` để tự cập nhật, không cần reload |
| `static/submit.js` | Luồng yêu cầu token: tạo request, polling trạng thái, resume qua `?request_id=` |
| `static/admin_requests.js` | Nút "Duyệt" trên trang quản trị |
| `static/feedback.js` | Modal "Báo lỗi / Góp ý" |
| `static/fresh-on-resume.js` | Tự reload trang chủ khi app PWA quay lại foreground sau khi rời đi lâu |
| `static/reader.js` | Bôi đen -> nút "Giải thích thuật ngữ" -> panel; chuyển VI/EN |
| `static/logo.svg` | Logo gốc (SVG) — nguồn sinh favicon và icon extension |
| `extension/` | Extension Chrome/Edge: đưa bài bạn đang đọc vào app (mọi trang có `<article>`) |

## Đưa bài vào app (extension)

Mở bài bạn muốn đọc trên trình duyệt (đăng nhập tài khoản member nếu cần), bấm
extension để gửi **nội dung đã render trên trang** về app — không có bot nào tự động
truy cập trang nguồn thay bạn. Hoạt động với mọi trang có thẻ `<article>`, không
riêng Medium.

**Với chính bạn (chủ site):**
1. Đặt `IMPORT_TOKEN` (chuỗi ngẫu nhiên dài) trong `.env` hoặc biến môi trường Railway.
2. Chrome/Edge → `chrome://extensions` → bật **Developer mode** → **Load unpacked** →
   chọn thư mục `extension/`.
3. Mở bài viết, đọc đến hết trang (để nội dung render đầy đủ).
4. Bấm icon extension → dán `IMPORT_TOKEN` → **Đưa bài đang mở vào app**.

**Với người khác muốn gửi bài:** bấm nút **"+"** (góc dưới phải trang chủ) →
`/submit` → yêu cầu token → đợi admin duyệt tại `/admin/requests` (có Basic Auth
riêng, xem `ADMIN_USER`/`ADMIN_PASS` bên dưới) → trang tự cập nhật khi được duyệt
(polling `GET /api/token-requests/<id>` mỗi 5s, không cần tải lại) → hiện token +
hướng dẫn cài extension thủ công (chưa publish lên Chrome Web Store).

Bài hiện ngay trên trang chủ kèm tóm tắt tiếng Anh và 2-3 tag chủ đề (tự sinh lúc
import — ưu tiên tag thật lấy từ trang nếu extension tìm thấy, vd. tag Medium).

**Lưu ý:** Chrome trên di động (Android/iOS) không hỗ trợ cài extension bên thứ ba —
đây là giới hạn của Chrome mobile, không phải của extension này. Chỉ dùng được trên
Chrome/Edge desktop.

## Dịch bài

Bấm icon ⇄ cạnh tiêu đề bài trong danh sách để dịch từng bài.

(Tính năng "Dịch hàng loạt" tạm ẩn, nhường chỗ nút "Gửi bài viết" — code còn nguyên
trong `templates/index.html`/`static/translate.js`, comment giải thích cách bật lại.)

Trong lúc dịch, cả trang hiện một thanh tiến độ vô định ở trên cùng (không có % cụ thể
vì server không biết chính xác còn bao lâu), bài đang dịch bị làm mờ và không click được,
có spinner xoay cạnh tiêu đề. `static/translate.js` tự polling `GET /api/status` mỗi 3
giây để biết khi nào xong — **không cần tải lại trang**: tiêu đề, tóm tắt tự chuyển sang
tiếng Việt ngay khi dịch xong. Nếu dịch lỗi, trang báo ngay bằng popup và hiện lại icon
⇄ để thử dịch lại, không phải đợi tải lại trang mới biết.

Bài đã dịch hiện tiêu đề và tóm tắt bằng tiếng Việt, không còn icon dịch (trạng thái
"đã dịch" thể hiện qua chính tiêu đề tiếng Việt, không cần nhãn riêng). Mỗi bài đã dịch
có ghi nguồn (link bài gốc + tác giả) ở cuối trang đọc, cùng dòng nhắc đây là bản dịch
không chính thức — bản quyền nội dung thuộc về tác giả gốc.

## Tag chủ đề

Mỗi bài có 2-3 tag chủ đề: nếu extension tìm thấy tag thật trên trang (hiện chỉ áp
dụng với Medium — link `/tag/<slug>` đầu bài viết) thì dùng luôn; nếu không, server
để Claude tự sinh tag cùng lúc tóm tắt lúc import (không tốn thêm lần gọi riêng).
Bấm vào một tag (trên thanh lọc đầu trang, hoặc tag nhỏ dưới mỗi bài) để lọc danh
sách theo đúng chủ đề đó (`GET /?tag=<tên tag>`).

## Thêm vào màn hình chính (mobile)

- **iOS (Safari):** Share → "Add to Home Screen". Icon và tên app lấy từ thẻ
  `apple-touch-icon`/`apple-mobile-web-app-title` trong `templates/base.html`.
- **Android (Chrome):** menu ⋮ → "Add to Home screen", dùng `static/manifest.json`.
- Mở app PWA từ Home Screen thường giữ nguyên trang cũ trong bộ nhớ (không tải lại),
  nên bài mới thêm từ lúc đóng app sẽ không hiện cho tới khi tự reload. `static/
  fresh-on-resume.js` tự reload trang chủ khi app quay lại foreground sau khi đã rời
  đi hơn 30 giây — không cần tắt/mở lại app thủ công nữa.

## Báo cáo sự cố / đóng góp ý kiến

Nút "Báo lỗi / Góp ý" (góc dưới trái trang chủ) mở form gửi thẳng vào email admin
qua `POST /api/feedback` (dùng chung `emailer.py`/Resend với luồng yêu cầu token).

## SEO

- URL bài viết dạng `/bai-viet/<slug>` (slug sinh từ tiêu đề tiếng Anh lúc import,
  cố định — không đổi khi dịch xong — và tự thêm hậu tố `-2`, `-3`... nếu trùng).
  Route cũ `/a/{id}` đã bị gỡ.
- Mỗi trang có `<meta name="description">`, Open Graph/Twitter card, và
  `<link rel="canonical">`; trang bài viết dùng tóm tắt thật làm mô tả.
- `/sitemap.xml` liệt kê trang chủ + mọi bài đã dịch; `/robots.txt` trỏ tới sitemap
  và chặn index `/submit`, `/admin/*`.

## Giới hạn đã biết

- **Trang chủ và trang đọc hoàn toàn công khai, không có đăng nhập.** Ai biết URL
  cũng đọc được danh sách bài, đọc nội dung đã dịch, và bấm nút dịch (tốn token
  Claude của bạn). Chỉ `/admin/*` (duyệt token request) có Basic Auth riêng qua
  `ADMIN_USER`/`ADMIN_PASS`; `/admin/import` và `/admin/translate*` xác thực khác
  (token riêng / không xác thực vì là thao tác công khai).
- Dùng cho cá nhân. Không public bản dịch vì nội dung thuộc bản quyền tác giả.
- Bôi đen cắt ngang nhiều định dạng (vd. nửa chữ đậm) vẫn giải thích được, chỉ là không tô vệt dạ quang.
- Trạng thái "đang dịch" lưu trong bộ nhớ process — chạy nhiều worker/instance cùng lúc
  có thể dịch trùng một bài (xem `Dockerfile`, cố định 1 worker).
- Extension chưa publish lên Chrome Web Store (cần tài khoản Google Developer trả
  phí + submit review) — người khác cài bằng "Load unpacked" thủ công qua hướng dẫn
  ở `/submit`.
- Gửi email (yêu cầu token, feedback) cần tự đăng ký `RESEND_API_KEY` tại resend.com
  và đặt `ADMIN_EMAIL`; thiếu 1 trong 2 thì request vẫn tạo được nhưng không ai được
  báo — bạn cần tự vào `/admin/requests` kiểm tra định kỳ.

## Deploy lên Railway

1. Đẩy code lên GitHub (file `.env` và thư mục `data/` đã nằm trong `.gitignore`).
2. Railway → New Project → Deploy from GitHub repo. Railway tự nhận `Dockerfile` và `railway.json`.
3. Chuột phải vào service → **Attach volume**, mount path `/data`.
4. Tab **Variables**:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   IMPORT_TOKEN=<chuỗi ngẫu nhiên dài, cho extension của bạn>
   ADMIN_USER=<tên đăng nhập trang duyệt token>
   ADMIN_PASS=<mật khẩu dài, ngẫu nhiên>
   ADMIN_EMAIL=<email nhận thông báo yêu cầu token/feedback>
   RESEND_API_KEY=<API key từ resend.com>
   PUBLIC_URL=https://<domain-railway-cua-ban>
   DB_PATH=/data/reader.db
   ```
5. Settings → Networking → **Generate Domain** — điền domain đó vào `PUBLIC_URL` ở trên.
6. Settings → giữ **1 replica** (trạng thái dịch lưu in-memory, nhiều replica sẽ không
   đồng bộ với nhau).
7. Mở domain, cài extension trỏ về domain này.

Bảo mật:
- **Trang chủ/trang đọc không yêu cầu đăng nhập** — xem phần Giới hạn đã biết ở trên.
- `/admin/requests` (duyệt token) có Basic Auth riêng qua `ADMIN_USER`/`ADMIN_PASS`;
  thiếu 1 trong 2 thì route này tự chặn (503) thay vì mở toang.
- `/admin/import` tự xác thực bằng header `X-Import-Token` (token gốc `IMPORT_TOKEN`
  hoặc token đã được duyệt qua `/admin/requests`).
- Nên bật **Usage limit** trong phần billing của Railway, và đặt giới hạn chi tiêu ở Anthropic Console.
