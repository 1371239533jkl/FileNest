/* 历史 / 扫描 / 工作区 / 归档 / 版本关系 / 事件 / 健康 / 时间线 / AI / 设置 */
'use strict';

/* ═══════════ 操作历史 ═══════════ */
Views.history = {
  title: '操作历史',
  async render(el) {
    el.innerHTML = '';
    const [d, undoable] = await Promise.all([
      API.get('/api/history', { limit: 200 }),
      API.get('/api/history/undoable', { limit: 100 }),
    ]);
    el.innerHTML = '';
    const undoSet = new Set((undoable.items || []).map(i => i.id));
    const tbl = document.createElement('table');
    tbl.className = 'tbl';
    tbl.innerHTML = '<thead><tr><th>时间</th><th>类型</th><th>状态</th><th>文件</th><th>变更</th><th>批次</th><th>操作</th></tr></thead>';
    const tbody = document.createElement('tbody');
    for (const it of (d.items || [])) {
      const tr = document.createElement('tr');
      const t1 = document.createElement('td'); t1.textContent = API.fmtTime(it.operation_time); tr.appendChild(t1);
      const t2 = document.createElement('td');
      t2.appendChild(UI.badge(it.operation_type || '-'));
      tr.appendChild(t2);
      const t3 = document.createElement('td');
      const st = it.operation_status || it.status || '';
      t3.appendChild(UI.badge(st, st === 'success' ? 'green' : st === 'failed' ? 'red' : 'gray'));
      tr.appendChild(t3);
      const t4 = document.createElement('td');
      t4.innerHTML = `<span class="name-cell">${API.esc(it.file_name || it.file_path || '')}</span><div class="path-cell">${API.esc(it.file_path || '')}</div>`;
      tr.appendChild(t4);
      const t5 = document.createElement('td');
      t5.style.cssText = 'max-width:260px;color:var(--text-dim);font-size:12px';
      t5.textContent = [it.old_value, it.new_value].filter(Boolean).join(' → ') || '-';
      tr.appendChild(t5);
      const t6 = document.createElement('td');
      t6.textContent = it.batch_id || '-';
      tr.appendChild(t6);
      const t7 = document.createElement('td');
      if (undoSet.has(it.id)) {
        const b = document.createElement('button');
        b.className = 'btn small'; b.textContent = '撤销';
        b.onclick = async () => {
          if (!await UI.confirm('撤销该操作？')) return;
          await API.post(`/api/history/${it.id}/undo`);
          UI.toast('已撤销', 'ok'); App.refresh();
        };
        t7.appendChild(b);
      }
      tr.appendChild(t7);
      tbody.appendChild(tr);
    }
    tbl.appendChild(tbody);
    el.appendChild(tbl);
    if (!d.items.length) { el.innerHTML = ''; el.appendChild(UI.empty('暂无操作历史')); }
  },
};

/* ═══════════ 时间线 ═══════════ */
Views.timeline = {
  title: '时间线',
  async render(el) {
    el.innerHTML = '';
    const bar = document.createElement('div');
    bar.className = 'filter-bar';
    bar.innerHTML = `
      <select data-mode>
        <option value="all">全部</option><option value="operations">系统操作</option>
        <option value="external">外部事件</option></select>
      <input data-path type="text" placeholder="路径前缀…" style="flex:1">
      <button data-go class="btn primary small">刷新</button>`;
    el.appendChild(bar);
    const res = document.createElement('div');
    res.dataset.results = '1';
    el.appendChild(res);
    const load = async () => {
      res.innerHTML = ''; res.appendChild(UI.spin());
      const mode = bar.querySelector('[data-mode]').value;
      const path_prefix = bar.querySelector('[data-path]').value.trim() || undefined;
      const d = await API.get('/api/timeline', { mode, path_prefix, limit: 200 });
      res.innerHTML = '';
      if (!d.items.length) { res.appendChild(UI.empty('暂无事件')); return; }
      const tbl = document.createElement('table');
      tbl.className = 'tbl';
      tbl.innerHTML = '<thead><tr><th>时间</th><th>来源</th><th>类型</th><th>文件</th><th>变更</th></tr></thead>';
      const tbody = document.createElement('tbody');
      for (const it of d.items) {
        const tr = document.createElement('tr');
        const t1 = document.createElement('td'); t1.textContent = API.fmtTime(it.event_time); tr.appendChild(t1);
        const t2 = document.createElement('td');
        t2.appendChild(UI.badge(it.event_source === 'operations' ? '系统' : '外部', it.event_source === 'operations' ? 'blue' : 'purple'));
        tr.appendChild(t2);
        const t3 = document.createElement('td'); t3.textContent = it.event_type || ''; tr.appendChild(t3);
        const t4 = document.createElement('td');
        t4.innerHTML = `<span class="name-cell">${API.esc(it.file_name || it.file_path || '')}</span><div class="path-cell">${API.esc(it.file_path || '')}</div>`;
        tr.appendChild(t4);
        const t5 = document.createElement('td');
        t5.style.cssText = 'max-width:260px;color:var(--text-dim);font-size:12px';
        t5.textContent = [it.old_value, it.new_value].filter(Boolean).join(' → ') || (it.error_message || '-');
        tr.appendChild(t5);
        tbody.appendChild(tr);
      }
      tbl.appendChild(tbody);
      res.appendChild(tbl);
    };
    bar.querySelector('[data-go]').onclick = load;
    await load();
  },
};

