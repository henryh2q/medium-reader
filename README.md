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
| `search.py` | Tìm kiếm trang chủ: chuẩn hoá bỏ dấu, lọc AND, tô vàng, đoạn trích |
| `categories.py` | Gộp tag chi tiết về 2 category chính hiển thị trên trang chủ (AI, System Design) |
| `fetcher.py` | HTML (từ extension) -> Markdown |
| `llm.py` | Tóm tắt + tag, dịch (theo đoạn, giữ nguyên code), giải thích thuật ngữ |
| `emailer.py` | Gửi email thông báo (yêu cầu token, feedback) qua Resend API |
| `app.py` | FastAPI: danh sách bài, trang đọc, import/dịch, `/submit` + hàng đợi link `/admin/queue` + `/admin/requests` (duyệt token), feedback, SEO (`/sitemap.xml`, `/robots.txt`) |
| `static/article_translate.js` | Nút "Dịch sang tiếng Việt" ở trang đọc bài chưa dịch: trạng thái đang dịch, polling, popup tải lại |
| `static/translate.js` | Icon dịch cạnh từng bài + polling `GET /api/status` để tự cập nhật, không cần reload |
| `static/submit.js` | Luồng yêu cầu token: tạo request, polling trạng thái, resume qua `?request_id=` |
| `static/submit_url.js` | Ô "Gửi link bài viết" ở `/submit` (hàng đợi URL), điền sẵn từ `?url=` |
| `static/admin_queue.js` | Nút "Từ chối" trên trang hàng đợi `/admin/queue` |
| `static/admin_requests.js` | Nút "Duyệt" trên trang quản trị |
| `static/feedback.js` | Modal "Báo lỗi / Góp ý" |
| `static/fresh-on-resume.js` | Tự reload trang chủ khi app PWA quay lại foreground sau khi rời đi lâu |
| `static/reader.js` | Bôi đen -> nút "Giải thích thuật ngữ" -> panel; chuyển VI/EN |
| `static/logo.svg` | Logo gốc (SVG) — nguồn sinh favicon và icon extension |
| `static/icons/google-translate*.png` | Icon nút "Dịch" — tải từ [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Google_Translate_Icon.png), là logo/nhãn hiệu của Google, dùng ở đây không có liên kết hay được Google tài trợ |
| `extension/` | Extension Chrome/Edge: đưa bài bạn đang đọc vào app (`<article>`, rơi về `<main>` nếu trang không có) |

## Đưa bài vào app (extension)

Mở bài bạn muốn đọc trên trình duyệt (đăng nhập tài khoản member nếu cần), bấm
extension để gửi **nội dung đã render trên trang** về app — không có bot nào tự động
truy cập trang nguồn thay bạn. Ưu tiên thẻ `<article>` cụ thể nhất nếu trang có; nếu
không (vd. blog dựng bằng Next.js/Webflow chỉ có `<main>`), tự rơi về `<main>` hoặc
`[role="main"]` — không riêng Medium hay trang có cấu trúc chuẩn.

**Với chính bạn (chủ site):**
1. Đặt `IMPORT_TOKEN` (chuỗi ngẫu nhiên dài) trong `.env` hoặc biến môi trường Railway.
2. Chrome/Edge → `chrome://extensions` → bật **Developer mode** → **Load unpacked** →
   chọn thư mục `extension/`.
3. Mở bài viết, đọc đến hết trang (để nội dung render đầy đủ).
4. Bấm icon extension → dán `IMPORT_TOKEN` → **Đưa bài đang mở vào app**.

**Với người khác muốn gửi bài (kể cả trên mobile):** bấm nút **"+"** (góc dưới phải
trang chủ) → `/submit` → dán link bài → **Gửi link**. Link vào **hàng đợi** (xem mục
dưới), không cần cài gì. Ai muốn tự đưa bài vào ngay bằng extension thì mở mục "extension"
trên cùng trang → yêu cầu token → đợi admin duyệt tại `/admin/requests` (có Basic Auth
riêng, xem `ADMIN_USER`/`ADMIN_PASS` bên dưới) → trang tự cập nhật khi được duyệt
(polling `GET /api/token-requests/<id>` mỗi 5s) → hiện token + hướng dẫn cài extension
thủ công (chưa publish lên Chrome Web Store).

