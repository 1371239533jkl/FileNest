/* API 客户端：封装 fetch，自动附带 X-API-Key，统一错误处理。 */
'use strict';

const KEY_STORE = 'sfm_api_key';

const API = {
  key() { return localStorage.getItem(KEY_STORE) || ''; },
  setKey(k) {
    if (k) localStorage.setItem(KEY_STORE, k);
    else localStorage.removeItem(KEY_STORE);
  },
  hasKey() { return !!this.key(); },

  /** 通用请求。qs 为对象，自动转 query string。 */
  async request(method, path, { qs, body, raw } = {}) {
    let url = path;
    if (qs) {
      const p = new URLSearchParams();
      for (const [k, v] of Object.entries(qs)) {
        if (v === undefined || v === null || v === '') continue;
        p.set(k, v);
      }
      const s = p.toString();
      if (s) url += (url.includes('?') ? '&' : '?') + s;
    }
    const headers = {};
    const key = this.key();
    if (key) headers['X-API-Key'] = key;
    let payload;
    if (body !== undefined) {
      headers['Content-Type'] = 'application/json';
      payload = JSON.stringify(body);
    }
    let res;
    try {
      res = await fetch(url, { method, headers, body: payload });
    } catch (e) {
      throw new Error('无法连接服务器：' + e.message);
    }
    let data = null;
    try { data = await res.json(); } catch (_) { /* 非 JSON */ }
    if (res.status === 401) {
      const err = new Error('API Key 无效或缺失，请到设置页配置');
      err.status = 401;
      throw err;
    }
    if (!res.ok) {
      const msg = (data && (data.detail || data.message)) ||
        `请求失败 (HTTP ${res.status})`;
      const err = new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
      err.status = res.status;
      throw err;
    }
    return raw ? res : data;
  },

  get(path, qs) { return this.request('GET', path, { qs }); },
  post(path, body, qs) { return this.request('POST', path, { body, qs }); },
  put(path, body) { return this.request('PUT', path, { body }); },
  del(path, qs) { return this.request('DELETE', path, { qs }); },

  /* ── 常用快捷方法 ── */
  health() { return this.request('GET', '/health', { raw: true }); },

  async checkKey() {
    // 用免 key 也能命中的 health 判断连通；再试带 key 请求判断有效性
    try {
      const res = await this.request('GET', '/health', { raw: true });
      if (!res.ok) return 'offline';
      if (!this.hasKey()) return 'no-key';
      try {
        await this.get('/api/dashboard');
        return 'ok';
      } catch (e) {
        return e.status === 401 ? 'bad-key' : 'offline';
      }
    } catch (_) { return 'offline'; }
  },

  fmtBytes(n) {
    if (n === null || n === undefined) return '-';
    if (n < 1024) return n + ' B';
    const units = ['KB', 'MB', 'GB', 'TB'];
    let v = n;
    let i = -1;
    do { v /= 1024; i++; } while (v >= 1024 && i < units.length - 1);
    return v.toFixed(1) + ' ' + units[i];
  },

  fmtTime(s) {
    if (!s) return '-';
    return String(s).replace('T', ' ').slice(0, 19);
  },

  esc(s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/[&<>"']/g, c =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  },
};

/* 全局错误弹出 */
window.onunhandledrejection = (e) => {
  const msg = e.reason && e.reason.message ? e.reason.message : '未知错误';
  UI.toast(msg, 'err');
};
