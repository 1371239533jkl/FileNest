/* 文件搜索 / 回收站 / 内容索引 / 详情弹窗 */
'use strict';

/* ── 通用文件表格 ──
   items: 文件记录数组；tags/cls: {file_id:[...]} 映射。
   opts.selectable 启用勾选；opts.actions 为 [{label,cls,onClick(file,row)}]。 */
function buildFileTable(items, tags, cls, { selectable = false, onSelect, actions = [] } = {}) {
  const tbl = document.createElement('table');
  tbl.className = 'tbl';
  const thead = document.createElement('thead');
  const tr = document.createElement('tr');
  const cols = [];
  if (selectable) cols.push('');
  cols.push('文件名', '类型', '大小', '状态', '标签', '分类', '修改时间', '操作');
  for (const c of cols) { const th = document.createElement('th'); th.textContent = c; tr.appendChild(th); }
  thead.appendChild(tr);
  tbl.appendChild(thead);
  const tbody = document.createElement('tbody');
  const selected = new Set();
  const checkboxes = [];
  const emit = () => { if (onSelect) onSelect(selected); };
  for (const f of items) {
    const row = document.createElement('tr');
    if (selectable) {
      const td = document.createElement('td');
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.onchange = () => { cb.checked ? selected.add(f.id) : selected.delete(f.id); emit(); };
      checkboxes.push(cb);
      td.appendChild(cb);
      row.appendChild(td);
    }
    const nameTd = document.createElement('td');
    nameTd.style.maxWidth = '360px';
    nameTd.innerHTML = `<span class="name-cell">${API.esc(f.file_name || '')}</span>` +
      `<div class="path-cell" title="${API.esc(f.file_path || '')}">${API.esc(f.file_path || '')}</div>`;
    row.appendChild(nameTd);
    const typeTd = document.createElement('td');
    typeTd.textContent = UI.ftype(f.file_type);
    row.appendChild(typeTd);
    const sizeTd = document.createElement('td');
    sizeTd.className = 'num';
    sizeTd.textContent = API.fmtBytes(f.file_size);
    row.appendChild(sizeTd);
    const statusTd = document.createElement('td');
    const st = f.status || 'active';
    statusTd.appendChild(UI.badge(st === 'active' ? '在用' : st, st === 'active' ? 'green' : 'gray'));
    if (f.is_duplicate) statusTd.appendChild(UI.badge('重复', 'red'));
    row.appendChild(statusTd);
    const tagTd = document.createElement('td');
    for (const t of (tags[f.id] || [])) {
      const c = document.createElement('span');
      c.className = 'tag-chip';
      c.textContent = t;
      tagTd.appendChild(c);
    }
    row.appendChild(tagTd);
    const clsTd = document.createElement('td');
    for (const c of (cls[f.id] || [])) {
      const s = document.createElement('span');
      s.className = 'tag-chip';
      s.style.background = 'rgba(167,139,250,.15)';
      s.style.color = 'var(--purple)';
      s.textContent = c;
      clsTd.appendChild(s);
    }
    row.appendChild(clsTd);
    const timeTd = document.createElement('td');
    timeTd.textContent = API.fmtTime(f.modify_time || f.create_time);
    row.appendChild(timeTd);
    const actTd = document.createElement('td');
    actTd.style.whiteSpace = 'nowrap';
    for (const a of actions) {
      const b = document.createElement('button');
      b.className = 'btn small' + (a.cls ? ' ' + a.cls : '');
      b.textContent = a.label;
      b.onclick = () => a.onClick(f, row);
      actTd.appendChild(b);
    }
    row.appendChild(actTd);
    tbody.appendChild(row);
  }
  tbl.appendChild(tbody);
  return {
    tbl, selected,
    clear() { for (const cb of checkboxes) cb.checked = false; selected.clear(); emit(); },
  };
}

/* ── 文件操作 ── */
async function doDeleteFile(f) {
  if (!await UI.confirm(`确定将「${f.file_name}」移入回收区？`, { danger: true })) return;
  const r = await API.post('/api/files/delete?file_id=' + f.id);
  UI.toast(r.message || '已移入回收区', 'ok');
  App.refresh();
}

