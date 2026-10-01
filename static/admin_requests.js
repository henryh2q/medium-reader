(() => {
  document.querySelectorAll('.approve-btn').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const id = btn.dataset.id;
      btn.disabled = true;
      try {
        const res = await fetch(`/admin/requests/${id}/approve`, { method: 'POST' });
        if (!res.ok) throw new Error(await res.text());
      } catch (e) {
        alert(`Lỗi: ${e.message}`);
        btn.disabled = false;
        return;
      }
      location.reload();
    });
  });
})();
