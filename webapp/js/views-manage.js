/* 去重 / 标签 / 分类 */
'use strict';

/* ═══════════ 重复文件 ═══════════ */
Views.duplicates = {
  title: '重复文件',
  state: { page: 0, pageSize: 10 },
  async render(el) {
    el.innerHTML = '';
    el.appendChild(UI.spin());
    const d = await API.get('/api/duplicates', { page: this.state.page, page_size: this.state.pageSize });
    el.innerHTML = '';
    if (!d.items.length) { el.appendChild(UI.empty('没有重复文件组')); return; }
    const head = document.createElement('div');
    head.style.cssText = 'color:var(--text-dim);font-size:12.5px;margin-bottom:12px';
    head.textContent = `共 ${d.total} 组重复 · 可回收 ${API.fmtBytes(d.wasted_size)}`;
    el.appendChild(head);
    const self = this;
    for (const g of d.items) {
      const panel = document.createElement('div');
      panel.className = 'panel';
      const top = document.createElement('div');
      top.className = 'panel-title';
      const h = document.createElement('h3');
      h.innerHTML = `重复组 #${g.group_id} · <span style="color:var(--accent)">${g.file_count} 个文件</span>`;
      top.appendChild(h);
      const acts = document.createElement('div');
      acts.className = 'actions';
      const btnView = document.createElement('button');
      btnView.className = 'btn small';
      btnView.textContent = '查看并清理';
      btnView.onclick = () => openDupGroup(g, () => App.refresh());
      acts.appendChild(btnView);
      top.appendChild(acts);
      panel.appendChild(top);
      const info = document.createElement('div');
      info.style.cssText = 'font-size:12.5px;color:var(--text-dim);display:flex;gap:18px;flex-wrap:wrap';
      info.innerHTML =
        `<span>单份大小：<b style="color:var(--text)">${API.fmtBytes(g.single_size || g.total_size)}</b></span>` +
        `<span>组内总量：<b style="color:var(--text)">${API.fmtBytes(g.total_size)}</b></span>` +
        `<span>可回收：<b style="color:var(--danger)">${API.fmtBytes(g.wasted_size)}</b></span>`;
      panel.appendChild(info);
      el.appendChild(panel);
    }
    el.appendChild(UI.pager({
      page: d.page, pageSize: d.page_size, total: d.total,
      onChange: (p) => { self.state.page = p; self.render(el); },
    }));
  },
};

