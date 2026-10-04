(() => {
  const POLL_MS = 5000;
  const stepRequest = document.getElementById('step-request');
  const stepWaiting = document.getElementById('step-waiting');
  const stepApproved = document.getElementById('step-approved');
  const requestBtn = document.getElementById('request-btn');
  const noteEl = document.getElementById('note');
  const requestStatus = document.getElementById('request-status');
  const waitingLink = document.getElementById('waiting-link');
  const tokenValue = document.getElementById('token-value');

  const showStep = (el) => {
    [stepRequest, stepWaiting, stepApproved].forEach((s) => { s.hidden = s !== el; });
  };

  const poll = async (requestId) => {
    try {
      const res = await fetch(`/api/token-requests/${requestId}`);
      if (res.ok) {
        const data = await res.json();
        if (data.status === 'approved') {
          tokenValue.textContent = data.token;
          showStep(stepApproved);
          return;
        }
      }
    } catch {
      // thử lại ở vòng poll tiếp theo
    }
    setTimeout(() => poll(requestId), POLL_MS);
  };

  const startWaiting = (requestId) => {
    document.getElementById('extension-details').open = true;
    const url = new URL(location.href);
    url.searchParams.set('request_id', requestId);
    history.replaceState(null, '', url);
    waitingLink.textContent = url.href;
    showStep(stepWaiting);
    poll(requestId);
  };

  requestBtn.addEventListener('click', async () => {
    requestBtn.disabled = true;
    requestStatus.textContent = 'Đang gửi yêu cầu…';
    try {
      const res = await fetch('/api/token-requests', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note: noteEl.value.trim() }),
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      startWaiting(data.request_id);
    } catch (e) {
      requestStatus.textContent = `Lỗi: ${e.message}`;
      requestBtn.disabled = false;
    }
  });

  // Nếu URL đã có request_id (user quay lại từ link đã lưu), tiếp tục polling luôn.
  const existingId = new URL(location.href).searchParams.get('request_id');
  if (existingId) startWaiting(existingId);
})();