### Hàng đợi link (gửi từ mobile, xử lý ở PC)

Trình duyệt mobile không cài được extension, nên người dùng chỉ gửi **URL**
(`POST /api/submissions`); server **không tự tải trang đó** (sẽ bị Cloudflare chặn, và
không có phiên đăng nhập member của bạn). Admin xử lý ở PC tại **`/admin/queue`** (Basic
Auth): bấm **Mở bài** → dùng extension đưa bài vào như thường → mục tự chuyển sang
"Đã đưa vào" khi `/admin/import` nhận URL khớp (so khớp sau khi bỏ query, `#`, dấu `/`
cuối). Hoặc bấm **Từ chối**.

- Ô gửi link công khai nên có giới hạn: 5 link/giờ mỗi IP, tối đa 500 link đang chờ,
  chỉ nhận `http(s)://`, tự bỏ link trùng và link của bài đã có. Gửi kèm header
  `X-Import-Token` (token chủ site) thì không bị giới hạn tần suất.
- Có `RESEND_API_KEY` + `ADMIN_EMAIL` thì mỗi link mới báo qua email; không có thì tự vào
  `/admin/queue` xem.
- `/submit?url=<link>` điền sẵn ô link — dùng được cho bookmarklet hoặc iOS Shortcut
  (chưa có sẵn Shortcut nào, tự tạo nếu cần).
- Link do người lạ gửi có thể độc hại: trang admin hiện rõ tên miền, link mở với
  `rel="noopener noreferrer"`, nhưng vẫn nên xem kỹ trước khi mở.

Bài hiện ngay trên trang chủ kèm tóm tắt tiếng Anh và 2-3 tag chủ đề (tự sinh lúc
import — ưu tiên tag thật lấy từ trang nếu extension tìm thấy, vd. tag Medium).

**Lưu ý:** Chrome trên di động (Android/iOS) không hỗ trợ cài extension bên thứ ba —
đây là giới hạn của Chrome mobile, không phải của extension này. Chỉ dùng được trên
Chrome/Edge desktop.

## Dịch bài

Bấm icon ⇄ cạnh tiêu đề bài trong danh sách để dịch từng bài, hoặc dịch ngay trong trang đọc
(xem dưới).

**Bài chưa dịch:** bấm tiêu đề ở trang chủ sẽ mở **trang đọc nội bộ** (`/bai-viet/<slug>`),
không nhảy sang Medium — vì bài member-only thường người đọc không xem được ở nguồn. Trang
này chỉ có bản tiếng Anh (không có tab VN/EN), kèm **icon dịch** (giống ở trang chủ) ngay sau
tiêu đề. Bấm icon: hiện trạng thái "Đang dịch…" + thanh tiến độ vô định, bạn vẫn đọc bản
tiếng Anh được; xong thì hiện popup **Đã dịch xong** với nút **Tải lại trang** (hoặc đóng popup,
còn lại nút "Đã dịch xong — tải lại trang" dưới dòng thông tin). Tải lại là thấy bản dịch với đủ
tab Tiếng Việt/English.
`static/article_translate.js` polling `GET /api/status` mỗi 3 giây. Nếu dịch lỗi (hoặc server
khởi động lại giữa chừng làm mất tiến trình) thì hiện thông báo lỗi và icon dịch quay lại (tooltip "Thử dịch lại"). Mở
trang đúng lúc bài đang được dịch thì trạng thái "Đang dịch" hiện ngay.
Trang bài chưa dịch có `noindex` và không nằm trong sitemap; lưu ý trang này công khai, ai
có link cũng đọc được bản gốc tiếng Anh.

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

## Tìm kiếm

Ô tìm kiếm ở đầu trang chủ lọc bài theo từ khoá (`GET /?q=<từ khoá>`), xử lý phía server
trong [search.py](search.py):

- Khớp trong tiêu đề (cả tiếng Việt lẫn tiếng Anh), tóm tắt, tác giả, tag và **toàn bộ nội
  dung bài** (cả hai bản dịch).
