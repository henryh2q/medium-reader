(() => {
  const entries = [...document.querySelectorAll('.entry')];

  // ---------- Dịch 1 bài ----------
  document.querySelectorAll('.translate-one').forEach((btn) => {
    btn.addEventListener('click', async (e) => {
      e.preventDefault();
      const id = btn.dataset.id;
      btn.disabled = true;
      try {
        const res = await fetch(`/admin/translate/${id}`, { method: 'POST' });
        if (!res.ok) throw new Error(await res.text());
      } catch (err) {
        alert(`Không bắt đầu dịch được: ${err.message}`);
        btn.disabled = false;
        return;
      }
      setTimeout(() => location.reload(), 1500);
    });
  });

  // ---------- Dịch hàng loạt ----------
  const fab = document.getElementById('batch-fab');
  const modal = document.getElementById('batch-modal');
  if (!fab || !modal) return;

  const list = document.getElementById('batch-list');
  const selectAll = document.getElementById('select-all');
  const submitBtn = document.getElementById('batch-submit');

  const pending = entries.filter((e) => e.dataset.status === 'new' || e.dataset.status === 'failed');

  const openModal = () => {
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
    modal.hidden = true;
    setTimeout(() => location.reload(), 1500);
  });
})();
