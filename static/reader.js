(() => {
  const body = document.getElementById('article-body');
  if (!body) return;

  const articleId = Number(document.body.dataset.articleId);
  const btn = document.getElementById('explain-btn');
  const panel = document.getElementById('explain-panel');
  const panelBody = panel.querySelector('.panel-body');
  const cache = new Map();          // term -> data (trong phiên đọc)
  let pending = null;               // {text, range}

  /* ---------- Chuyển ngôn ngữ ---------- */
  const setLang = (lang) => {
    document.body.dataset.lang = lang;
    document.querySelectorAll('[data-set-lang]').forEach((b) =>
      b.setAttribute('aria-pressed', String(b.dataset.setLang === lang)));
    try { localStorage.setItem('reader-lang', lang); } catch {}
  };
  document.querySelectorAll('[data-set-lang]').forEach((b) =>
    b.addEventListener('click', () => setLang(b.dataset.setLang)));
  try { const saved = localStorage.getItem('reader-lang'); if (saved) setLang(saved); } catch {}

  /* ---------- Bắt vùng chọn ---------- */
  const readSelection = () => {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !sel.rangeCount) return null;
    const range = sel.getRangeAt(0);
    if (!body.contains(range.commonAncestorContainer)) return null;
    const text = sel.toString().replace(/\s+/g, ' ').trim();
    if (text.length < 2 || text.length > 80 || text.split(' ').length > 8) return null;
    return { text, range: range.cloneRange() };
  };

  const hideButton = () => { btn.hidden = true; };

  const showButton = () => {
    const s = readSelection();
    if (!s) return hideButton();
    pending = s;
    const r = s.range.getBoundingClientRect();
    btn.hidden = false;
    const w = btn.offsetWidth, h = btn.offsetHeight;
    // Trên cảm ứng, menu của hệ điều hành nằm phía trên => đặt nút phía dưới
    const touch = matchMedia('(pointer: coarse)').matches;
    const top = touch ? r.bottom + 12 : r.top - h - 10;
    const left = Math.min(window.innerWidth - w - 8, Math.max(8, r.left + r.width / 2 - w / 2));
    btn.style.top = `${Math.max(8, top) + window.scrollY}px`;
    btn.style.left = `${left + window.scrollX}px`;
  };

  let timer;
  document.addEventListener('selectionchange', () => {
    clearTimeout(timer);
    timer = setTimeout(showButton, 250);
  });

  btn.addEventListener('mousedown', (e) => e.preventDefault()); // giữ vùng chọn
  btn.addEventListener('click', () => {
    if (!pending) return;
    const { text, range } = pending;
    const context = contextOf(range);
    markTerm(range, text);
    window.getSelection().removeAllRanges();
    hideButton();
    explain(text, context);
  });

  // Chạm lại thuật ngữ đã tra để mở lại giải thích
  body.addEventListener('click', (e) => {
    const m = e.target.closest('mark.term');
    if (m) explain(m.dataset.term, contextOf(m));
  });

  const contextOf = (rangeOrEl) => {
    const node = rangeOrEl.startContainer ?? rangeOrEl;
    const el = node.nodeType === 1 ? node : node.parentElement;
    const block = el.closest('p, li, blockquote, h1, h2, h3, h4, td, pre') || el;
    return block.textContent.replace(/\s+/g, ' ').trim().slice(0, 1500);
  };

  const markTerm = (range, text) => {
    try {
      const mark = document.createElement('mark');
      mark.className = 'term';
      mark.dataset.term = text;
      range.surroundContents(mark);
    } catch { /* vùng chọn cắt ngang nhiều thẻ: bỏ qua việc tô */ }
  };

  /* ---------- Gọi API & hiển thị ---------- */
  const el = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  };

  const openPanel = (...nodes) => {
    panelBody.replaceChildren(...nodes);
    panel.hidden = false;
    document.body.classList.add('panel-open');
    panelBody.scrollTop = 0;
  };

  const section = (title, text) => {
    if (!text) return null;
    const s = el('section', 'x-section');
    s.append(el('h3', null, title));
    String(text).split(/\n{2,}/).forEach((p) => s.append(el('p', null, p)));
    return s;
  };

  const render = (d) => {
    const h = el('h2', 'x-term');
    h.append(el('span', null, d.term));
    const nodes = [h];
    if (d.pronunciation && (d.pronunciation.ipa || d.pronunciation.vi)) {
      const p = el('p', 'x-pronunciation');
      if (d.pronunciation.ipa) p.append(el('span', 'x-ipa', d.pronunciation.ipa));
      if (d.pronunciation.vi) p.append(el('span', 'x-vi-sound', `cách đọc: ${d.pronunciation.vi}`));
      nodes.push(p);
    }
    nodes.push(el('p', 'x-short', d.short),
      section('Giải thích', d.detail),
      section('Hình dung', d.analogy));
    let ex = section('Ví dụ', d.example);
    if (d.code && d.code.snippet) {
      if (!ex) { ex = el('section', 'x-section'); ex.append(el('h3', null, 'Ví dụ')); }
      const pre = el('pre');
      pre.append(el('code', null, d.code.snippet));
      ex.append(pre);
    }
    nodes.push(ex, section('Trong bài này', d.in_this_article));
    openPanel(...nodes.filter(Boolean));
  };

  const explain = async (term, context) => {
    const key = term.toLowerCase();
    if (cache.has(key)) return render(cache.get(key));
    openPanel(el('p', 'x-status', `Đang giải thích “${term}”…`));
    try {
      const res = await fetch('/api/explain', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ term, context, article_id: articleId }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Không lấy được giải thích.');
      cache.set(key, data);
      render(data);
    } catch (err) {
      openPanel(el('p', 'x-error', `${err.message} Bôi đen lại thuật ngữ để thử lần nữa.`));
    }
  };

  const closePanel = () => { panel.hidden = true; document.body.classList.remove('panel-open'); };
  panel.querySelector('.panel-close').addEventListener('click', closePanel);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closePanel(); });
})();