async function renameFileDialog(f) {
  const v = await UI.formModal({
    title: '重命名文件',
    fields: [{ name: 'new_name', label: '新文件名', type: 'text', value: f.file_name, required: true, full: true }],
  });
  if (!v) return;
  await API.post('/api/files/rename', { file_id: f.id, new_name: v.new_name.trim() });
  UI.toast('已重命名', 'ok');
  App.refresh();
}

async function moveFileDialog(f) {
  const v = await UI.formModal({
    title: '移动文件',
    fields: [{ name: 'target_dir', label: '目标目录', type: 'text', placeholder: '例如 /home/user/Documents', required: true, full: true }],
  });
  if (!v) return;
  await API.post('/api/files/move', { file_id: f.id, target_dir: v.target_dir.trim() });
  UI.toast('已移动', 'ok');
  App.refresh();
}

async function addTagsDialog(fileIds, label = '批量添加标签') {
  const v = await UI.formModal({
    title: label,
    fields: [{ name: 'tags', label: '标签（逗号分隔）', type: 'text', placeholder: '例如 工作, 重要', required: true, full: true }],
  });
  if (!v) return;
  const tags = v.tags.split(/[,，]/).map(s => s.trim()).filter(Boolean);
  if (!tags.length) return;
  const r = await API.post('/api/tags/batch-add', { file_ids: fileIds, tags });
  UI.toast(`已添加 ${r.added} 条标签`, 'ok');
  App.refresh();
}

/* ── 文件详情弹窗 ── */
async function openFileDetail(id) {
  const modal = UI.modal({ title: '文件详情', body: UI.spin() });
  let f;
  try {
    f = await API.get('/api/files/' + id);
  } catch (e) {
    modal.body.innerHTML = `<div class="empty">${API.esc(e.message)}</div>`;
    return;
  }
  const body = modal.body;
  body.innerHTML = '';
  const grid = document.createElement('div');
  grid.className = 'detail-grid';
  const kv = (k, v, pre) => {
    const kd = document.createElement('div'); kd.className = 'k'; kd.textContent = k;
    const vd = document.createElement('div'); vd.className = 'v';
    if (pre) vd.style.whiteSpace = 'pre-wrap';
    vd.textContent = (v === null || v === undefined || v === '') ? '-' : String(v);
    grid.append(kd, vd);
  };
  kv('文件名', f.file_name);
  kv('路径', f.file_path);
  kv('类型', UI.ftype(f.file_type) + (f.file_extension ? ' · ' + f.file_extension : ''));
  kv('大小', API.fmtBytes(f.file_size));
  kv('文件哈希', f.file_hash);
  kv('状态', f.status);
  kv('重复', f.is_duplicate ? '是' : '否');
  kv('创建时间', API.fmtTime(f.create_time));
  kv('修改时间', API.fmtTime(f.modify_time));
  kv('扫描时间', API.fmtTime(f.scan_time));
  kv('标签', (f.tags || []).join('，'));
  kv('分类', (f.classifications || []).map(c => `${c.classification_type}:${c.classification_value}`).join('；'));
  if (f.content_excerpt) kv('内容摘录', f.content_excerpt, true);
  if (f.metadata) {
    let meta = f.metadata;
    if (typeof meta === 'string') { try { meta = JSON.parse(meta); } catch (_) { /* keep */ } }
    try { kv('元数据', JSON.stringify(meta, null, 2), true); } catch (_) { kv('元数据', String(meta), true); }
  }
  if (f.relations && f.relations.length) {
    kv('版本关系', f.relations.map(r => `${r.relation_type} → #${r.related_file_id || r.target_file_id}`).join('；'));
  }
  body.appendChild(grid);
  const foot = document.createElement('div');
  foot.className = 'modal-foot';
  const mk = (label, cls, fn) => {
    const b = document.createElement('button');
    b.className = 'btn' + (cls ? ' ' + cls : '');
    b.textContent = label;
    b.onclick = fn;
    foot.appendChild(b);
    return b;
  };
  mk('AI 描述', '', async () => {
    const ab = document.createElement('div');
    ab.className = 'ai-box';
    ab.innerHTML = '<h4>AI 描述</h4><p>生成中…</p>';
    body.appendChild(ab);
    try {
      const r = await API.post('/api/ai/describe', { file_id: id });
      ab.querySelector('p').textContent = r.description || '（无描述内容）';
    } catch (e) { ab.remove(); UI.toast(e.message, 'err'); }
  });
  mk('索引内容', '', async () => {
    const r = await API.post('/api/content/index/' + id);
    UI.toast(`已索引 ${r.indexed} 条`, 'ok');
  });
  mk('重命名', '', () => { UI.close(modal); renameFileDialog(f); });
  mk('移动', '', () => { UI.close(modal); moveFileDialog(f); });
  mk('删除', 'danger', async () => { UI.close(modal); await doDeleteFile(f); });
  modal.modal.appendChild(foot);
}

