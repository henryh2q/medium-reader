// Cuộn vô hạn ở trang chủ: server chỉ render sẵn trang đầu; khi khối skeleton #feed-more
// tiến gần màn hình thì gọi GET /api/articles để lấy trang kế tiếp và nối vào danh sách.
(() => {
  const more = document.getElementById('feed-more');
  if (!more) return; // đã hết bài ngay từ trang đầu

  const list = document.getElementById('entries');
  const skeleton = document.getElementById('feed-skeleton');
  const errorBox = document.getElementById('feed-error');
  const filters = new URLSearchParams(location.search); // giữ nguyên q / tag / category đang chọn
  let next = Number(more.dataset.next);
  let loading = false;

  const observer = new IntersectionObserver((hits) => {
    if (hits.some((h) => h.isIntersecting)) loadMore();
  }, { rootMargin: '600px 0px' }); // tải trước khi người đọc chạm tới cuối

  const loadMore = async () => {
    if (loading || next === null) return;
    loading = true;
    observer.unobserve(more);
    try {
      const params = new URLSearchParams();
      for (const key of ['q', 'tag', 'category']) {
        if (filters.get(key)) params.set(key, filters.get(key));
      }
      params.set('offset', next);
      const res = await fetch(`/api/articles?${params}`);
      if (!res.ok) throw new Error(res.status);
      const data = await res.json();

      const tpl = document.createElement('template');
      tpl.innerHTML = data.html;
      // Bài mới có thể được thêm lúc đang cuộn làm lệch offset => bỏ bài đã có để khỏi lặp.
      const fresh = [...tpl.content.querySelectorAll('.entry')].filter(
        (el) => !list.querySelector(`.entry[data-id="${el.dataset.id}"]`),
      );
      list.append(...fresh);
      // translate.js lắng nghe để gắn nút dịch + theo dõi bài đang dịch cho các dòng mới
      document.dispatchEvent(new CustomEvent('entries:added', { detail: { entries: fresh } }));

      next = data.next;
      if (next === null) {
        more.remove();
        observer.disconnect();
        return;
      }
      skeleton.hidden = false;
      errorBox.hidden = true;
      loading = false;
      // observe lại để callback chạy ngay nếu skeleton vẫn còn trong tầm nhìn (màn hình cao)
      observer.observe(more);
    } catch {
      loading = false;
      skeleton.hidden = true;
      errorBox.hidden = false;
    }
  };

  document.getElementById('feed-retry').addEventListener('click', () => {
    errorBox.hidden = true;
    skeleton.hidden = false;
    loadMore();
  });

  observer.observe(more);
})();
