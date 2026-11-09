// /admin/jobs: chọn job, lọc/tìm tại chỗ, đăng/gỡ/xoá. URL #<id> nhớ job đang chọn qua lần tải lại.
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const layout = $('#a-layout');
  const body = $('#a-detail-body');
  const cards = [...document.querySelectorAll('#a-list .jb-card')];
  const fold = (s) => s.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/đ/g, 'd');
  let filter = 'all';
  let query = '';

  function select(id, view) {
    cards.forEach((c) => c.classList.toggle('sel', c.dataset.id === String(id)));
    const tpl = id && document.getElementById(`tpl-${id}`);
    body.replaceChildren(...(tpl ? [tpl.content.cloneNode(true)] : []));
    $('#a-detail').scrollTop = 0;
    layout.dataset.view = view;
    history.replaceState(null, '', id ? `#${id}` : location.pathname);
  }

  function apply() {
    const terms = fold(query).split(/\s+/).filter(Boolean);
    const shown = cards.filter((c) => {
      const ok = (filter === 'all' || c.dataset.state === filter) && terms.every((t) => c.dataset.search.includes(t));
      c.hidden = !ok;
      return ok;
    });
    $('#a-count').innerHTML = `<b>${shown.length} job</b>`;
    $('#a-empty').hidden = shown.length > 0 || cards.length === 0;
    const current = shown.find((c) => c.classList.contains('sel'));
    if (!current) select(shown[0]?.dataset.id, 'list');
    else layout.dataset.view = 'list';
  }

  $('#a-filters').addEventListener('click', (e) => {
    const b = e.target.closest('[data-filter]');
    if (!b) return;
    filter = b.dataset.filter;
    document.querySelectorAll('#a-filters .jb-pill').forEach((p) => p.classList.toggle('on', p === b));
    apply();
  });
  $('#a-q').addEventListener('input', (e) => { query = e.target.value; apply(); });
  $('#a-list').addEventListener('click', (e) => {
    const c = e.target.closest('.jb-card');
    if (c) select(c.dataset.id, 'detail');
  });
  $('#a-back').addEventListener('click', () => { layout.dataset.view = 'list'; });

  async function post(url, data) {
    const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data || {}) });
    if (!res.ok) { const j = await res.json().catch(() => ({})); throw new Error(typeof j.detail === 'string' ? j.detail : res.statusText); }
  }

  $('#a-detail').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-act]');
    if (!b) return;
    try {
      if (b.dataset.act === 'status') {
        await post(`/admin/jobs/${b.dataset.id}/status`, { status: b.dataset.to });
        location.reload();
      } else if (b.dataset.act === 'del') {
        if (!b.dataset.armed) {  // 2 bước thay cho confirm(), dễ bấm trên điện thoại
          b.dataset.armed = '1';
          b.textContent = 'Bấm lần nữa để xoá';
          setTimeout(() => { if (b.isConnected) { delete b.dataset.armed; b.textContent = 'Xoá'; } }, 3000);
          return;
        }
        await post(`/admin/jobs/${b.dataset.id}/delete`);
        history.replaceState(null, '', location.pathname);
        location.reload();
      }
    } catch (err) {
      alert(`Lỗi: ${err.message}`);
    }
  });

  const hashId = location.hash.slice(1);
  const initial = cards.find((c) => c.dataset.id === hashId);
  apply();
  if (initial) select(initial.dataset.id, 'detail');
})();
