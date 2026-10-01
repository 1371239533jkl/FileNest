/* 应用装配层：导航 / 路由 / 全局搜索 / 主题 / 快捷键 / 命令面板 / API Key 状态 */
'use strict';

const App = {
  current: 'dashboard',
  el: document.getElementById('content'),

  init() {
    this.initTheme();
    this.initSidebar();
    this.buildNav();
    this.bindTopbar();
    this.bindSettingsBtn();
    this.bindShortcuts();
    this.checkKey();
    // 支持 #/view 深链
    const h = location.hash.replace('#/', '');
    window.addEventListener('hashchange', () => this.nav(location.hash.replace('#/', '') || 'dashboard'));
    this.nav(Views[h] ? h : 'dashboard');
  },

  /* ── 侧边导航（按分组装配 Views 注册表） ── */
  buildNav() {
    const nav = document.getElementById('nav');
    const groups = [
      ['总览', ['dashboard']],
      ['文件', ['files', 'recycle', 'content']],
      ['管理', ['duplicates', 'tags', 'classification', 'cleanup']],
      ['自动化', ['lifecycle', 'saved-queries', 'workspaces', 'archives']],
      ['记录', ['history', 'timeline', 'events', 'relations']],
      ['系统', ['scan', 'health', 'ai']],
    ];
    const icons = {
      dashboard: '▤', files: '🔍', recycle: '🗑', content: '☰',
      duplicates: '⧉', tags: '🏷', classification: '◈', cleanup: '✂',
      lifecycle: '⏳', 'saved-queries': '◆', workspaces: '▣', archives: '📦',
      history: '↺', timeline: '🕒', events: '⚡', relations: '⇄',
      scan: '⟳', health: '♥', ai: '✦',
    };
    for (const [title, keys] of groups) {
      const g = document.createElement('div');
      g.className = 'nav-group-title';
      g.textContent = title;
      nav.appendChild(g);
      for (const k of keys) {
        const v = Views[k];
        if (!v) continue;
        const b = document.createElement('button');
        b.className = 'nav-btn';
        b.dataset.view = k;
        b.title = v.title;
        b.innerHTML = `<span class="ico">${icons[k] || '·'}</span><span>${v.title}</span>`;
        b.onclick = () => this.nav(k);
        nav.appendChild(b);
      }
    }
  },

  bindTopbar() {
    document.getElementById('btn-refresh').onclick = () => this.refresh();
    const cmd = document.getElementById('btn-cmd');
    if (cmd) cmd.onclick = () => CommandPalette.open();
    const gs = document.getElementById('global-search');
    gs.onkeydown = (e) => {
      if (e.key !== 'Enter') return;
      const q = gs.value.trim();
      if (!q) return;
      this.nav('files', { qs: { name: q } });
    };
  },

  bindSettingsBtn() {
    document.getElementById('nav-settings').onclick = () => this.nav('settings');
  },

  /* ── 侧边栏折叠（localStorage 持久化；折叠后为图标窄栏，对齐桌面端） ── */
  initSidebar() {
    this.applySidebar(localStorage.getItem('sfm_sidebar') === 'collapsed');
    const b = document.getElementById('btn-collapse');
    if (b) b.onclick = () => this.toggleSidebar();
  },

  applySidebar(collapsed) {
    document.getElementById('sidebar').classList.toggle('collapsed', collapsed);
    const b = document.getElementById('btn-collapse');
    if (b) b.textContent = collapsed ? '»' : '«';
  },

  toggleSidebar() {
    const collapsed = !document.getElementById('sidebar').classList.contains('collapsed');
    localStorage.setItem('sfm_sidebar', collapsed ? 'collapsed' : 'expanded');
    this.applySidebar(collapsed);
  },

  /* ── 主题（深色 / 浅色，localStorage 持久化） ── */
  initTheme() {
    this.applyTheme(localStorage.getItem('sfm_theme') || 'dark');
    const btn = document.getElementById('btn-theme');
    if (btn) btn.onclick = () => this.toggleTheme();
  },

  applyTheme(name) {
    document.body.classList.toggle('light', name === 'light');
    const btn = document.getElementById('btn-theme');
    if (btn) btn.textContent = name === 'light' ? '☀' : '🌙';
  },

  toggleTheme() {
    const next = document.body.classList.contains('light') ? 'dark' : 'light';
    localStorage.setItem('sfm_theme', next);
    this.applyTheme(next);
    UI.toast(next === 'light' ? '已切换到浅色主题' : '已切换到深色主题', 'ok');
  },

  /* ── 全局快捷键（对齐桌面端）── */
  bindShortcuts() {
    document.addEventListener('keydown', (e) => {
      const mod = e.ctrlKey || e.metaKey;
      const k = (e.key || '').toLowerCase();
      if (mod && e.shiftKey && k === 'p') { e.preventDefault(); CommandPalette.open(); return; }
      if (mod && k === 'k') { e.preventDefault(); CommandPalette.open(); return; }
      if (mod && k === 'f') {
        e.preventDefault();
        const g = document.getElementById('global-search');
        if (g) { g.focus(); g.select(); }
        return;
      }
      if (mod && k === 'r') { e.preventDefault(); this.refresh(); return; }
      if (e.key === 'F5') { e.preventDefault(); this.refresh(); return; }
      if (e.key === 'Escape' && typeof CommandPalette !== 'undefined'
        && CommandPalette.isOpen()) {
        CommandPalette.close();
      }
    });
  },

  /* ── 视图切换 ── */
  nav(key, opts) {
    const v = Views[key];
    if (!v) return;
    this.current = key;
    document.querySelectorAll('#nav .nav-btn').forEach(b => b.classList.toggle('active', b.dataset.view === key));
    document.getElementById('nav-settings').classList.toggle('active', key === 'settings');
    document.getElementById('page-title').textContent = v.title;
    if (location.hash !== '#/' + key) history.replaceState(null, '', '#/' + key);
    const el = this.el;
    el.innerHTML = '';
    Promise.resolve(v.render(el, opts)).catch((e) => {
      el.innerHTML = '';
      el.appendChild(UI.empty(e && e.message ? e.message : '加载失败'));
    });
  },

  refresh() { this.nav(this.current); },

  /* ── API Key 状态灯 ── */
  setKeyState(st) {
    const el = document.getElementById('apikey-state');
    const dot = el.querySelector('.dot');
    const cls = st === 'ok' ? 'on' : (st === 'no-key' ? 'mid' : 'off');
    const txt = st === 'ok' ? '已连接'
      : st === 'no-key' ? '服务端未设 Key'
      : st === 'bad-key' ? 'Key 无效'
      : '未连接';
    dot.className = 'dot ' + cls;
    el.lastChild.textContent = ' ' + txt;
  },

  async checkKey() {
    try {
      this.setKeyState(await API.checkKey());
    } catch (_) { this.setKeyState('offline'); }
  },
};

App.init();
