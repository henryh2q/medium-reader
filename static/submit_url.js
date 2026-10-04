(() => {
  const urlEl = document.getElementById('submit-url');
  const noteEl = document.getElementById('submit-note');
  const btn = document.getElementById('submit-url-btn');
  const statusEl = document.getElementById('submit-url-status');

  // /submit?url=<link> điền sẵn ô link (dùng được từ iOS Shortcut / bookmarklet).
  const prefill = new URL(location.href).searchParams.get('url');
  if (prefill) urlEl.value = prefill;

  const send = async () => {
    const url = urlEl.value.trim();
    if (!url) {
      statusEl.textContent = 'Dán link bài viết trước đã.';
      return;
    }
    btn.disabled = true;
    statusEl.textContent = 'Đang gửi…';
    try {
      const res = await fetch('/api/submissions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, note: noteEl.value.trim() }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(typeof data.detail === 'string' ? data.detail : 'Dữ liệu không hợp lệ.');
      }
      statusEl.textContent = data.message;
      if (data.state === 'queued') {
        urlEl.value = '';
        noteEl.value = '';
      }
    } catch (e) {
      statusEl.textContent = `Lỗi: ${e.message}`;
    } finally {
      btn.disabled = false;
    }
  };

  btn.addEventListener('click', send);
  urlEl.addEventListener('keydown', (e) => { if (e.key === 'Enter') send(); });
})();
