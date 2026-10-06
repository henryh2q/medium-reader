const appUrlEl = document.getElementById('appUrl');
const tokenEl = document.getElementById('token');
const statusEl = document.getElementById('status');
const sendBtn = document.getElementById('send');

chrome.storage.local.get(['appUrl', 'token'], (saved) => {
  if (saved.appUrl) appUrlEl.value = saved.appUrl;
  if (saved.token) tokenEl.value = saved.token;
});

const setStatus = (text, cls) => {
  statusEl.textContent = text;
  statusEl.className = cls || '';
};

// Chạy trong trang đang mở để lấy nội dung bài viết đã render (bạn đang tự đọc,
// kể cả nội dung cần đăng nhập) — không tự động truy cập trang nào thay bạn.
// Hàm này được inject nguyên văn vào trang qua chrome.scripting.executeScript
// (func.toString()), nên không được gọi hàm nào định nghĩa bên ngoài nó — mọi
// logic phụ trợ (vd. tìm vùng nội dung chính) phải viết lồng bên trong.
function extractArticle() {
  // Không phải mọi trang đều dùng thẻ <article> (vd. blog dựng bằng Next.js/
  // Webflow chỉ có <main>) — ưu tiên <article> cụ thể nhất nếu có; chỉ rơi về
  // <main>/[role=main] (kém chính xác hơn, có thể dính cả nav/sidebar) khi
  // trang không có <article> nào.
  const articleCandidates = [...document.querySelectorAll('article')]
    .filter((el) => el.textContent.trim().length > 200)
    .sort((a, b) => b.textContent.length - a.textContent.length);
  const fallbackCandidates = [document.querySelector('main'), document.querySelector('[role="main"]')]
    .filter(Boolean)
    .filter((el) => el.textContent.trim().length > 200)
    .sort((a, b) => b.textContent.length - a.textContent.length);
  const article = articleCandidates[0] || fallbackCandidates[0] || null;
  if (!article) return null;
  const clone = article.cloneNode(true);
  clone.querySelectorAll('header, nav, footer, button, script, style, noscript, svg, picture source').forEach((el) => el.remove());
  // HTML của Medium/blog hiện đại phình rất to vì class, style, data-*... — server
  // chỉ cần cấu trúc thẻ + href/src/alt, nên bỏ hết thuộc tính khác để bài dài
  // không vượt giới hạn dung lượng.
  const keepAttrs = ['href', 'src', 'alt', 'title'];
  clone.querySelectorAll('*').forEach((el) => {
    [...el.attributes].forEach((attr) => {
      if (!keepAttrs.includes(attr.name)) el.removeAttribute(attr.name);
    });
  });
  const title = document.title.replace(/\s*\|\s*by.*$/, '').trim();
  const authorLink = document.querySelector('a[rel="author"], a[data-testid="authorName"]');
  // Medium hiện tag bài viết dạng link trỏ tới /tag/<slug> ngay trên đầu bài; site
  // khác thường không có cấu trúc này nên mảng rỗng là bình thường (server sẽ tự
  // sinh tag bằng LLM khi không có tag thật từ trang).
  const tagLinks = [...document.querySelectorAll('a[href*="/tag/"]')]
    .map((a) => a.textContent.trim())
    .filter(Boolean);
  const tags = [...new Set(tagLinks)].slice(0, 3);
  return {
    title,
    author: authorLink ? authorLink.textContent.trim() : '',
    html: clone.innerHTML,
    tags,
  };
}

sendBtn.addEventListener('click', async () => {
  const appUrl = appUrlEl.value.trim().replace(/\/$/, '');
  const token = tokenEl.value.trim();
  if (!appUrl || !token) {
    setStatus('Điền địa chỉ app và import token trước.', 'err');
    return;
  }
  let appOrigin;
  try {
    appOrigin = new URL(appUrl);
  } catch {
    setStatus('Địa chỉ app không hợp lệ.', 'err');
    return;
  }

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !/^https?:\/\//.test(tab.url || '')) {
    setStatus('Mở một bài viết trên trình duyệt trước.', 'err');
    return;
  }
  if (new URL(tab.url).origin === appOrigin.origin) {
    setStatus('Ô "Địa chỉ app" phải là địa chỉ server "Đọc gì hôm nay" của bạn, không phải trang bạn đang đọc.', 'err');
    return;
  }

  // Chỉ giữ scheme+host+port — bỏ mọi path/query người dùng lỡ dán kèm, để
  // request luôn gọi đúng {origin}/admin/import thay vì cộng dồn path thừa.
  chrome.storage.local.set({ appUrl: appOrigin.origin, token });

  setStatus('Đang đọc nội dung bài…');
  let result;
  try {
    [{ result } = {}] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: extractArticle,
    });
  } catch (e) {
    setStatus(`Không đọc được trang: ${e.message}`, 'err');
    return;
  }
  if (!result) {
    setStatus('Không tìm thấy nội dung bài viết trên trang này.', 'err');
    return;
  }

  setStatus('Đang gửi về app…');
  const payload = { url: tab.url, title: result.title, author: result.author, html: result.html, tags: result.tags };
  const showResult = (resp) => {
    if (resp && resp.ok) {
      setStatus(resp.data.ok ? `Đã thêm (${resp.data.words} từ).` : resp.data.reason, resp.data.ok ? 'ok' : 'err');
    } else {
      setStatus(`Lỗi: ${resp ? resp.error : 'không rõ'}`, 'err');
    }
  };
  // Ưu tiên gửi qua service worker (không bị huỷ nếu popup đóng giữa chừng). Service worker
  // có thể hỏng sau khi sửa file extension mà chưa Reload ở chrome://extensions — lúc đó
  // hoặc báo "Receiving end does not exist", hoặc treo im lặng — nên "gõ cửa" trước, không
  // thấy trả lời thì tự gửi thẳng từ popup (giữ popup mở tới khi xong).
  if (!(await swAlive())) {
    setStatus('Đang gửi trực tiếp…');
    showResult(await importDirect(appOrigin.origin, token, payload));
    return;
  }
  chrome.runtime.sendMessage(
    { type: 'import', appUrl: appOrigin.origin, token, payload },
    async (resp) => {
      if (!chrome.runtime.lastError) return showResult(resp);
      setStatus('Đang gửi trực tiếp…');
      showResult(await importDirect(appOrigin.origin, token, payload));
    },
  );
});

function swAlive() {
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(false), 1500);
    chrome.runtime.sendMessage({ type: 'ping' }, (resp) => {
      clearTimeout(timer);
      resolve(!chrome.runtime.lastError && !!resp && resp.pong === true);
    });
  });
}

async function importDirect(appUrl, token, payload) {
  try {
    const res = await fetch(`${appUrl}/admin/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Import-Token': token },
      body: JSON.stringify(payload),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = Array.isArray(data.detail)
        ? data.detail.map((d) => `${(d.loc || []).slice(1).join('.')}: ${d.msg}`).join('; ')
        : data.detail;
      return { ok: false, error: detail || `HTTP ${res.status}` };
    }
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: e.message };
  }
}