/* ═══════════ 文件搜索视图 ═══════════ */
Views.files = {
  title: '文件搜索',
  state: { page: 0, pageSize: 50, qs: {}, selected: new Set() },

  async render(el, opts = {}) {
    this.state.qs = Object.assign({}, opts.qs || {});
    this.state.page = 0;
    this.state.selected.clear();
    el.innerHTML = '';
    const bar = document.createElement('div');
    bar.className = 'filter-bar';
    bar.innerHTML = `
      <input data-f="name" type="text" placeholder="文件名包含…">
      <select data-f="file_type"><option value="">类型</option>
        <option value="image">图片</option><option value="document">文档</option>
        <option value="code">代码</option><option value="video">视频</option>
        <option value="audio">音频</option><option value="archive">压缩包</option>
        <option value="executable">可执行文件</option><option value="other">其他</option></select>
      <input data-f="extension" type="text" placeholder="扩展名，如 pdf" style="width:110px">
      <input data-f="min_size" type="number" placeholder="最小大小(B)" style="width:110px">
      <input data-f="max_size" type="number" placeholder="最大大小(B)" style="width:110px">
      <input data-f="tag" type="text" placeholder="标签" style="width:110px">
      <input data-f="content" type="text" placeholder="全文内容…" style="width:130px">
      <span class="spacer"></span>
      <button data-act="saveq" class="btn small">另存为集合</button>
      <button data-act="search" class="btn primary small">搜索</button>`;
    el.appendChild(bar);
    for (const [k, v] of Object.entries(this.state.qs)) {
      const inp = bar.querySelector(`[data-f="${k}"]`);
      if (inp) inp.value = v;
    }
    bar.querySelector('[data-act="search"]').onclick = () => {
      const qs = {};
      for (const inp of bar.querySelectorAll('[data-f]')) {
        if (inp.value) qs[inp.dataset.f] = inp.value.trim();
      }
      if (qs.min_size) qs.min_size = parseInt(qs.min_size, 10);
      if (qs.max_size) qs.max_size = parseInt(qs.max_size, 10);
      this.state.qs = qs;
      this.state.page = 0;
      this.load(el);
    };
    bar.querySelector('[data-act="saveq"]').onclick = async () => {
      const qs = {};
      for (const inp of bar.querySelectorAll('[data-f]')) {
        if (inp.value) qs[inp.dataset.f] = inp.value.trim();
      }
      if (!Object.keys(qs).length) { UI.toast('请先设置筛选条件', 'err'); return; }
      const v = await UI.formModal({
        title: '另存为智能集合',
        fields: [{ name: 'name', label: '集合名称', type: 'text', required: true, full: true }],
      });
      if (!v) return;
      await API.post('/api/saved-queries', { name: v.name.trim(), params: qs });
      UI.toast('已保存智能集合', 'ok');
    };

    const results = document.createElement('div');
    results.dataset.results = '1';
    el.appendChild(results);
    await this.load(el);
  },

  async load(el) {
    const box = el.querySelector('[data-results]');
    if (!box) return;
    box.innerHTML = '';
    box.appendChild(UI.spin());
    const qs = Object.assign({}, this.state.qs, { page: this.state.page, page_size: this.state.pageSize });
    let d;
    try { d = await API.get('/api/files', qs); }
    catch (e) { box.innerHTML = ''; box.appendChild(UI.empty(e.message)); return; }
    box.innerHTML = '';
    if (!d.items || !d.items.length) { box.appendChild(UI.empty('没有匹配的文件')); return; }
    const self = this;
    const ft = buildFileTable(d.items, d.tags || {}, d.classifications || {}, {
      selectable: true,
      onSelect: (sel) => {
        self.state.selected = sel;
        const bb = box.querySelector('[data-batch]');
        if (bb) bb.querySelector('.cnt').textContent = `已选 ${sel.size} 项`;
      },
      actions: [
        { label: '详情', onClick: (f) => openFileDetail(f.id) },
        { label: '重命名', onClick: (f) => renameFileDialog(f) },
        { label: '移动', onClick: (f) => moveFileDialog(f) },
        { label: '删除', cls: 'danger', onClick: (f) => doDeleteFile(f) },
      ],
    });
    const batch = document.createElement('div');
    batch.className = 'filter-bar';
    batch.dataset.batch = '1';
    batch.style.marginBottom = '10px';
    batch.innerHTML = `<span class="cnt" style="color:var(--text-dim)">已选 0 项</span>`;
    const mkBatch = (label, cls, fn) => {
      const b = document.createElement('button');
      b.className = 'btn small' + (cls ? ' ' + cls : '');
      b.textContent = label;
      b.onclick = () => fn([...self.state.selected]);
      batch.appendChild(b);
    };
    mkBatch('批量删除', 'danger', async (ids) => {
      if (!ids.length) { UI.toast('未选择文件', 'err'); return; }
      if (!await UI.confirm(`将 ${ids.length} 个文件移入回收区？`, { danger: true })) return;
      const r = await API.post('/api/files/delete/batch', { file_ids: ids });
      UI.toast(`成功 ${r.success}，失败 ${r.failed}`, 'ok');
      self.state.selected.clear();
      App.refresh();
    });
    mkBatch('批量重命名', '', async (ids) => {
      if (!ids.length) { UI.toast('未选择文件', 'err'); return; }
      const v = await UI.formModal({
        title: '批量重命名',
        fields: [{ name: 'pattern', label: '命名模板', type: 'text',
          value: '{date}_{type}_{original_name}', full: true,
          placeholder: '可用 {date}/{type}/{extension}/{original_name} 等' }],
      });
      if (!v) return;
      const preview = await API.post('/api/files/rename/preview', { file_ids: ids, pattern: v.pattern.trim() || undefined });
      if (!await UI.confirm(`将重命名 ${preview.items.length} 个文件：\n` +
        preview.items.slice(0, 8).map(i => `${i.old_name || i.file_name} → ${i.new_name}`).join('\n'),
        { title: '重命名预览' })) return;
      const r = await API.post('/api/files/rename/batch', { file_ids: ids, pattern: v.pattern.trim() || undefined });
      UI.toast(`成功 ${r.success}，失败 ${r.failed}`, 'ok');
      App.refresh();
    });
    mkBatch('批量移动', '', async (ids) => {
      if (!ids.length) { UI.toast('未选择文件', 'err'); return; }
      const v = await UI.formModal({
        title: '批量移动',
        fields: [{ name: 'target_dir', label: '目标目录', type: 'text', required: true, full: true }],
      });
      if (!v) return;
      const r = await API.post('/api/files/move/batch', { file_ids: ids, target_dir: v.target_dir.trim() });
      UI.toast(`成功 ${r.success}，失败 ${r.failed}`, 'ok');
      App.refresh();
    });
    mkBatch('添加标签', '', (ids) => {
      if (!ids.length) { UI.toast('未选择文件', 'err'); return; }
      addTagsDialog(ids);
    });
    box.appendChild(batch);
    box.appendChild(ft.tbl);
    box.appendChild(UI.pager({
      page: d.page, pageSize: d.page_size, total: d.total,
      onChange: (p) => { self.state.page = p; self.load(el); },
    }));
  },
};

