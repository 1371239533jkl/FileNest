/* 仪表盘视图 —— 布局对齐桌面端 dashboard_tab：
   统计卡 + 待处理 + AI 洞察 + 类型饼图 + 最近活动 + 增长趋势 + 快捷操作 + 目录排行 */
'use strict';

function _fmtInt(n) {
  return (n === null || n === undefined) ? '-' : Number(n).toLocaleString('en-US');
}

Views.dashboard = {
  title: '仪表盘',
  async render(el) {
    el.innerHTML = '';
    el.appendChild(UI.spin());
    const d = await API.get('/api/dashboard');
    el.innerHTML = '';

    /* ── 1. 统计卡片 ── */
    const cards = document.createElement('div');
    cards.className = 'grid cards stat-colors';
    const mk = (label, val, sub) => {
      const c = document.createElement('div');
      c.className = 'card';
      c.innerHTML = `<h3>${API.esc(label)}</h3><div class="big">${API.esc(val)}</div>`
        + `<div class="sub">${API.esc(sub || '')}</div>`;
      return c;
    };
    cards.append(
      mk('总文件数', _fmtInt(d.active_count), `近 7 天索引 ${_fmtInt(d.recent_7d)} 个`),
      mk('已分类', _fmtInt(d.classified_count), `${(d.coverage || 0).toFixed(1)}% 覆盖率`),
      mk('标签数', _fmtInt(d.tag_count), `覆盖 ${_fmtInt(d.tag_hits)} 次`),
      mk('存储用量', API.fmtBytes(d.total_size), `重复占用约 ${API.fmtBytes(d.duplicate_wasted)}`),
    );
    el.appendChild(cards);

    /* ── 2. 待处理事项 ── */
    const pending = document.createElement('div');
    pending.className = 'panel';
    pending.innerHTML = `<div class="panel-title"><h3>待处理事项</h3></div>`;
    const chips = document.createElement('div');
    chips.className = 'pending-chips';
    const pendItems = [
      ['未分类', d.unclassified_count, 'classification'],
      ['未计算哈希', d.unhashed_count, 'duplicates'],
      ['重复组', d.duplicate_groups, 'duplicates'],
      ['回收区', d.deleted_count, 'recycle'],
    ];
    for (const [name, val, view] of pendItems) {
      const b = document.createElement('button');
      b.className = 'pending-chip';
      b.innerHTML = `<span class="pc-name">${API.esc(name)}</span><b>${_fmtInt(val)}</b>`;
      b.onclick = () => App.nav(view);
      chips.appendChild(b);
    }
    pending.appendChild(chips);
    el.appendChild(pending);

    /* ── 3. 中间行：AI 洞察 / 类型分布 / 最近活动 ── */
    const mid = document.createElement('div');
    mid.className = 'dash-mid';

    const insight = document.createElement('div');
    insight.className = 'panel';
    insight.innerHTML = `<div class="panel-title"><h3>✦ AI 文件洞察</h3></div>`
      + `<div class="sub" style="margin-bottom:10px">基于文件类型和使用模式的智能分析</div>`
      + `<div class="insight-text" id="insight-text">正在分析磁盘状况…</div>`;
    mid.appendChild(insight);
    const fp = [d.active_count, d.total_size, d.duplicate_groups, d.recent_7d,
      (d.type_stats || []).length].join('|');
    this._loadInsight(insight.querySelector('#insight-text'), fp);

    const piePanel = document.createElement('div');
    piePanel.className = 'panel';
    piePanel.innerHTML = `<div class="panel-title"><h3>类型分布</h3></div>`;
    const typeNames = d.type_names || {};
    const rows = (d.type_stats || []).map(t => ({
      label: typeNames[t.file_type] || t.file_type || '未知',
      value: t.count || 0,
      color: Charts.TYPE_COLORS[t.file_type],
    }));
    piePanel.appendChild(Charts.pie(rows));
    mid.appendChild(piePanel);

    const actPanel = document.createElement('div');
    actPanel.className = 'panel';
    actPanel.innerHTML = `<div class="panel-title"><h3>最近活动</h3></div>`;
    const acts = d.recent_activities || [];
    if (!acts.length) {
      actPanel.appendChild(UI.empty('暂无文件操作记录'));
    } else {
      const opNames = {
        rename: '重命名', move: '移动', delete: '删除', restore: '恢复',
        permanent_delete: '永久删除', scan: '扫描', classify: '分类', dedup: '去重',
        tag: '标签', cleanup: '清理',
      };
      const list = document.createElement('div');
      list.className = 'activity-list';
      for (const a of acts) {
        const ok = a.operation_status === 'completed';
        const li = document.createElement('div');
        li.className = 'activity-item';
        li.innerHTML = `<span class="dot ${ok ? 'on' : 'mid'}"></span>`
          + `<span class="at-name">${API.esc(opNames[a.operation_type] || a.operation_type || '操作')}</span>`
          + `<span class="at-time">${API.esc(String(a.operation_time || '').slice(5, 16))}</span>`;
        list.appendChild(li);
      }
      actPanel.appendChild(list);
    }
    mid.appendChild(actPanel);
    el.appendChild(mid);

    /* ── 4. 底部行：增长趋势 + 快捷操作 ── */
    const bottom = document.createElement('div');
    bottom.className = 'dash-bottom';

    const trendPanel = document.createElement('div');
    trendPanel.className = 'panel';
    trendPanel.innerHTML = `<div class="panel-title"><h3>文件增长趋势</h3></div>`;
    const months = (d.monthly_trend || []).slice().reverse();
    const labels = months.map(m => m.month || '');
    let cum = 0;
    const cumVals = [], newVals = [];
    for (const m of months) {
      cum += (m.count || 0);
      cumVals.push(cum);
      newVals.push(m.count || 0);
    }
    trendPanel.appendChild(Charts.line(labels, [
      { name: '累计文件数', values: cumVals, color: '#4f8cff' },
      { name: '每月新增', values: newVals, color: '#34d399' },
    ]));
    bottom.appendChild(trendPanel);

    const quick = document.createElement('div');
    quick.className = 'panel';
    quick.innerHTML = `<div class="panel-title"><h3>快捷操作</h3></div>`;
    const qa = document.createElement('div');
    qa.className = 'quick-actions';
    for (const [label, view] of [
      ['⟳ 开始新扫描', 'scan'],
      ['⧉ 查找重复文件', 'duplicates'],
      ['✦ AI 文件分析', 'ai'],
      ['✂ 清理建议', 'cleanup'],
      ['🏷 标签管理', 'tags'],
    ]) {
      const b = document.createElement('button');
      b.className = 'quick-btn';
      b.textContent = label;
      b.onclick = () => App.nav(view);
      qa.appendChild(b);
    }
    quick.appendChild(qa);
    bottom.appendChild(quick);
    el.appendChild(bottom);

    /* ── 5. 目录占用排行 ── */
    const dirPanel = document.createElement('div');
    dirPanel.className = 'panel';
    dirPanel.style.marginTop = '16px';
    dirPanel.innerHTML = `<div class="panel-title"><h3>目录占用排行（前 5）</h3></div>`;
    const tops = (d.top_directories || []).slice(0, 5);
    if (!tops.length) {
      dirPanel.appendChild(UI.empty('暂无目录统计'));
    } else {
      const maxSize = Math.max(1, ...tops.map(t => t.total_size || 0));
      for (const t of tops) {
        const row = document.createElement('div');
        row.className = 'hbar';
        const pct = Math.round((t.total_size || 0) / maxSize * 100);
        row.innerHTML = `<span class="lbl" title="${API.esc(t.dir_path)}">${API.esc(t.dir_path)}</span>`
          + `<span class="track"><i style="width:${pct}%;background:var(--accent)"></i></span>`
          + `<span class="val">${_fmtInt(t.file_count)} 个 · ${API.fmtBytes(t.total_size)}</span>`;
        dirPanel.appendChild(row);
      }
    }
    el.appendChild(dirPanel);
  },

  /* AI 洞察异步加载（不阻塞渲染；数据指纹未变时复用本地缓存，避免重复消耗 token） */
  async _loadInsight(node, fingerprint) {
    if (!node) return;
    const CACHE = 'sfm_ai_insight';
    try {
      const cached = JSON.parse(localStorage.getItem(CACHE) || 'null');
      if (cached && cached.fp === fingerprint && cached.text) {
        node.textContent = cached.text;
        return;
      }
    } catch (_) { /* 缓存损坏则忽略 */ }
    try {
      const r = await API.get('/api/ai/insights');
      if (!r || !r.enabled) {
        node.innerHTML = '<span class="dim">AI 未启用（未配置后端模型），可在设置中检查模型配置。</span>';
        return;
      }
      node.textContent = r.insight || '（暂无洞察结果）';
      if (r.insight) {
        try {
          localStorage.setItem(CACHE, JSON.stringify({ fp: fingerprint, text: r.insight }));
        } catch (_) { /* 存储超限忽略 */ }
      }
    } catch (e) {
      node.innerHTML = `<span class="dim">${API.esc(e.message || '洞察加载失败')}</span>`;
    }
  },
};