/* ═══════════ 扫描目录 ═══════════ */
Views.scan = {
  title: '扫描目录',
  async render(el) {
    el.innerHTML = '';
    const d = await API.get('/api/scan/directories');
    el.innerHTML = '';
    const panel = document.createElement('div');
    panel.className = 'panel';
    const hh = document.createElement('div');
    hh.className = 'panel-title';
    const h = document.createElement('h3');
    h.textContent = `目录（${d.items.length}）`;
    hh.appendChild(h);
    const add = document.createElement('button');
    add.className = 'btn small'; add.textContent = '+ 添加目录';
    add.onclick = async () => {
      const v = await UI.formModal({ title: '添加扫描目录', fields: [
        { name: 'directory', label: '目录路径', type: 'text', required: true, full: true },
        { name: 'recursive', label: '递归扫描', type: 'checkbox', value: true },
      ] });
      if (!v) return;
      const r = await API.post(`/api/scan/directories?directory=${encodeURIComponent(v.directory.trim())}&recursive=${v.recursive}`);
      UI.toast(r.message || '已添加', 'ok'); App.refresh();
    };
    hh.appendChild(add);
    panel.appendChild(hh);
    if (!d.items.length) { panel.appendChild(UI.empty('暂无扫描目录')); el.appendChild(panel); return; }
    const tbl = document.createElement('table');
    tbl.className = 'tbl';
    tbl.innerHTML = '<thead><tr><th>目录</th><th>递归</th><th>启用</th><th>操作</th></tr></thead>';
    const tbody = document.createElement('tbody');
    for (const it of d.items) {
      const tr = document.createElement('tr');
      const t1 = document.createElement('td');
      t1.className = 'path-cell'; t1.textContent = it.directory; tr.appendChild(t1);
      const t2 = document.createElement('td'); t2.textContent = it.recursive ? '是' : '否'; tr.appendChild(t2);
      const t3 = document.createElement('td'); t3.textContent = it.is_active ? '启用' : '停用'; tr.appendChild(t3);
      const t4 = document.createElement('td');
      t4.style.whiteSpace = 'nowrap';
      const mk = (label, cls, fn) => {
        const b = document.createElement('button');
        b.className = 'btn small' + (cls ? ' ' + cls : '');
        b.textContent = label; b.onclick = fn;
        t4.appendChild(b);
      };
      mk('立即扫描', 'primary', async () => {
        const r = await API.post(`/api/scan?directory=${encodeURIComponent(it.directory)}&recursive=${it.recursive ? 1 : 0}`);
        UI.toast(`扫描完成：${r.scanned || r.found || ''} 个文件`, 'ok');
      });
      mk(it.is_active ? '停用' : '启用', '', async () => {
        await API.post(`/api/scan/directories/${it.id}/toggle?active=${!it.is_active}`);
        App.refresh();
      });
      mk('删除', 'danger', async () => {
        if (!await UI.confirm(`删除扫描目录「${it.directory}」？`, { danger: true })) return;
        await API.del(`/api/scan/directories/${it.id}`);
        App.refresh();
      });
      tr.appendChild(t4);
      tbody.appendChild(tr);
    }
    tbl.appendChild(tbody);
    panel.appendChild(tbl);
    el.appendChild(panel);
  },
};

