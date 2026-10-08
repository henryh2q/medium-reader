(() => {
  const bar = document.getElementById('translate-bar');
  if (!bar) return;

  const POLL_MS = 3000;
  const id = Number(bar.dataset.id);
  const btn = document.getElementById('translate-btn');
  const reloadBtn = document.getElementById('translate-reload');
  const statusEl = document.getElementById('translate-status');
  const errorEl = document.getElementById('translate-error');
  const progress = document.getElementById('progress-bar');
  const modal = document.getElementById('translated-modal');

  const setBusy = (busy) => {
    btn.hidden = busy;
    statusEl.hidden = !busy;
    progress.hidden = !busy;
    if (busy) errorEl.hidden = true;
  };

  const setBtnLabel = (text) => {
    btn.title = text;
    btn.setAttribute('aria-label', text);
  };

  const showFailed = (message) => {
    setBusy(false);
    btn.disabled = false;
    setBtnLabel('Thử dịch lại');
    errorEl.textContent = message;
    errorEl.hidden = false;
  };

  const showDone = () => {
    setBusy(false);
    btn.hidden = true;            // đã dịch xong, không cần icon dịch nữa
    reloadBtn.hidden = false;     // còn lại lối tắt tải lại trang nếu người dùng đóng popup
    modal.hidden = false;
  };

  const poll = async () => {
    try {
      const res = await fetch(`/api/status?ids=${id}`);
      if (res.ok) {
        const info = (await res.json()).articles[0];
        if (info && info.status === 'translated') return showDone();
        // Không còn "translating" mà cũng chưa "translated": dịch lỗi, hoặc server khởi
        // động lại giữa chừng làm mất tiến trình dịch.
        if (info && info.status !== 'translating') {
          return showFailed('Dịch chưa hoàn tất (có thể do lỗi hoặc server vừa khởi động lại). Bấm thử lại.');
        }
      }
    } catch {
      // mạng chập chờn: thử lại ở vòng sau
    }
    setTimeout(poll, POLL_MS);
  };

  btn.addEventListener('click', async () => {
    btn.disabled = true;
    try {
      const res = await fetch(`/admin/translate/${id}`, { method: 'POST' });
      if (!res.ok) throw new Error(await res.text());
    } catch (e) {
      showFailed(`Không bắt đầu dịch được: ${e.message}`);
      return;
    }
    setBusy(true);
    // Chờ một nhịp rồi mới hỏi: server cần chút thời gian đánh dấu bài đang dịch.
    setTimeout(poll, POLL_MS);
  });

  reloadBtn.addEventListener('click', () => location.reload());
  document.getElementById('translated-reload').addEventListener('click', () => location.reload());
  document.getElementById('translated-later').addEventListener('click', () => { modal.hidden = true; });
  modal.addEventListener('click', (e) => { if (e.target === modal) modal.hidden = true; });

  // Mở trang khi bài đang được dịch (vd. bấm dịch ở trang chủ rồi vào xem): hiện trạng thái luôn.
  if (bar.dataset.translating === 'true') {
    setBusy(true);
    poll();
  }
})();
