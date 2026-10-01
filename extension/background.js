chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
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
        sendResponse({ ok: false, error: data.detail || `HTTP ${res.status}` });
        return;
      }
      sendResponse({ ok: true, data });
    } catch (e) {
      sendResponse({ ok: false, error: e.message });
    }
  })();
  return true; // giữ kênh mở cho phản hồi bất đồng bộ
});