/* ═══════════ 工作区 ═══════════ */
Views.workspaces = {
  title: '工作区',
  async render(el) {
    el.innerHTML = '';
    const d = await API.get('/api/workspaces');
    el.innerHTML = '';
    const panel = document.createElement('div');
    panel.className = 'panel';
    const hh = document.createElement('div');
    hh.className = 'panel-title';
    const h = document.createElement('h3');
    h.textContent = `工作区（${d.items.length}）`;
    hh.appendChild(h);
    const add = document.createElement('button');
    add.className = 'btn small'; add.textContent = '+ 新建';
    add.onclick = () => wsDialog(null);
    hh.appendChild(add);
    panel.appendChild(hh);
    if (!d.items.length) { panel.appendChild(UI.empty('暂无工作区')); el.appendChild(panel); return; }
    for (const it of d.items) {
      const row = document.createElement('div');
      row.className = 'rule-row';
      row.innerHTML =
        `<div><b>${API.esc(it.name)}</b> ${it.is_active === 0 || it.is_active === false ? '<span style="color:var(--text-dim)">(停用)</span>' : ''}` +
        `<div class="path-cell">${API.esc(it.root_path)}</div>` +
        `<div class="sub">规则 ${API.esc(it.rule_scope)} · 标签 ${API.esc(it.tag_scope)} · ${it.ai_allowed ? '允许 AI' : '禁 AI'}</div></div>`;
      const acts = document.createElement('div');
      acts.className = 'actions';
      const mk = (label, cls, fn) => {
        const b = document.createElement('button');
        b.className = 'btn small' + (cls ? ' ' + cls : '');
        b.textContent = label; b.onclick = fn;
        acts.appendChild(b);
      };
      mk('编辑', '', () => wsDialog(it));
      mk(it.is_active ? '停用' : '启用', '', async () => {
        await API.put(`/api/workspaces/${it.id}`, { is_active: !it.is_active });
        App.refresh();
      });
      mk('删除', 'danger', async () => {
        if (!await UI.confirm(`删除工作区「${it.name}」？`, { danger: true })) return;
        await API.del(`/api/workspaces/${it.id}`);
        App.refresh();
      });
      row.appendChild(acts);
      panel.appendChild(row);
    }
    el.appendChild(panel);

    function wsDialog(ws) {
      const isEdit = !!ws;
      UI.formModal({ title: isEdit ? '编辑工作区' : '新建工作区', wide: true, fields: [
        { name: 'name', label: '名称', type: 'text', value: ws?.name || '', required: true, full: true },
        { name: 'root_path', label: '根目录', type: 'text', value: ws?.root_path || '', required: true, full: true },
        { name: 'description', label: '描述', type: 'text', value: ws?.description || '', full: true },
        { name: 'rule_scope', label: '规则范围', type: 'select', value: ws?.rule_scope || 'all',
          options: ['all', 'file_type', 'tag', 'path'].map(v => ({ v, l: v })) },
        { name: 'tag_scope', label: '标签范围', type: 'select', value: ws?.tag_scope || 'all',
          options: ['all', 'allowed', 'restricted'].map(v => ({ v, l: v })) },
        { name: 'ai_allowed', label: '允许 AI 分析', type: 'checkbox', value: ws ? !!ws.ai_allowed : true },
      ], submitText: '保存' }).then(async (v) => {
        if (!v) return;
        if (isEdit) {
          await API.put(`/api/workspaces/${ws.id}`, {
            name: v.name.trim(), root_path: v.root_path.trim(), description: v.description.trim(),
            rule_scope: v.rule_scope, tag_scope: v.tag_scope, ai_allowed: v.ai_allowed,
          });
        } else {
          const qs = `name=${encodeURIComponent(v.name.trim())}&root_path=${encodeURIComponent(v.root_path.trim())}&description=${encodeURIComponent(v.description.trim())}&rule_scope=${v.rule_scope}&tag_scope=${v.tag_scope}&ai_allowed=${v.ai_allowed}`;
          await API.post(`/api/workspaces?${qs}`);
        }
        UI.toast('已保存', 'ok'); App.refresh();
      });
    }
  },
};

/* ═══════════ 归档包 ═══════════ */
Views.archives = {
  title: '归档包',
  async render(el) {
    el.innerHTML = '';
    const d = await API.get('/api/archives');
    el.innerHTML = '';
    const panel = document.createElement('div');
    panel.className = 'panel';
    const hh = document.createElement('div');
    hh.className = 'panel-title';
    const h = document.createElement('h3');
    h.textContent = `归档包（${d.items.length}）`;
    hh.appendChild(h);
    const add = document.createElement('button');
    add.className = 'btn small'; add.textContent = '+ 新建归档';
    add.onclick = async () => {
      const v = await UI.formModal({ title: '新建归档包', wide: true, fields: [
        { name: 'package_name', label: '包名', type: 'text', required: true, full: true },
        { name: 'output_dir', label: '输出目录', type: 'text', required: true, full: true },
        { name: 'source_paths', label: '源文件路径（每行一个）', type: 'textarea', required: true, full: true },
      ], submitText: '创建' });
      if (!v) return;
      const paths = v.source_paths.split(/\r?\n/).map(s => s.trim()).filter(Boolean);
      const qs = `package_name=${encodeURIComponent(v.package_name.trim())}&output_dir=${encodeURIComponent(v.output_dir.trim())}`;
      const r = await API.post(`/api/archives?${qs}`, { source_paths: paths });
      UI.toast('已创建归档包', 'ok'); App.refresh();
    };
    hh.appendChild(add);
    panel.appendChild(hh);
    if (!d.items.length) { panel.appendChild(UI.empty('暂无归档包')); el.appendChild(panel); return; }
    for (const it of d.items) {
      const row = document.createElement('div');
      row.className = 'rule-row';
      row.innerHTML =
        `<div><b>${API.esc(it.package_name)}</b> ${UI.badge(it.status || '-', it.status === 'completed' ? 'green' : 'blue').outerHTML}` +
        `<div class="path-cell">${API.esc(it.output_path || it.archive_path || '')}</div>` +
        `<div class="sub">${it.file_count ?? 0} 个文件 · ${API.fmtBytes(it.total_size)} · ${API.fmtTime(it.create_time)}</div></div>`;
      const acts = document.createElement('div');
      acts.className = 'actions';
      const mk = (label, cls, fn) => {
        const b = document.createElement('button');
        b.className = 'btn small' + (cls ? ' ' + cls : '');
        b.textContent = label; b.onclick = fn;
        acts.appendChild(b);
      };
      mk('标记完成', '', async () => { await API.post(`/api/archives/${it.id}/status?status=completed`); App.refresh(); });
      mk('删除', 'danger', async () => {
        if (!await UI.confirm(`删除归档包「${it.package_name}」？`, { danger: true })) return;
        await API.del(`/api/archives/${it.id}`);
        App.refresh();
      });
      row.appendChild(acts);
      panel.appendChild(row);
    }
    el.appendChild(panel);
  },
};

