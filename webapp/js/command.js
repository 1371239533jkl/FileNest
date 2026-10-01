/* 命令面板（Ctrl+Shift+P / Ctrl+K）——对齐桌面端 CommandPalette */
'use strict';

const CommandPalette = {
  _root: null,
  _input: null,
  _list: null,
  _all: [],
  _shown: [],
  _sel: 0,

  _build() {
    if (this._root) return;
    const root = document.createElement('div');
    root.id = 'cmdk-root';
    root.innerHTML = `<div class="cmdk">
      <input type="text" placeholder="输入命令或页面名称…" autocomplete="off">
      <div class="cmdk-list"></div>
      <div class="cmdk-hint">↑↓ 选择 · Enter 执行 · Esc 关闭</div>
    </div>`;
    document.body.appendChild(root);
    this._root = root;
    this._input = root.querySelector('input');
    this._list = root.querySelector('.cmdk-list');
    root.addEventListener('click', (e) => { if (e.target === root) this.close(); });
    this._input.addEventListener('input', () => { this._sel = 0; this._render(); });
    this._input.addEventListener('keydown', (e) => this._onKey(e));
  },

  open() {
    this._build();
    this._all = this._commands();
    this._input.value = '';
    this._sel = 0;
    this._render();
    this._root.classList.add('show');
    this._input.focus();
  },

  close() { if (this._root) this._root.classList.remove('show'); },

  isOpen() { return !!this._root && this._root.classList.contains('show'); },

  _commands() {
    const cmds = [
      { ico: '⟳', label: '刷新当前页', hint: 'F5', run: () => App.refresh() },
      { ico: '⌕', label: '聚焦全局搜索', hint: 'Ctrl+F', run: () => {
        App.nav('files');
        setTimeout(() => {
          const g = document.getElementById('global-search');
          if (g) g.focus();
        }, 60);
      } },
      { ico: '◐', label: '切换深色 / 浅色主题', hint: '', run: () => App.toggleTheme() },
      { ico: '⚙', label: '打开系统设置', hint: '', run: () => App.nav('settings') },
    ];
    for (const [k, v] of Object.entries(Views)) {
      if (!v || !v.title) continue;
      cmds.push({ ico: '▸', label: '前往：' + v.title, hint: '', run: () => App.nav(k) });
    }
    return cmds;
  },

  _filter(q) {
    if (!q) return this._all;
    const ql = q.toLowerCase();
    return this._all.filter(c => c.label.toLowerCase().includes(ql));
  },

  _render() {
    const q = (this._input.value || '').trim();
    this._shown = this._filter(q).slice(0, 40);
    if (this._sel >= this._shown.length) this._sel = 0;
    this._list.innerHTML = '';
    if (!this._shown.length) {
      this._list.innerHTML = '<div class="cmdk-item dim">无匹配命令</div>';
      return;
    }
    this._shown.forEach((c, i) => {
      const d = document.createElement('div');
      d.className = 'cmdk-item' + (i === this._sel ? ' sel' : '');
      d.innerHTML = `<span class="cmdk-ico">${c.ico || '·'}</span>`
        + `<span>${API.esc(c.label)}</span>`
        + (c.hint ? `<span class="cmdk-key">${API.esc(c.hint)}</span>` : '');
      d.onclick = () => this._run(i);
      d.onmouseenter = () => { this._sel = i; this._paint(); };
      this._list.appendChild(d);
    });
    this._paint();
  },

  _paint() {
    Array.from(this._list.children).forEach((el, i) =>
      el.classList.toggle('sel', i === this._sel));
  },

  _onKey(e) {
    if (e.key === 'Escape') { this.close(); return; }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      this._sel = Math.min(this._sel + 1, this._shown.length - 1);
      this._paint();
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      this._sel = Math.max(this._sel - 1, 0);
      this._paint();
    } else if (e.key === 'Enter') {
      e.preventDefault();
      this._run(this._sel);
    }
  },

  _run(i) {
    const c = this._shown[i];
    if (!c) return;
    this.close();
    try { c.run(); } catch (_) { /* 单条命令失败不影响面板 */ }
  },
};
