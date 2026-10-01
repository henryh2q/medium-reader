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

// Chạy trong trang Medium đang mở để lấy nội dung bài viết đã render (bạn đang đọc
// bằng tài khoản member của mình) — không tự động truy cập Medium thay bạn.
function extractArticle() {
  const article = document.querySelector('article');
  if (!article) return null;
  const clone = article.cloneNode(true);
  clone.querySelectorAll('header, button').forEach((el) => el.remove());
  const title = document.title.replace(/\s*\|\s*by.*$/, '').trim();
  const authorLink = document.querySelector('a[rel="author"], a[data-testid="authorName"]');
  return {
    title,
    author: authorLink ? authorLink.textContent.trim() : '',
    html: clone.innerHTML,
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
  if (/(^|\.)medium\.com$/.test(appOrigin.hostname)) {
    setStatus('Ô "Địa chỉ app" phải là địa chỉ server "Đọc gì hôm nay" của bạn, không phải URL bài Medium.', 'err');
    return;
  }
  chrome.storage.local.set({ appUrl, token });

  // Nếu app chạy ở domain khác railway.app/localhost (đã khai báo sẵn trong manifest),
  // xin thêm quyền truy cập domain đó ngay bây giờ.
  const origin = `${appOrigin.origin}/*`;
  const hasPerm = await chrome.permissions.contains({ origins: [origin] });
  if (!hasPerm) {
    const granted = await chrome.permissions.request({ origins: [origin] });
    if (!granted) {
      setStatus('Cần cấp quyền truy cập địa chỉ app để gửi dữ liệu.', 'err');
      return;
    }
  }

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !/^https:\/\/([a-z0-9-]+\.)?medium\.com\//.test(tab.url || '')) {
    setStatus('Mở một bài viết trên medium.com trước.', 'err');
    return;
  }

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
      appUrl,
      token,
      payload: { url: tab.url, title: result.title, author: result.author, html: result.html },
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