async function openDupGroup(g, onDone) {
  const modal = UI.modal({ title: `重复组 #${g.group_id}`, body: UI.spin(), wide: true });
  const [d, suggest] = await Promise.all([
    API.get('/api/duplicates/' + g.group_id),
    API.get('/api/duplicates/' + g.group_id + '/suggest?strategy=keep_newest').catch(() => null),
  ]);
  const body = modal.body;
  body.innerHTML = '';
  const hint = document.createElement('p');
  hint.style.cssText = 'color:var(--text-dim);font-size:12.5px;margin-bottom:10px';
  hint.textContent = suggest
    ? `建议保留「${(d.files.find(f => f.id === suggest.keep_file_id) || {}).file_name || '#' + suggest.keep_file_id}」，可回收 ${API.fmtBytes(suggest.remove_total_size)}`
    : '已按「保留最新」策略给出建议。';
  body.appendChild(hint);

  const keepRadios = {};
  const rmChecks = {};
  const table = document.createElement('table');
  table.className = 'tbl';
  table.innerHTML = '<thead><tr><th>保留</th><th>删除</th><th>文件名</th><th>大小</th><th>修改时间</th></tr></thead>';
  const tbody = document.createElement('tbody');
  for (const f of d.files) {
    const tr = document.createElement('tr');
    const tdKeep = document.createElement('td');
    const rk = document.createElement('input');
    rk.type = 'radio'; rk.name = 'keep'; rk.value = f.id;
    rk.checked = suggest && f.id === suggest.keep_file_id;
    keepRadios[f.id] = rk;
    tdKeep.appendChild(rk);
    const tdRm = document.createElement('td');
    const ck = document.createElement('input');
    ck.type = 'checkbox';
    ck.checked = suggest && (suggest.remove_file_ids || []).includes(f.id);
    rmChecks[f.id] = ck;
    tdRm.appendChild(ck);
    tr.append(tdKeep, tdRm);
    const tdName = document.createElement('td');
    tdName.innerHTML = `<span class="name-cell">${API.esc(f.file_name)}</span><div class="path-cell">${API.esc(f.file_path)}</div>`;
    tr.appendChild(tdName);
    const tdSize = document.createElement('td');
    tdSize.className = 'num'; tdSize.textContent = API.fmtBytes(f.file_size);
    tr.appendChild(tdSize);
    const tdTime = document.createElement('td');
    tdTime.textContent = API.fmtTime(f.modify_time);
    tr.appendChild(tdTime);
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  body.appendChild(table);

  const foot = document.createElement('div');
  foot.className = 'modal-foot';
  const cancel = document.createElement('button');
  cancel.className = 'btn'; cancel.textContent = '取消';
  cancel.onclick = () => UI.close(modal);
  const clean = document.createElement('button');
  clean.className = 'btn danger'; clean.textContent = '清理选中副本';
  clean.onclick = async () => {
    const keepId = Number(Object.values(keepRadios).find(r => r.checked)?.value);
    const removeIds = Object.entries(rmChecks).filter(([, c]) => c.checked).map(([id]) => Number(id));
    if (!keepId || !removeIds.length) { UI.toast('请选择保留文件并勾选要删除的副本', 'err'); return; }
    if (!await UI.confirm(`将 ${removeIds.length} 个副本移入回收区？`, { danger: true })) return;
    const r = await API.post('/api/duplicates/clean', {
      group_id: g.group_id, keep_file_id: keepId, remove_file_ids: removeIds, confirm: true,
    });
    UI.toast(r.message || `已清理 ${r.removed} 个文件`, 'ok');
    UI.close(modal);
    onDone();
  };
  foot.append(cancel, clean);
  modal.modal.appendChild(foot);
}

/* ═══════════ 标签管理 ═══════════ */
Views.tags = {
  title: '标签管理',
  state: { current: null, page: 0, pageSize: 100 },
  async render(el) {
    el.innerHTML = '';
    const self = this;
    const d = await API.get('/api/tags/full');
    el.innerHTML = '';
    const wrap = document.createElement('div');
    wrap.className = 'grid';
    wrap.style.gridTemplateColumns = '280px 1fr';
    wrap.style.alignItems = 'start';
    el.appendChild(wrap);

    const left = document.createElement('div');
    left.className = 'panel';
    const lh = document.createElement('div');
    lh.className = 'panel-title';
    const h = document.createElement('h3');
    h.textContent = `标签（${d.total}）`;
    lh.appendChild(h);
    const add = document.createElement('button');
    add.className = 'btn small'; add.textContent = '+ 新建';
    add.onclick = async () => {
      const v = await UI.formModal({ title: '新建标签',
        fields: [{ name: 'tag', label: '标签名', type: 'text', required: true, full: true }] });
      if (!v) return;
      await API.post('/api/tags?tag=' + encodeURIComponent(v.tag.trim()));
      UI.toast('已创建', 'ok'); App.refresh();
    };
    lh.appendChild(add);
    left.appendChild(lh);
    const list = document.createElement('div');
    list.style.cssText = 'display:flex;flex-direction:column;gap:4px';
    for (const t of d.tags) {
      const item = document.createElement('div');
      item.className = 'nav-btn';
      if (this.state.current === t.tag_name) item.classList.add('active');
      const cnt = document.createElement('span');
      cnt.className = 'num'; cnt.textContent = t.file_count;
      const nm = document.createElement('span');
      nm.style.cssText = 'flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap';
      nm.textContent = t.tag_name;
      item.append(nm, cnt);
      item.onclick = () => { self.state.current = t.tag_name; self.state.page = 0; self.render(el); };
      list.appendChild(item);
    }
    if (!d.tags.length) left.appendChild(UI.empty('暂无标签'));
    left.appendChild(list);
    wrap.appendChild(left);

    const right = document.createElement('div');
    right.className = 'panel';
    if (!this.state.current) { right.appendChild(UI.empty('点击左侧标签查看文件')); wrap.appendChild(right); return; }
    const cur = this.state.current;
    const rh = document.createElement('div');
    rh.className = 'panel-title';
    const rh3 = document.createElement('h3');
    rh3.textContent = `「${cur}」的文件`;
    rh.appendChild(rh3);
    const acts = document.createElement('div');
    acts.className = 'actions';
    const mkAct = (label, fn) => {
      const b = document.createElement('button');
      b.className = 'btn small'; b.textContent = label; b.onclick = fn;
      acts.appendChild(b);
    };
    mkAct('重命名', async () => {
      const v = await UI.formModal({ title: '重命名标签',
        fields: [{ name: 'new_name', label: '新名称', type: 'text', value: cur, required: true, full: true }] });
      if (!v) return;
      await API.post(`/api/tags/rename?old_name=${encodeURIComponent(cur)}&new_name=${encodeURIComponent(v.new_name.trim())}`);
      self.state.current = v.new_name.trim(); UI.toast('已重命名', 'ok'); App.refresh();
    });
    mkAct('合并到…', async () => {
      const v = await UI.formModal({ title: '合并标签',
        fields: [{ name: 'target', label: '目标标签', type: 'text', required: true, full: true }] });
      if (!v) return;
      const r = await API.post(`/api/tags/merge?source=${encodeURIComponent(cur)}&target=${encodeURIComponent(v.target.trim())}`);
      self.state.current = null; UI.toast(`已合并 ${r.moved} 个文件`, 'ok'); App.refresh();
    });
    mkAct('设父标签', async () => {
      const v = await UI.formModal({ title: '设置父标签',
        fields: [{ name: 'parent', label: '父标签（留空清除）', type: 'text', full: true }] });
      if (!v) return;
      await API.post(`/api/tags/${encodeURIComponent(cur)}/parent?parent=${encodeURIComponent(v.parent.trim())}`);
      UI.toast('已设置', 'ok'); App.refresh();
    });
    mkAct('加别名', async () => {
      const v = await UI.formModal({ title: '添加别名',
        fields: [{ name: 'alias', label: '别名', type: 'text', required: true, full: true }] });
      if (!v) return;
      await API.post(`/api/tags/${encodeURIComponent(cur)}/aliases?alias=${encodeURIComponent(v.alias.trim())}`);
      UI.toast('已添加别名', 'ok'); App.refresh();
    });
    mkAct('删除', async () => {
      if (!await UI.confirm(`删除标签「${cur}」？关联关系将一并移除。`, { danger: true })) return;
      await API.del('/api/tags/' + encodeURIComponent(cur));
      self.state.current = null; UI.toast('已删除', 'ok'); App.refresh();
    });
    rh.appendChild(acts);
    right.appendChild(rh);

    const fd = await API.get('/api/tags/' + encodeURIComponent(cur) + '/files',
      { page: this.state.page, page_size: this.state.pageSize });
    if (!fd.items.length) right.appendChild(UI.empty('该标签下暂无文件'));
    else {
      const ft = buildFileTable(fd.items, {}, {}, { actions: [{ label: '详情', onClick: (f) => openFileDetail(f.id) }] });
      right.appendChild(ft.tbl);
      right.appendChild(UI.pager({
        page: fd.page, pageSize: fd.page_size, total: fd.total,
        onChange: (p) => { self.state.page = p; self.render(el); },
      }));
    }
    wrap.appendChild(right);
  },
};

/* ═══════════ 智能分类 ═══════════ */
Views.classification = {
  title: '智能分类',
  async render(el) {
    el.innerHTML = '';
    const d = await API.get('/api/classification');
    el.innerHTML = '';

    const head = document.createElement('div');
    head.className = 'panel';
    const hh = document.createElement('div');
    hh.className = 'panel-title';
    const h = document.createElement('h3');
    h.textContent = '分类规则';
    hh.appendChild(h);
    const applyAll = document.createElement('button');
    applyAll.className = 'btn small'; applyAll.textContent = '全部重新分类';
    applyAll.onclick = async (e) => {
      if (!await UI.confirm('对全部活跃文件重新分类（先清旧分类）？', { danger: true })) return;
      e.target.textContent = '分类中…'; e.target.disabled = true;
      try {
        const r = await API.post('/api/classification/apply-all');
        UI.toast(`完成：${r.total} 个文件，成功 ${r.classified}，失败 ${r.failed}`, 'ok');
        App.refresh();
      } finally { e.target.textContent = '全部重新分类'; e.target.disabled = false; }
    };
    hh.appendChild(applyAll);
    head.appendChild(hh);

    const rules = d.rules || [];
    if (!rules.length) head.appendChild(UI.empty('暂无规则'));
    for (const r of rules) {
      const row = document.createElement('div');
      row.className = 'rule-row';
      row.innerHTML =
        `<div><b>${API.esc(r.rule_name)}</b> <span class="tag-chip">${API.esc(r.rule_type)}:${API.esc(r.rule_pattern)}</span>` +
        `<div class="sub">→ ${API.esc(r.target_category)} · 优先级 ${r.priority ?? 0} · ${r.enabled ? '<span style="color:var(--green)">启用</span>' : '<span style="color:var(--text-dim)">停用</span>'}</div></div>`;
      const acts = document.createElement('div');
      acts.className = 'actions';
      const mk = (label, cls, fn) => {
        const b = document.createElement('button');
        b.className = 'btn small' + (cls ? ' ' + cls : '');
        b.textContent = label; b.onclick = fn;
        acts.appendChild(b);
      };
      mk('编辑', '', () => ruleDialog(r));
      mk(r.enabled ? '停用' : '启用', '', async () => {
        await API.post(`/api/classification/rules/${r.id}/toggle?enabled=${!r.enabled}`);
        App.refresh();
      });
      mk('删除', 'danger', async () => {
        if (!await UI.confirm(`删除规则「${r.rule_name}」？`, { danger: true })) return;
        await API.del(`/api/classification/rules/${r.id}`);
        App.refresh();
      });
      row.appendChild(acts);
      head.appendChild(row);
    }
    const addRule = document.createElement('div');
    addRule.style.marginTop = '8px';
    const ab = document.createElement('button');
    ab.className = 'btn small'; ab.textContent = '+ 新建规则';
    ab.onclick = () => ruleDialog(null);
    addRule.appendChild(ab);
    head.appendChild(addRule);
    el.appendChild(head);

    const types = d.types || {};
    if (Object.keys(types).length) {
      const chips = document.createElement('div');
      chips.className = 'panel';
      chips.innerHTML = `<div class="panel-title"><h3>分类分布</h3></div>`;
      for (const [type, values] of Object.entries(types)) {
        const row = document.createElement('div');
        row.style.cssText = 'display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:8px';
        const lbl = document.createElement('span');
        lbl.style.cssText = 'min-width:90px;color:var(--text-dim);font-size:12.5px';
        lbl.textContent = type;
        row.appendChild(lbl);
        for (const v of values) {
          const chip = document.createElement('span');
          chip.className = 'tag-chip';
          chip.style.cssText = 'cursor:pointer;background:rgba(167,139,250,.15);color:var(--purple)';
          chip.textContent = `${v.value} · ${v.count}`;
          chip.title = `查看「${v.value}」下的文件`;
          chip.onclick = () => openClassFiles(type, v.value);
          row.appendChild(chip);
        }
        chips.appendChild(row);
      }
      el.appendChild(chips);
    }

    function ruleDialog(r) {
      const isEdit = !!r;
      UI.formModal({
        title: isEdit ? '编辑规则' : '新建规则', wide: true,
        fields: [
          { name: 'rule_name', label: '规则名', type: 'text', value: r?.rule_name || '', required: true, full: true },
          { name: 'rule_type', label: '规则类型', type: 'select', value: r?.rule_type || 'filename',
            options: ['filename', 'extension', 'path', 'regex'].map(v => ({ v, l: v })) },
          { name: 'rule_pattern', label: '匹配模式', type: 'text', value: r?.rule_pattern || '', required: true, full: true },
          { name: 'target_category', label: '目标分类（如 category:工作）', type: 'text', value: r?.target_category || '', required: true, full: true },
          { name: 'priority', label: '优先级（数字）', type: 'number', value: r?.priority ?? 0 },
        ],
        submitText: '保存',
      }).then(async (v) => {
        if (!v) return;
        const qs = `rule_name=${encodeURIComponent(v.rule_name.trim())}&rule_type=${encodeURIComponent(v.rule_type)}&rule_pattern=${encodeURIComponent(v.rule_pattern.trim())}&target_category=${encodeURIComponent(v.target_category.trim())}&priority=${Number(v.priority) || 0}`;
        if (isEdit) await API.put(`/api/classification/rules/${r.id}?${qs}`);
        else await API.post(`/api/classification/rules?${qs}`);
        UI.toast('已保存', 'ok'); App.refresh();
      });
    }

    function openClassFiles(type, value) {
      const modal = UI.modal({ title: `分类「${type}:${value}」`, body: UI.spin(), wide: true });
      API.get('/api/classification/' + encodeURIComponent(type) + '/' + encodeURIComponent(value) + '/files')
        .then((d2) => {
          modal.body.innerHTML = '';
          if (!d2.items.length) { modal.body.appendChild(UI.empty('该分类下暂无文件')); return; }
          const ft = buildFileTable(d2.items, d2.tags || {}, d2.classifications || {}, {
            actions: [{ label: '详情', onClick: (f) => openFileDetail(f.id) }],
          });
          modal.body.appendChild(ft.tbl);
        })
        .catch((e) => { modal.body.innerHTML = `<div class="empty">${API.esc(e.message)}</div>`; });
    }
  },
};
