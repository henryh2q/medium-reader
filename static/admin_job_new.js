// /admin/jobs/new: 1 textarea + 1 file -> POST /admin/jobs/extract -> chuyển sang trang duyệt.
(() => {
  const $ = (s) => document.querySelector(s);
  const MAX = 10 * 1024 * 1024;
  const EXTS = ['pdf', 'docx', 'txt', 'md', 'png', 'jpg', 'jpeg', 'webp', 'gif'];
  const jt = $('#jt'), dz = $('#dz'), jf = $('#jf'), err = $('#err');
  let file = null;

  const size = (n) => (n > 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);
  const refresh = () => { $('#extract').disabled = !(jt.value.trim() || file); };
  const fail = (msg) => { err.textContent = msg; err.hidden = false; };

  function setFile(f) {
    err.hidden = true;
    if (f) {
      const ext = f.name.split('.').pop().toLowerCase();
      if (!EXTS.includes(ext)) return fail('Chỉ nhận file PDF, Word (.docx), ảnh, .txt hoặc .md.');
      if (f.size > MAX) return fail('File quá lớn (tối đa 10 MB).');
    }
    file = f;
    dz.hidden = !!f;
    $('#file-chip').hidden = !f;
    if (f) { $('#file-ext').textContent = f.name.split('.').pop().slice(0, 4); $('#file-name').textContent = f.name; $('#file-size').textContent = size(f.size); }
    refresh();
  }

  jt.addEventListener('input', refresh);
  jf.addEventListener('change', () => { if (jf.files[0]) setFile(jf.files[0]); jf.value = ''; });
  $('#file-x').addEventListener('click', () => setFile(null));
  ['dragenter', 'dragover'].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add('over'); }));
  ['dragleave', 'drop'].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove('over'); }));
  dz.addEventListener('drop', (e) => { if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]); });

  const toBase64 = (f) => new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(',')[1]);
    r.onerror = reject;
    r.readAsDataURL(f);
  });

  $('#extract').addEventListener('click', async () => {
    err.hidden = true;
    $('#post-card').hidden = true;
    $('#progress-card').hidden = false;
    // Bước thật chỉ có 1 lời gọi; các mốc này chỉ báo "đang chạy" theo thời gian.
    const steps = [...document.querySelectorAll('#steps li')];
    steps.forEach((s) => s.classList.remove('doing', 'done'));
    let i = 0;
    steps[0].classList.add('doing');
    const timer = setInterval(() => {
      if (i >= steps.length - 1) return;
      steps[i].classList.replace('doing', 'done');
      steps[++i].classList.add('doing');
    }, 2500);
    try {
      const res = await fetch('/admin/jobs/extract', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: jt.value, filename: file ? file.name : '', content_b64: file ? await toBase64(file) : '' }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Không trích xuất được, thử lại.');
      steps.forEach((s) => { s.classList.remove('doing'); s.classList.add('done'); });
      location.href = data.url;
    } catch (e) {
      clearInterval(timer);
      $('#progress-card').hidden = true;
      $('#post-card').hidden = false;
      fail(e.message);
    }
  });
})();