/* ═══════════ 版本关系 ═══════════ */
Views.relations = {
  title: '版本关系',
  state: { status: 'pending' },
  async render(el) {
    el.innerHTML = '';
    const bar = document.createElement('div');
    bar.className = 'filter-bar';
    bar.innerHTML = `<select data-s><option value="pending">待确认</option><option value="confirmed">已确认</option><option value="dismissed">已忽略</option></select>`;
    bar.querySelector('[data-s]').value = this.state.status;
    bar.querySelector('[data-s]').onchange = (e) => { this.state.status = e.target.value; this.render(el); };
    el.appendChild(bar);
    const d = await API.get('/api/relations', { status: this.state.status });
    const panel = document.createElement('div');
    panel.className = 'panel';
    panel.innerHTML = `<div class="panel-title"><h3>关系（${d.items.length}）</h3></div>`;
    if (!d.items.length) panel.appendChild(UI.empty('该状态下暂无版本关系'));
    for (const it of d.items) {
      const row = document.createElement('div');
      row.className = 'rule-row';
      row.innerHTML =
        `<div><b>#${it.source_file_id} ↔ #${it.target_file_id}</b> <span class="tag-chip">${API.esc(it.relation_type || '')}</span>` +
        `<div class="sub">${API.esc(it.file_name || '')} · 置信度 ${it.confidence ?? '-'} · ${API.fmtTime(it.create_time)}</div></div>`;
      const acts = document.createElement('div');
      acts.className = 'actions';
      const mk = (label, cls, fn) => {
        const b = document.createElement('button');
        b.className = 'btn small' + (cls ? ' ' + cls : '');
        b.textContent = label; b.onclick = fn;
        acts.appendChild(b);
      };
      mk('确认', 'primary', async () => { await API.post(`/api/relations/${it.id}/status?status=confirmed`); App.refresh(); });
      mk('忽略', '', async () => { await API.post(`/api/relations/${it.id}/status?status=dismissed`); App.refresh(); });
      mk('删除', 'danger', async () => { await API.del(`/api/relations/${it.id}`); App.refresh(); });
      row.appendChild(acts);
      panel.appendChild(row);
    }
    el.appendChild(panel);
  },
};

/* ═══════════ 文件事件 ═══════════ */
Views.events = {
  title: '文件事件',
  async render(el) {
    el.innerHTML = '';
    const d = await API.get('/api/events', { limit: 200 });
    el.innerHTML = '';
    const bar = document.createElement('div');
    bar.className = 'filter-bar';
    bar.innerHTML = `<button class="btn small danger" data-del>清理 90 天前事件</button>`;
    bar.querySelector('[data-del]').onclick = async () => {
      if (!await UI.confirm('删除 90 天前的文件事件记录？', { danger: true })) return;
      const r = await API.del('/api/events/older-than/90');
      UI.toast(`已删除 ${r.deleted} 条`, 'ok'); App.refresh();
    };
    el.appendChild(bar);
    const tbl = document.createElement('table');
    tbl.className = 'tbl';
    tbl.innerHTML = '<thead><tr><th>时间</th><th>类型</th><th>文件</th><th>状态</th></tr></thead>';
    const tbody = document.createElement('tbody');
    for (const it of (d.items || [])) {
      const tr = document.createElement('tr');
      const t1 = document.createElement('td'); t1.textContent = API.fmtTime(it.event_time); tr.appendChild(t1);
      const t2 = document.createElement('td'); t2.appendChild(UI.badge(it.event_type || '-')); tr.appendChild(t2);
      const t3 = document.createElement('td');
      t3.innerHTML = `<span class="name-cell">${API.esc(it.file_name || '')}</span><div class="path-cell">${API.esc(it.file_path || '')}</div>`;
      tr.appendChild(t3);
      const t4 = document.createElement('td'); t4.textContent = it.status || '-'; tr.appendChild(t4);
      tbody.appendChild(tr);
    }
    tbl.appendChild(tbody);
    if (!d.items.length) { el.innerHTML = ''; el.appendChild(UI.empty('暂无文件事件')); return; }
    el.appendChild(tbl);
  },
};

/* ═══════════ 索引健康 ═══════════ */
Views.health = {
  title: '索引健康',
  async render(el) {
    el.innerHTML = '';
    el.appendChild(UI.spin());
    const report = await API.get('/api/health/index');
    el.innerHTML = '';
    const panel = document.createElement('div');
    panel.className = 'panel';
    const hh = document.createElement('div');
    hh.className = 'panel-title';
    const h = document.createElement('h3');
    h.textContent = '索引健康报告';
    hh.appendChild(h);
    const repair = document.createElement('button');
    repair.className = 'btn small danger'; repair.textContent = '执行修复';
    repair.onclick = async () => {
      if (!await UI.confirm('修复将删除磁盘上已不存在的记录，确定执行？', { danger: true })) return;
      const r = await API.post('/api/health/index/repair?confirm=true');
      UI.toast(JSON.stringify(r), 'ok');
      App.refresh();
    };
    hh.appendChild(repair);
    panel.appendChild(hh);
    const pre = document.createElement('pre');
    pre.className = 'code-pre';
    pre.textContent = JSON.stringify(report, null, 2);
    panel.appendChild(pre);
    el.appendChild(panel);
  },
};