/* ═══════════ 回收站视图 ═══════════ */
Views.recycle = {
  title: '回收站',
  state: { page: 0, pageSize: 50 },
  async render(el) {
    el.innerHTML = '';
    el.appendChild(UI.spin());
    const d = await API.get('/api/recycle', { page: this.state.page, page_size: this.state.pageSize });
    el.innerHTML = '';
    if (!d.items.length) { el.appendChild(UI.empty('回收站为空')); return; }
    const tbl = document.createElement('table');
    tbl.className = 'tbl';
    tbl.innerHTML = '<thead><tr><th>文件名</th><th>路径</th><th>大小</th><th>删除时间</th><th>操作</th></tr></thead>';
    const tbody = document.createElement('tbody');
    const self = this;
    for (const f of d.items) {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td><span class="name-cell">${API.esc(f.file_name)}</span></td>` +
        `<td class="path-cell" title="${API.esc(f.file_path)}">${API.esc(f.file_path)}</td>` +
        `<td class="num">${API.fmtBytes(f.file_size)}</td>` +
        `<td>${API.fmtTime(f.delete_time || f.modify_time)}</td>`;
      const act = document.createElement('td');
      act.style.whiteSpace = 'nowrap';
      const mk = (label, cls, fn) => {
        const b = document.createElement('button');
        b.className = 'btn small' + (cls ? ' ' + cls : '');
        b.textContent = label;
        b.onclick = fn;
        act.appendChild(b);
      };
      mk('恢复预览', '', async () => {
        try {
          const p = await API.get(`/api/files/${f.id}/restore/preview`);
          UI.toast(`将恢复到：${p.target_path || p.destination || '（未知）'}`, 'info');
        } catch (e) { UI.toast(e.message, 'err'); }
      });
      mk('恢复', 'primary', async () => {
        if (!await UI.confirm(`恢复「${f.file_name}」？`)) return;
        const r = await API.post(`/api/files/${f.id}/restore`, { conflict_strategy: 'rename' });
        UI.toast(`已恢复到 ${r.file_path}`, 'ok');
        App.refresh();
      });
      mk('永久删除', 'danger', async () => {
        if (!await UI.confirm(`永久删除「${f.file_name}」？此操作不可恢复！`, { danger: true })) return;
        await API.del(`/api/files/${f.id}?confirm=true`);
        UI.toast('已永久删除', 'ok');
        App.refresh();
      });
      tr.appendChild(act);
      tbody.appendChild(tr);
    }
    tbl.appendChild(tbody);
    el.appendChild(tbl);
    el.appendChild(UI.pager({
      page: d.page, pageSize: d.page_size, total: d.total,
      onChange: (p) => { self.state.page = p; self.render(el); },
    }));
  },
};

/* ═══════════ 内容索引视图 ═══════════ */
Views.content = {
  title: '内容索引',
  async render(el) {
    el.innerHTML = '';
    const [stats] = await Promise.all([API.get('/api/content/stats')]);
    const panel = document.createElement('div');
    panel.className = 'panel';
    panel.innerHTML = `<div class="panel-title"><h3>全文索引</h3>` +
      `<div class="actions"><button class="btn small" data-act="all">索引全部活跃文件</button></div></div>`;
    const info = document.createElement('p');
    info.style.color = 'var(--text-dim)';
    info.style.marginBottom = '12px';
    info.textContent = `当前已索引 ${stats.indexed} 条内容记录。索引范围受配置 MAX_FILE_SIZE_FOR_HASH 等限制。`;
    panel.appendChild(info);
    panel.querySelector('[data-act="all"]').onclick = async (e) => {
      if (!await UI.confirm('对全部活跃文件重新建立内容索引？', { danger: true })) return;
      e.target.textContent = '索引中…';
      e.target.disabled = true;
      try {
        const r = await API.post('/api/content/index/all?limit=1000');
        UI.toast(`完成：索引 ${r.indexed}，跳过 ${r.skipped || 0}，失败 ${r.failed || 0}`, 'ok');
      } finally {
        e.target.textContent = '索引全部活跃文件';
        e.target.disabled = false;
      }
    };
    el.appendChild(panel);

    const box = document.createElement('div');
    box.className = 'filter-bar';
    box.innerHTML = '<input data-q type="text" placeholder="搜索文件内容…" style="flex:1">' +
      '<button data-go class="btn primary small">搜索</button>';
    el.appendChild(box);
    const res = document.createElement('div');
    res.dataset.results = '1';
    el.appendChild(res);
    box.querySelector('[data-go]').onclick = async () => {
      const q = box.querySelector('[data-q]').value.trim();
      if (!q) return;
      res.innerHTML = '';
      res.appendChild(UI.spin());
      const d = await API.get('/api/content/search', { q, limit: 100 });
      res.innerHTML = '';
      if (!d.items.length) { res.appendChild(UI.empty('没有匹配的内容')); return; }
      const ft = buildFileTable(d.items, {}, {}, {
        actions: [{ label: '详情', onClick: (f) => openFileDetail(f.id) }],
      });
      res.appendChild(ft.tbl);
    };
  },
};
