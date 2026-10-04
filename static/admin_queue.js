(() => {
  document.querySelectorAll('.reject-btn').forEach((btn) => {
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      try {
        const res = await fetch(`/admin/queue/${btn.dataset.id}/reject`, { method: 'POST' });
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