/* ═══════════ AI 助手（多轮会话 + 上下文面板，对齐桌面端） ═══════════ */

/* 会话本地持久化（浏览器 localStorage） */
const AIChat = {
  KEY: 'sfm_ai_sessions',

  load() {
    try {
      const raw = localStorage.getItem(this.KEY);
      if (raw) {
        const d = JSON.parse(raw);
        if (d && Array.isArray(d.sessions)) return d;
      }
    } catch (_) { /* 损坏数据回退为空 */ }
    return { currentId: null, sessions: [] };
  },

  save(d) {
    try { localStorage.setItem(this.KEY, JSON.stringify(d)); } catch (_) { /* 容量超限忽略 */ }
  },

  newSession(d) {
    const s = { id: 's' + Date.now(), title: '新会话', ts: Date.now(), messages: [] };
    d.sessions.unshift(s);
    d.currentId = s.id;
    return s;
  },

  current(d) {
    return d.sessions.find(s => s.id === d.currentId) || null;
  },
};

Views.ai = {
  title: 'AI 助手',
  async render(el) {
    el.innerHTML = '';
    const data = AIChat.load();
    if (!data.sessions.length) AIChat.newSession(data);
    let cur = AIChat.current(data) || AIChat.newSession(data);
    const status = await API.get('/api/ai/status').catch(() => ({ enabled: false }));

    const page = document.createElement('div');
    page.className = 'ai-page';

    /* ── 主区：会话栏 + 消息流 + 输入栏 ── */
    const main = document.createElement('div');
    main.className = 'ai-main';

    const bar = document.createElement('div');
    bar.className = 'ai-bar';
    const sel = document.createElement('select');
    sel.className = 'ai-session-sel';
    for (const s of data.sessions) {
      const o = document.createElement('option');
      o.value = s.id;
      o.textContent = `${s.title} · ${new Date(s.ts).toLocaleDateString()}`;
      sel.appendChild(o);
    }
    sel.value = cur.id;
    const nw = document.createElement('button');
    nw.className = 'btn small primary';
    nw.textContent = '+ 新建会话';
    bar.append(sel, nw);
    main.appendChild(bar);

    const msgs = document.createElement('div');
    msgs.className = 'ai-msgs';
    main.appendChild(msgs);

    const inputBar = document.createElement('div');
    inputBar.className = 'ai-input';
    const ta = document.createElement('textarea');
    ta.rows = 1;
    ta.placeholder = '输入文件操作指令，Enter 发送 · Shift+Enter 换行…';
    const send = document.createElement('button');
    send.className = 'btn primary';
    send.textContent = '发送';
    inputBar.append(ta, send);
    main.appendChild(inputBar);
    page.appendChild(main);

    /* ── 右侧上下文面板 ── */
    const side = document.createElement('aside');
    side.className = 'ai-side';
    side.innerHTML = `
      <div class="ai-side-block">
        <h4>AI 状态</h4>
        <p class="dim" id="ai-status-text"></p>
      </div>
      <div class="ai-side-block">
        <h4>快捷指令</h4>
        <div class="ai-quick"></div>
      </div>
      <div class="ai-side-block">
        <h4>历史会话</h4>
        <div class="ai-hist"></div>
      </div>`;
    page.appendChild(side);
    el.appendChild(page);

    side.querySelector('#ai-status-text').innerHTML = status.enabled
      ? `已启用 · 后端 <b>${API.esc(status.backend || '')}</b>`
        + (status.model ? ' · 模型 ' + API.esc(status.model) : '')
      : '未启用（未配置后端模型）';

    const quick = side.querySelector('.ai-quick');
    for (const q of ['找出最近一周修改的 PDF 文件', '查找重复文件', '整理下载目录',
      '找出占用空间最大的文件', '列出图片类文件']) {
      const b = document.createElement('button');
      b.className = 'ai-quick-btn';
      b.textContent = q;
      b.onclick = () => { ta.value = q; ta.focus(); };
      quick.appendChild(b);
    }

    const hist = side.querySelector('.ai-hist');
    const renderHist = () => {
      hist.innerHTML = '';
      if (!data.sessions.length) { hist.appendChild(UI.empty('暂无会话')); return; }
      for (const s of data.sessions) {
        const b = document.createElement('button');
        b.className = 'ai-hist-item' + (s.id === data.currentId ? ' active' : '');
        b.innerHTML = `<span>${API.esc(s.title)}</span>`
          + `<span class="dim">${new Date(s.ts).toLocaleDateString()}</span>`;
        b.onclick = () => {
          data.currentId = s.id;
          AIChat.save(data);
          App.refresh();
        };
        hist.appendChild(b);
      }
    };
    renderHist();

    /* 消息气泡 */
    const bubble = (role, text, meta) => {
      const b = document.createElement('div');
      b.className = 'ai-bubble ' + role;
      const t = document.createElement('div');
      t.className = 'ai-text';
      t.textContent = text;
      b.appendChild(t);
      if (meta) b.appendChild(meta);
      msgs.appendChild(b);
      msgs.scrollTop = msgs.scrollHeight;
      return b;
    };

    const renderMsgs = () => {
      msgs.innerHTML = '';
      if (!cur.messages.length) {
        const w = document.createElement('div');
        w.className = 'ai-welcome';
        w.innerHTML = '<p>你好，我是文件管家 AI 助手。用自然语言描述你想做的操作，例如：</p>'
          + '<ul><li>找出最近一周修改的 PDF 文件</li>'
          + '<li>查找重复文件并说明可释放空间</li>'
          + '<li>整理下载目录</li></ul>';
        msgs.appendChild(w);
        return;
      }
      for (const m of cur.messages) {
        if (m.role === 'user') { bubble('user', m.text); continue; }
        const meta = document.createElement('div');
        meta.className = 'ai-meta';
        if (m.matches !== undefined) {
          const tag = document.createElement('span');
          tag.className = 'badge blue';
          tag.textContent = `匹配 ${m.matches} 个文件`;
          meta.appendChild(tag);
        }
        if (m.query) {
          const go = document.createElement('button');
          go.className = 'btn small';
          go.textContent = '查看结果 →';
          go.onclick = () => App.nav('files', { qs: { name: m.query } });
          meta.appendChild(go);
        }
        bubble('assistant', m.text, meta);
      }
    };
    renderMsgs();

    sel.onchange = () => {
      data.currentId = sel.value;
      AIChat.save(data);
      App.refresh();
    };
    nw.onclick = () => {
      AIChat.newSession(data);
      AIChat.save(data);
      App.refresh();
    };

    /* 发送：优先走 SSE 流式（逐字输出），失败时降级为整段返回 */
    const ask = async () => {
      const msg = ta.value.trim();
      if (!msg) return;
      ta.value = '';
      if (!cur.messages.length) cur.title = msg.slice(0, 18);
      cur.messages.push({ role: 'user', text: msg, ts: Date.now() });
      AIChat.save(data);
      renderHist();
      renderMsgs();

      const bub = document.createElement('div');
      bub.className = 'ai-bubble assistant';
      const t = document.createElement('div');
      t.className = 'ai-text';
      t.textContent = '思考中…';
      bub.appendChild(t);
      msgs.appendChild(bub);
      msgs.scrollTop = msgs.scrollHeight;

      let text = '';
      let matches;
      let failed = '';
      try {
        const res = await fetch('/api/ai/chat/stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-API-Key': API.key() },
          body: JSON.stringify({ message: msg }),
        });
        if (!res.ok) {
          let detail = 'HTTP ' + res.status;
          try { const j = await res.json(); detail = j.detail || detail; } catch (_) { /* 非 JSON */ }
          throw new Error(detail);
        }
        const reader = res.body.getReader();
        const dec = new TextDecoder();
        let buf = '';
        let started = false;
        for (;;) {
          const rd = await reader.read();
          if (rd.done) break;
          buf += dec.decode(rd.value, { stream: true });
          let idx;
          while ((idx = buf.indexOf('\n\n')) >= 0) {
            const raw = buf.slice(0, idx).trim();
            buf = buf.slice(idx + 2);
            if (!raw.startsWith('data:')) continue;
            let evt;
            try { evt = JSON.parse(raw.slice(5).trim()); } catch (_) { continue; }
            if (evt.type === 'meta') {
              matches = evt.matches;
            } else if (evt.type === 'delta') {
              if (!started) { t.textContent = ''; started = true; }
              text += evt.text;
              t.textContent = text;
              msgs.scrollTop = msgs.scrollHeight;
            } else if (evt.type === 'error') {
              failed = evt.message || 'AI 出错';
            }
          }
        }
      } catch (e) {
        failed = e.message || '请求失败';
      }

      bub.remove();
      if (!text && failed) {
        cur.messages.push({
          role: 'assistant', text: '出错了：' + failed, ts: Date.now(),
        });
      } else {
        cur.messages.push({
          role: 'assistant',
          text: (text || '（无回答）') + (failed ? `\n\n（中断：${failed}）` : ''),
          matches,
          query: msg,
          ts: Date.now(),
        });
      }
      AIChat.save(data);
      renderMsgs();
    };
    send.onclick = ask;
    ta.onkeydown = (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask(); }
    };
    ta.focus();
  },
};