- **Không phân biệt hoa/thường và dấu tiếng Việt**: gõ `thiet ke` vẫn ra "thiết kế".
- Nhiều từ khoá = **AND** (bài phải chứa đủ mọi từ, ở bất kỳ trường nào), tối đa 6 từ,
  câu tìm tối đa 100 ký tự.
- Chỗ khớp được tô vàng (`<mark class="hit">`) ở tiêu đề, tóm tắt, tác giả và tag. Nếu từ
  khoá chỉ khớp ở nơi không đang hiển thị (nội dung bài, bản tiếng Anh) thì hiện thêm một
  đoạn trích ngắn có tô vàng. Mọi văn bản được escape trước khi tô nên không chèn được HTML.
- Kết hợp được với bộ lọc category (pill giữ nguyên từ khoá). Trang kết quả tìm kiếm có
  `noindex` để công cụ tìm kiếm không lập chỉ mục các URL `?q=`.
- **Xếp hạng:** mỗi từ khoá được tính điểm theo chỗ khớp tốt nhất của nó — tiêu đề 10, tag 8,
  tóm tắt/tác giả 4, chỉ trong nội dung 1 — rồi cộng lại; điểm cao lên trước, cùng điểm thì bài
  mới hơn trước. Nhờ vậy bài có từ khoá ở tiêu đề/tag luôn nằm trên bài chỉ nhắc thoáng trong
  nội dung. Không có từ khoá thì danh sách vẫn theo ngày. Chỉ duyệt trong 200 bài mới nhất
  như danh sách chính.

## Chia sẻ bài viết

Trang đọc có hai nút dưới tiêu đề: **Chia sẻ** (dùng Web Share API, mở khung chia sẻ của
hệ điều hành — chỉ hiện trên thiết bị/trình duyệt hỗ trợ, như iOS Safari, Android
Chrome) và **Sao chép link** (luôn có; rơi về `execCommand` khi mở qua http thường vì
clipboard API cần https). Link chia sẻ lấy từ `<link rel="canonical">` nên luôn là
`https://<domain công khai>/bai-viet/<slug>`; tiêu đề đi kèm theo tab ngôn ngữ đang chọn.
Nếu chia sẻ lỗi (không phải do người dùng tự đóng) thì tự sao chép link thay thế.

## Tóm tắt ý chính

Trang đọc có nút icon cố định ở mép phải (đi theo khi cuộn). Bấm vào để Claude tóm
tắt các ý chính của cả bài (`POST /api/articles/<id>/summary`, dùng `MODEL_SUMMARIZE`).
Mỗi bài chỉ gọi Claude **một lần** — kết quả lưu vào bảng `article_summaries`, các lần
bấm sau (kể cả từ người khác) trả thẳng từ DB, không tốn token. Lỗi không được cache.

## Tag chủ đề & category

Mỗi bài có 2-3 tag chủ đề: nếu extension tìm thấy tag thật trên trang (hiện chỉ áp
dụng với Medium — link `/tag/<slug>` đầu bài viết) thì dùng luôn; nếu không, server
để Claude tự sinh tag cùng lúc tóm tắt lúc import (không tốn thêm lần gọi riêng).
Tag nhỏ vẫn hiện dưới mỗi bài — bấm vào để lọc đúng tag đó (`GET /?tag=<tên tag>`).

Thanh lọc chính ở đầu trang chỉ hiện 2 category lớn — **AI** và **System Design**
(`categories.py`) — để không chiếm hết diện tích màn hình trên mobile khi có nhiều
tag. Mỗi category gộp từ các tag khớp từ khoá (vd. tag "AI Agents", "Data Science"
đều thuộc category AI); một bài có thể thuộc cả 2 category nếu tag của nó khớp cả
hai. Bấm category để lọc (`GET /?category=AI` hoặc `?category=System Design`).

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
- Giải thích thuật ngữ kèm cách phát âm (IPA + cách đọc phỏng theo tiếng Việt) khi
  thuật ngữ là từ/cụm từ tiếng Anh có cách đọc không hiển nhiên; bỏ qua với viết tắt
  đọc từng chữ cái (API, SQL...).
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
