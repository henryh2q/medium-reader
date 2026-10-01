// Khi mở app PWA từ Home Screen, iOS/Android giữ nguyên trang cũ trong bộ nhớ thay
// vì tải lại — nên bài mới thêm từ lúc đó sẽ không hiện cho đến khi tự tay reload.
// Script này tự reload trang khi app quay lại foreground, miễn là đã rời đi đủ lâu
// (tránh reload vô ích khi chỉ lướt sang tab khác vài giây rồi quay lại ngay).
(() => {
  const STALE_AFTER_MS = 30_000;
  let hiddenAt = null;

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      hiddenAt = Date.now();
    } else if (hiddenAt && Date.now() - hiddenAt > STALE_AFTER_MS) {
      location.reload();
    }
  });
})();