/* ═══════════ 设置 ═══════════ */
/* ── AI 模型设置面板（对齐桌面端 AiSettingsDialog 的核心能力） ── */
function aiSettingsPanel(providers, templates, err) {
  const panel = document.createElement('div');
  panel.className = 'panel';
  const hh = document.createElement('div');
  hh.className = 'panel-title';
  hh.innerHTML = '<h3>AI 模型设置</h3>';
  const addBtn = document.createElement('button');
  addBtn.className = 'btn small';
  addBtn.textContent = '+ 添加提供商';
  addBtn.onclick = () => aiAddProvider(templates);
  hh.appendChild(addBtn);
  panel.appendChild(hh);

  const hint = document.createElement('p');
  hint.className = 'sub';
  hint.style.marginBottom = '10px';
  hint.textContent = '配置保存在服务器项目根的 ai_models.json；保存后 AI 文件洞察与 AI 助手立即生效。';
  panel.appendChild(hint);

  if (err) {
    panel.appendChild(UI.empty(err + '（需要先在下方填入有效的 API Key）'));
    return panel;
  }
  if (!providers.length) {
    panel.appendChild(UI.empty('尚未配置 AI 提供商，点击右上角「+ 添加提供商」'));
    return panel;
  }

  for (const p of providers) {
    const row = document.createElement('div');
    row.className = 'rule-row';
    const left = document.createElement('div');
    left.innerHTML = `<div><b>${API.esc(p.name || p.provider_id)}</b> `
      + (p.active ? '<span class="badge green">当前使用</span> ' : '')
      + (p.has_key ? '' : '<span class="badge amber">未配置 Key</span>')
      + `</div>`
      + `<div class="path-cell">${API.esc(p.base_url)}</div>`
      + `<div class="sub">模型 ${API.esc(p.model || '-')} · Key ${API.esc(p.api_key || '未配置')}`
      + ` · 超时 ${p.timeout || '-'}s</div>`;
    const acts = document.createElement('div');
    acts.className = 'row-actions';
    const pid = encodeURIComponent(p.provider_id);

    if (!p.active) {
      const b = document.createElement('button');
      b.className = 'btn small'; b.textContent = '设为当前';
      b.onclick = async () => {
        try {
          await API.post(`/api/ai/providers/${pid}/activate`);
          UI.toast('已切换为当前模型', 'ok');
          App.refresh();
        } catch (e) { UI.toast(e.message || '切换失败', 'err'); }
      };
      acts.appendChild(b);
    }

    const t = document.createElement('button');
    t.className = 'btn small'; t.textContent = '测试';
    t.onclick = async () => {
      t.disabled = true; t.textContent = '测试中…';
      try {
        const r = await API.post(`/api/ai/providers/${pid}/test`);
        UI.toast(r.success ? `连接正常 · ${r.model} · ${r.latency_ms}ms`
          : '连接失败：' + r.error, r.success ? 'ok' : 'err');
      } catch (e) { UI.toast(e.message || '测试失败', 'err'); }
      t.disabled = false; t.textContent = '测试';
    };
    acts.appendChild(t);

    const eb = document.createElement('button');
    eb.className = 'btn small'; eb.textContent = '编辑';
    eb.onclick = () => aiEditProvider(p, false);
    acts.appendChild(eb);

    const db = document.createElement('button');
    db.className = 'btn small danger'; db.textContent = '删除';
    db.onclick = async () => {
      if (!await UI.confirm(`删除提供商「${p.name || p.provider_id}」？`, { danger: true })) return;
      try {
        await API.del(`/api/ai/providers/${pid}`);
        UI.toast('已删除', 'ok');
        App.refresh();
      } catch (e) { UI.toast(e.message || '删除失败', 'err'); }
    };
    acts.appendChild(db);

    row.append(left, acts);
    panel.appendChild(row);
  }
  return panel;
}

