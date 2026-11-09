// /admin/jobs/<id>: form chỉnh sửa + xem trước dựng ở server + thanh tóm tắt các ô cần xem.
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const root = $('#rv-root');
  const id = root.dataset.id;
  const form = $('#rv-form');
  const layout = $('#rv-layout');
  const LABEL = { title: 'Chức danh', company: 'Công ty', location: 'Địa điểm', mode: 'Hình thức', level: 'Cấp bậc', type: 'Loại hợp đồng', salary: 'Lương', headcount: 'Số lượng', deadline: 'Hạn nộp', skills: 'Kỹ năng', desc: 'Mô tả', req: 'Yêu cầu', ben: 'Quyền lợi', email: 'Email', phone: 'SĐT', person: 'Người liên hệ', link: 'Link ứng tuyển' };

  const val = (n) => form.elements[n].value.trim();
  const lines = (n) => val(n).split('\n').map((s) => s.replace(/^[-•*]\s*/, '').trim()).filter(Boolean);
  const collect = () => ({
    title: val('title'), company: val('company'), location: val('location'), mode: val('mode'), level: val('level'), type: val('type'),
    headcount: val('headcount'), deadline: val('deadline'),
    salary_min: val('salary_min'), salary_max: val('salary_max'), salary_unit: val('salary_unit'), salary_per: val('salary_per'), salary_nego: form.elements.salary_nego.checked,
    skills: val('skills').split(',').map((s) => s.trim()).filter(Boolean),
    description: lines('description'), requirements: lines('requirements'), benefits: lines('benefits'),
    contact_email: val('contact_email'), contact_phone: val('contact_phone'), contact_person: val('contact_person'), contact_link: val('contact_link'),
  });

  async function post(url, data) {
    const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) });
    if (!res.ok) { const j = await res.json().catch(() => ({})); throw new Error(typeof j.detail === 'string' ? j.detail : res.statusText); }
    return res;
  }

  // Xem trước: server dựng bằng đúng template của trang công khai; gõ xong 300ms mới gọi, bỏ kết quả cũ.
  let timer, seq = 0;
  function preview() {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      const mine = ++seq;
      try {
        const res = await post('/admin/jobs/preview', collect());
        const html = await res.text();
        if (mine === seq) $('#rv-preview').innerHTML = html;
      } catch { /* xem trước là phụ, lỗi mạng thì giữ bản cũ */ }
    }, 300);
  }

  // Thanh tóm tắt (chỉ có ở bản nháp từ AI): đếm lại theo trạng thái ô hiện tại.
  function refreshBar() {
    const box = $('#rv-chips');
    if (!box) return;
    const fields = $$('.field[data-key]', form);
    const flagged = fields.filter((f) => f.classList.contains('missing') || f.classList.contains('inferred'));
    const miss = flagged.filter((f) => f.classList.contains('missing')).length;
    const inf = flagged.length - miss;
    const chip = (f) => `<button type="button" class="rv-chip ${f.classList.contains('missing') ? 'missing' : 'inferred'}" data-jump="${f.dataset.key}">${LABEL[f.dataset.key]}</button>`;
    box.innerHTML = `<div class="rv-sum"><b>AI điền ${fields.length - miss}/${fields.length} trường</b>${miss ? `<span class="flag miss">${miss} thiếu</span>` : ''}${inf ? `<span class="flag inf">${inf} suy luận</span>` : ''}${flagged.length ? '<span style="color:var(--muted)">· bấm để nhảy tới ô cần xem</span>' : ''}</div>
      <div class="rv-jump">${flagged.length ? flagged.map(chip).join('') : '<span class="rv-ok">Đã xem xong các ô cần kiểm tra. Có thể đăng.</span>'}</div>`;
  }

  function setView(v) {
    layout.dataset.view = v;
    $$('[data-tab]').forEach((b) => b.classList.toggle('on', b.dataset.tab === v));
  }

  form.addEventListener('input', (e) => {
    e.target.closest('.field')?.classList.remove('missing', 'inferred');
    refreshBar();
    preview();
  });
  root.addEventListener('click', async (e) => {
    const tab = e.target.closest('[data-tab]');
    if (tab) return setView(tab.dataset.tab);
    const jump = e.target.closest('[data-jump]');
    if (jump) {
      setView('edit');
      const fld = $(`.field[data-key="${jump.dataset.jump}"]`, form);
      fld.scrollIntoView({ block: 'center', behavior: 'smooth' });
      fld.querySelector('input, textarea, select')?.focus({ preventScroll: true });
      return;
    }
    const save = e.target.closest('[data-save]');
    if (!save) return;
    if (!val('title')) { setView('edit'); form.elements.title.focus(); return alert('Cần nhập Chức danh.'); }
    $$('[data-save]').forEach((b) => { b.disabled = true; });
    try {
      await post(`/admin/jobs/${id}`, { ...collect(), action: save.dataset.save });
      location.href = `/admin/jobs#${id}`;
    } catch (err) {
      alert(`Lỗi: ${err.message}`);
      $$('[data-save]').forEach((b) => { b.disabled = false; });
    }
  });

  refreshBar();
})();
