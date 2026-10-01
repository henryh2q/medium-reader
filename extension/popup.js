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
function extractArticle() {
  const article = document.querySelector('article');
  if (!article) return null;
  const clone = article.cloneNode(true);
  clone.querySelectorAll('header, button').forEach((el) => el.remove());
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
  chrome.runtime.sendMessage(
    {
      type: 'import',
      appUrl: appOrigin.origin,
      token,
      payload: { url: tab.url, title: result.title, author: result.author, html: result.html, tags: result.tags },
    },
    (resp) => {
      if (chrome.runtime.lastError) {
        setStatus(`Lỗi: ${chrome.runtime.lastError.message}`, 'err');
      } else if (resp && resp.ok) {
        setStatus(resp.data.ok ? `Đã thêm (${resp.data.words} từ).` : resp.data.reason, resp.data.ok ? 'ok' : 'err');
      } else {
        setStatus(`Lỗi: ${resp ? resp.error : 'không rõ'}`, 'err');
      }
    },
  );
});