async function aiAddProvider(templates) {
  const opts = (templates || []).map(t => ({
    v: t.provider_id, l: `${t.name}（${t.base_url}）`,
  }));
  opts.push({ v: '__custom__', l: '自定义（手动填写）' });
  const sel = await UI.formModal({
    title: '添加 AI 提供商',
    fields: [{ name: 'tpl', label: '选择模板', type: 'select', full: true, options: opts }],
    submitText: '下一步',
  });
  if (!sel) return;
  const t = (templates || []).find(x => x.provider_id === sel.tpl);
  aiEditProvider(t ? {
    provider_id: t.provider_id, name: t.name, base_url: t.base_url,
    model: t.default_model || '', models: t.models || '',
    timeout: t.timeout || 60, api_key: '', has_key: false,
  } : {
    provider_id: '', name: '', base_url: '', model: '', models: '',
    timeout: 60, api_key: '', has_key: false,
  }, true);
}

async function aiEditProvider(p, isNew) {
  const v = await UI.formModal({
    title: isNew ? '添加 AI 提供商' : `编辑提供商：${p.name || p.provider_id}`,
    wide: true,
    submitText: '保存',
    fields: [
      { name: 'provider_id', label: 'ID（唯一标识，如 qwen）', type: 'text', value: p.provider_id, required: true, full: true },
      { name: 'name', label: '显示名称', type: 'text', value: p.name, required: true },
      { name: 'base_url', label: 'API 端点', type: 'text', value: p.base_url, required: true, full: true },
      { name: 'api_key', label: p.has_key ? 'API Key（留空 = 保持不变）' : 'API Key', type: 'password', value: '', full: true },
      { name: 'model', label: '当前使用模型', type: 'text', value: p.model, required: true },
      { name: 'models', label: '可选模型（逗号分隔）', type: 'text', value: p.models, full: true },
      { name: 'timeout', label: '超时（秒）', type: 'number', value: p.timeout || 60 },
    ],
  });
  if (!v) return;
  try {
    await API.post('/api/ai/providers', {
      provider_id: String(v.provider_id || '').trim(),
      name: String(v.name || '').trim(),
      base_url: String(v.base_url || '').trim(),
      api_key: String(v.api_key || '').trim(),
      model: String(v.model || '').trim(),
      models: String(v.models || '').trim(),
      timeout: parseFloat(v.timeout) || 60,
    });
    UI.toast('已保存', 'ok');
    App.refresh();
  } catch (e) {
    UI.toast('保存失败：' + (e.message || ''), 'err');
  }
}

