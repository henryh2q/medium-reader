(() => {
  const fab = document.getElementById('feedback-fab');
  const modal = document.getElementById('feedback-modal');
  if (!fab || !modal) return;

  const kindEl = document.getElementById('feedback-kind');
  const messageEl = document.getElementById('feedback-message');
  const contactEl = document.getElementById('feedback-contact');
  const statusEl = document.getElementById('feedback-status');
  const submitBtn = document.getElementById('feedback-submit');

  fab.addEventListener('click', () => { modal.hidden = false; });
  document.getElementById('feedback-close').addEventListener('click', () => { modal.hidden = true; });
  modal.addEventListener('click', (e) => { if (e.target === modal) modal.hidden = true; });

  submitBtn.addEventListener('click', async () => {
    const message = messageEl.value.trim();
    if (!message) {
      statusEl.textContent = 'Nhập nội dung trước đã.';
      return;
    }
    submitBtn.disabled = true;
    statusEl.textContent = 'Đang gửi…';
    try {
      const res = await fetch('/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          kind: kindEl.value,
          message,
          contact: contactEl.value.trim(),
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      statusEl.textContent = 'Đã gửi, cảm ơn bạn!';
      messageEl.value = '';
      contactEl.value = '';
      setTimeout(() => { modal.hidden = true; statusEl.textContent = ''; }, 1500);
    } catch (e) {
      statusEl.textContent = `Lỗi: ${e.message}`;
    } finally {
      submitBtn.disabled = false;
    }
  });
})();
