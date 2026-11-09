// /viec-lam: bấm thẻ ở màn rộng thì chỉ thay khung chi tiết (không tải lại trang) và đổi URL;
// màn hẹp để trình duyệt điều hướng bình thường (danh sách -> trang chi tiết).
(() => {
  const list = document.getElementById('jb-list');
  const body = document.getElementById('jb-detail-body');
  const detail = document.getElementById('jb-detail');
  const wide = window.matchMedia('(min-width: 52.01rem)');

  async function open(card) {
    const url = new URL(card.href);
    url.searchParams.set('partial', '1');
    try {
      const res = await fetch(url);
      if (!res.ok) throw new Error(res.status);
      body.innerHTML = await res.text();
    } catch {
      location.href = card.href;  // lỗi mạng/404: cứ điều hướng thường
      return;
    }
    list.querySelectorAll('.jb-card.sel').forEach((c) => c.classList.remove('sel'));
    card.classList.add('sel');
    detail.scrollTop = 0;
    history.pushState(null, '', card.href);
    document.title = `${card.querySelector('.jb-title').textContent} | Việc làm | Đọc gì hôm nay`;
  }

  list.addEventListener('click', (e) => {
    const card = e.target.closest('a.jb-card');
    if (!card || !wide.matches || e.metaKey || e.ctrlKey || e.shiftKey || e.button) return;
    e.preventDefault();
    open(card);
  });
  window.addEventListener('popstate', () => location.reload());

  detail.addEventListener('click', async (e) => {
    const btn = e.target.closest('[data-share]');
    if (!btn) return;
    const link = location.origin + btn.dataset.path;
    try {
      if (navigator.share && !wide.matches) await navigator.share({ url: link });
      else { await navigator.clipboard.writeText(link); btn.textContent = 'Đã sao chép ✓'; setTimeout(() => { btn.textContent = 'Sao chép link'; }, 1500); }
    } catch { /* người dùng huỷ chia sẻ */ }
  });
})();