Views.settings = {
  title: '设置',
  async render(el) {
    el.innerHTML = '';

    /* API Key：纯本地操作，不依赖服务端，任何情况下都可输入 */
    const keyPanel = document.createElement('div');
    keyPanel.className = 'panel';
    keyPanel.innerHTML = `<div class="panel-title"><h3>API Key（浏览器本地保存）</h3></div>`;
    const keyRow = document.createElement('div');
    keyRow.className = 'filter-bar';
    const keyInp = document.createElement('input');
    keyInp.type = 'password';
    keyInp.placeholder = '输入服务端 SFM_API_KEY';
    keyInp.style.flex = '1';
    keyInp.value = API.key() || '';
    const saveKey = document.createElement('button');
    saveKey.className = 'btn primary small'; saveKey.textContent = '保存并测试';
    const clearKey = document.createElement('button');
    clearKey.className = 'btn small'; clearKey.textContent = '清除';
    keyRow.append(keyInp, saveKey, clearKey);
    keyPanel.appendChild(keyRow);
    const keyHint = document.createElement('p');
    keyHint.className = 'dim';
    keyHint.style.cssText = 'margin-top:8px;color:var(--text-dim);font-size:12.5px';
    keyHint.textContent = '服务端 Key 见 /home/admin/sfm/api_key.txt（或环境变量 SFM_API_KEY）。若服务端未设 Key，可留空。';
    keyPanel.appendChild(keyHint);
    const reloadSettings = () => App.refresh();
    saveKey.onclick = async () => {
      API.setKey(keyInp.value.trim());
      const st = await API.checkKey();
      UI.toast(st === 'ok' ? 'API Key 验证通过' : (st === 'no-key' ? '服务端未要求 Key' : 'Key 无效：' + st), st === 'ok' ? 'ok' : 'err');
      App.setKeyState(st);
      reloadSettings();
    };
    clearKey.onclick = () => { API.setKey(''); keyInp.value = ''; UI.toast('已清除', 'ok'); reloadSettings(); };
    el.appendChild(keyPanel);

    /* AI 模型设置：独立加载，失败只降级提示 */
    let aiProviders = [];
    let aiTemplates = [];
    let aiErr = '';
    try {
      const r = await API.get('/api/ai/providers');
      aiProviders = r.providers || [];
      aiTemplates = r.templates || [];
    } catch (e) {
      aiErr = e && e.message ? e.message : 'AI 配置加载失败';
    }
    el.appendChild(aiSettingsPanel(aiProviders, aiTemplates, aiErr));

    /* 设置项：独立加载，401/失败只降级提示，不阻断 Key 面板 */
    let items = [];
    let loadErr = '';
    try {
      const d = await API.get('/api/settings');
      items = d.items || [];
    } catch (e) {
      loadErr = e && e.message ? e.message : '设置项加载失败';
    }
    const panel = document.createElement('div');
    panel.className = 'panel';
    const hh = document.createElement('div');
    hh.className = 'panel-title';
    const h = document.createElement('h3');
    h.textContent = `系统设置（${items.length}）`;
    hh.appendChild(h);
    const add = document.createElement('button');
    add.className = 'btn small'; add.textContent = '+ 新增';
    add.onclick = async () => {
      const v = await UI.formModal({ title: '新增设置', wide: true, fields: [
        { name: 'key', label: '键', type: 'text', required: true, full: true },
        { name: 'value', label: '值', type: 'text', required: true, full: true },
        { name: 'setting_type', label: '类型', type: 'select', value: 'string',
          options: ['string', 'int', 'bool', 'json', 'float'].map(x => ({ v: x, l: x })) },
        { name: 'description', label: '描述', type: 'text', full: true },
      ] });
      if (!v) return;
      await API.post(`/api/settings?key=${encodeURIComponent(v.key.trim())}&value=${encodeURIComponent(v.value)}&setting_type=${v.setting_type}&description=${encodeURIComponent(v.description.trim())}`);
      UI.toast('已保存', 'ok'); App.refresh();
    };
    hh.appendChild(add);
    panel.appendChild(hh);
    if (loadErr) panel.appendChild(UI.empty(loadErr + '（输入上方 API Key 后保存即可查看）'));
    else if (!items.length) panel.appendChild(UI.empty('暂无设置'));
    for (const it of items) {
      const row = document.createElement('div');
      row.className = 'rule-row';
      row.innerHTML =
        `<div><b>${API.esc(it.setting_key)}</b> <span class="tag-chip">${API.esc(it.setting_type || '')}</span>` +
        `<div class="path-cell">${API.esc(it.setting_value)}</div>` +
        (it.description ? `<div class="sub">${API.esc(it.description)}</div>` : '') + `</div>`;
      const acts = document.createElement('div');
      const b = document.createElement('button');
      b.className = 'btn small danger'; b.textContent = '删除';
      b.onclick = async () => {
        if (!await UI.confirm(`删除设置「${it.setting_key}」？`, { danger: true })) return;
        await API.del('/api/settings/' + encodeURIComponent(it.setting_key));
        App.refresh();
      };
      acts.appendChild(b);
      row.appendChild(acts);
      panel.appendChild(row);
    }
    el.appendChild(panel);
  },
};
