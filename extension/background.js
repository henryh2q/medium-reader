chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === 'ping') {
    sendResponse({ pong: true });
    return;
  }
  if (msg.type !== 'import') return;
  (async () => {
    try {
      const res = await fetch(`${msg.appUrl}/admin/import`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Import-Token': msg.token,
        },
        body: JSON.stringify(msg.payload),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        // FastAPI trả `detail` là chuỗi (lỗi nghiệp vụ) hoặc mảng object (lỗi
        // validation 422) — chuyển về chuỗi đọc được thay vì "[object Object]".
        const detail = Array.isArray(data.detail)
          ? data.detail.map((d) => `${(d.loc || []).slice(1).join('.')}: ${d.msg}`).join('; ')
          : data.detail;
        sendResponse({ ok: false, error: detail || `HTTP ${res.status}` });
        return;
      }
      sendResponse({ ok: true, data });
    } catch (e) {
      sendResponse({ ok: false, error: e.message });
    }
  })();
  return true; // giữ kênh mở cho phản hồi bất đồng bộ
});
