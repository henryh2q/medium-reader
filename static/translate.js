(() => {
  const entries = [...document.querySelectorAll('.entry')];
  const POLL_MS = 3000;
  let pollTimer = null;

  const escapeHtml = (s) => s.replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));

  // Icon kiểu Google Translate (chữ 文 + A), khớp với templates/_translate_icon.html —
  // sửa cả 2 nơi nếu đổi icon, vì JS không include được partial Jinja khi render động.
  const TRANSLATE_ICON_SVG = `<svg class="translate-icon" viewBox="0 0 24 24" width="16" height="16" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <path d="M5 4h5M7.5 4v2.2c0 2.6-1.6 5-4 6.1M4 9.5c1.6 1.4 3.6 2.3 5.8 2.6M11 4.3c-.6 3.7-3 6.8-6.3 8.5"
          stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M14.5 21l4-9 4 9M15.8 18h5.4"
          stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>`;

  // ---------- Theo dõi tiến độ các bài đang dịch ----------
  const progressBar = document.getElementById('progress-bar');
  const trackingIds = new Set(
    entries.filter((e) => e.dataset.status === 'translating').map((e) => Number(e.dataset.id)),
  );
  const syncProgressBar = () => { progressBar.hidden = trackingIds.size === 0; };
  syncProgressBar();

  // Xoá mọi dấu hiệu trạng thái tạm (spinner, tag, icon dịch) trước khi áp trạng thái
  // mới, để không bao giờ hiện lẫn hai trạng thái cùng lúc (vd. "Đang dịch…" + "Dịch lỗi").
  const clearTransientUI = (entry) => {
    entry.querySelector('.spinner')?.remove();
    entry.querySelector('.translate-one')?.remove();
    entry.querySelectorAll('.meta .tag').forEach((el) => el.remove());
  };

  const applyResult = (entry, info) => {
    clearTransientUI(entry);
    entry.dataset.status = info.status;
    if (info.status === 'translated') {
      entry.querySelector('h2').innerHTML =
        `<a href="/bai-viet/${info.slug}">${escapeHtml(info.title_vi || entry.dataset.title)}</a>`;
      const descEl = entry.querySelector('.desc');
      if (info.summary_vi) {
        if (descEl) descEl.textContent = info.summary_vi;
        else entry.querySelector('h2').insertAdjacentHTML('afterend', `<p class="desc">${escapeHtml(info.summary_vi)}</p>`);
      }
    } else if (info.status === 'failed') {
      const h2 = entry.querySelector('h2');
      h2.insertAdjacentHTML('beforeend',
        `<button type="button" class="translate-one" data-id="${info.id}" title="Dịch bài này" aria-label="Dịch bài này">${TRANSLATE_ICON_SVG}</button>`);
      bindTranslateButton(h2.querySelector('.translate-one'));
      entry.querySelector('.meta').insertAdjacentHTML('beforeend', '<span class="tag tag-err">Dịch lỗi</span>');
      alert(`Dịch lỗi: "${entry.dataset.title}". Bấm icon dịch để thử lại.`);
    }
  };

  const poll = async () => {
    if (!trackingIds.size) {
      pollTimer = null;
      return;
    }
    try {
      const res = await fetch(`/api/status?ids=${[...trackingIds].join(',')}`);
      if (res.ok) {
        const { articles } = await res.json();
        for (const info of articles) {
          if (info.status === 'translating') continue;
          const entry = document.querySelector(`.entry[data-id="${info.id}"]`);
          trackingIds.delete(info.id);
          if (entry) applyResult(entry, info);
        }
        syncProgressBar();
      }
    } catch {
      // bỏ qua, thử lại ở vòng poll tiếp theo
    }
    pollTimer = trackingIds.size ? setTimeout(poll, POLL_MS) : null;
  };

  const startTracking = (id) => {
    trackingIds.add(id);
    syncProgressBar();
    if (!pollTimer) pollTimer = setTimeout(poll, POLL_MS);
  };

  const markTranslating = (id) => {
    const entry = document.querySelector(`.entry[data-id="${id}"]`);
    if (!entry) return;
    clearTransientUI(entry);
    entry.dataset.status = 'translating';
    entry.querySelector('h2').insertAdjacentHTML('beforeend',
      '<span class="spinner" title="Đang dịch…" aria-label="Đang dịch…"></span>');
    entry.querySelector('.meta').insertAdjacentHTML('beforeend', '<span class="tag">Đang dịch…</span>');
  };

  // ---------- Dịch 1 bài ----------
  const bindTranslateButton = (btn) => {
    btn.addEventListener('click', async (e) => {
      e.preventDefault();
      const id = Number(btn.dataset.id);
      btn.disabled = true;
      try {
        const res = await fetch(`/admin/translate/${id}`, { method: 'POST' });
        if (!res.ok) throw new Error(await res.text());
      } catch (err) {
        alert(`Không bắt đầu dịch được: ${err.message}`);
        btn.disabled = false;
        return;
      }
      markTranslating(id);
      startTracking(id);
    });
  };
  document.querySelectorAll('.translate-one').forEach(bindTranslateButton);

  if (trackingIds.size) poll();

  // ---------- Dịch hàng loạt ----------
  const fab = document.getElementById('batch-fab');
  const modal = document.getElementById('batch-modal');
  if (!fab || !modal) return;

  const list = document.getElementById('batch-list');
  const selectAll = document.getElementById('select-all');
  const submitBtn = document.getElementById('batch-submit');

  const openModal = () => {
    const pending = entries.filter((e) => e.dataset.status === 'new' || e.dataset.status === 'failed');
    list.innerHTML = '';
    if (!pending.length) {
      const li = document.createElement('li');
      li.textContent = 'Không có bài nào đang chờ dịch.';
      list.append(li);
      submitBtn.hidden = true;
      selectAll.closest('.modal-all').hidden = true;
    } else {
      submitBtn.hidden = false;
      selectAll.closest('.modal-all').hidden = false;
      pending.forEach((entry) => {
        const id = entry.dataset.id;
        const title = entry.dataset.title;
        const li = document.createElement('li');
        const label = document.createElement('label');
        const cb = document.createElement('input');
        cb.type = 'checkbox';
        cb.value = id;
        cb.className = 'batch-pick';
        label.append(cb, ` ${title}`);
        li.append(label);
        list.append(li);
      });
    }
    selectAll.checked = false;
    modal.hidden = false;
  };

  fab.addEventListener('click', openModal);
  document.getElementById('batch-close').addEventListener('click', () => { modal.hidden = true; });
  modal.addEventListener('click', (e) => { if (e.target === modal) modal.hidden = true; });

  selectAll.addEventListener('change', () => {
    list.querySelectorAll('.batch-pick').forEach((cb) => { cb.checked = selectAll.checked; });
  });

  submitBtn.addEventListener('click', async () => {
    const ids = [...list.querySelectorAll('.batch-pick:checked')].map((cb) => Number(cb.value));
    if (!ids.length) {
      alert('Chọn ít nhất một bài.');
      return;
    }
    submitBtn.disabled = true;
    try {
      const res = await fetch('/admin/translate-batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ article_ids: ids }),
      });
      if (!res.ok) throw new Error(await res.text());
    } catch (e) {
      alert(`Lỗi: ${e.message}`);
      submitBtn.disabled = false;
      return;
    }
    ids.forEach((id) => { markTranslating(id); startTracking(id); });
    modal.hidden = true;
    submitBtn.disabled = false;
  });
})();
