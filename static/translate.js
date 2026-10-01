(() => {
  const entries = document.querySelectorAll('.entry');

  const setBusy = (id, btn) => {
    const entry = document.querySelector(`.entry[data-id="${id}"]`);
    if (btn) btn.disabled = true;
    const meta = entry && entry.querySelector('.meta');
    if (meta && !meta.querySelector('.tag')) {
      const tag = document.createElement('span');
      tag.className = 'tag';
      tag.textContent = 'Đang dịch…';
      meta.appendChild(tag);
    }
  };

  // ---------- Dịch 1 bài ----------
  document.querySelectorAll('.translate-one').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const id = btn.dataset.id;
      setBusy(id, btn);
      try {
        const res = await fetch(`/admin/translate/${id}`, { method: 'POST' });
        if (!res.ok) throw new Error(await res.text());
      } catch (e) {
        alert(`Không bắt đầu dịch được: ${e.message}`);
        btn.disabled = false;
        return;
      }
      setTimeout(() => location.reload(), 1500);
    });
  });

  // ---------- Dịch hàng loạt ----------
  const batchBtn = document.getElementById('batch-btn');
  const modal = document.getElementById('batch-modal');
  if (!batchBtn || !modal) return;

  const list = document.getElementById('batch-list');
  const selectAll = document.getElementById('select-all');
  const submitBtn = document.getElementById('batch-submit');

  const pending = [...entries].filter((e) => e.querySelector('.pick:not(:disabled)'));

  const openModal = () => {
    list.innerHTML = '';
    pending.forEach((entry) => {
      const id = entry.dataset.id;
      const title = entry.querySelector('h2').textContent.trim();
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
    selectAll.checked = false;
    modal.hidden = false;
  };

  batchBtn.addEventListener('click', openModal);
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
    modal.hidden = true;
    setTimeout(() => location.reload(), 1500);
  });
})();
