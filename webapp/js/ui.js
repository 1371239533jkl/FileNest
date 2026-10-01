/* UI 基础组件：toast / 模态 / 表单弹窗 / 确认框 / 分页 / 徽章 / 表格外壳 */
'use strict';

const Views = {};   // 视图注册表（app.js 装配导航）

const UI = {
  /* ── Toast ── */
  toast(msg, type = 'info', ms = 3200) {
    const wrap = document.getElementById('toast-wrap');
    const el = document.createElement('div');
    el.className = 'toast ' + type;
    el.textContent = msg;
    wrap.appendChild(el);
    setTimeout(() => { el.style.transition = 'opacity .35s'; el.style.opacity = '0'; }, ms);
    setTimeout(() => el.remove(), ms + 400);
  },

  /* ── 模态（body 可为字符串或元素；foot 可选；返回对象供 close） ── */
  modal({ title, body, foot }) {
    const root = document.getElementById('modal-root');
    root.innerHTML = '';
    const m = document.createElement('div');
    m.className = 'modal';
    m.innerHTML = `<div class="modal-head"><h3>${API.esc(title || '')}</h3><button class="modal-close">×</button></div>`;
    const bodyEl = document.createElement('div');
    bodyEl.className = 'modal-body';
    if (typeof body === 'string') bodyEl.innerHTML = body;
    else if (body) bodyEl.appendChild(body);
    m.appendChild(bodyEl);
    if (foot) m.appendChild(foot);
    root.appendChild(m);
    root.classList.add('show');
    let closed = false;
    const close = () => {
      if (closed) return;
      closed = true;
      root.classList.remove('show');
      root.innerHTML = '';
    };
    m.querySelector('.modal-close').onclick = close;
    root.addEventListener('mousedown', (e) => { if (e.target === root) close(); });
    return { root, modal: m, body: bodyEl, close };
  },

  close(modal) {
    if (modal) modal.close();
  },

  /* ── 确认框 → Promise<boolean> ── */
  confirm(msg, { title = '确认操作', danger = false } = {}) {
    return new Promise((resolve) => {
      const foot = document.createElement('div');
      foot.className = 'modal-foot';
      const cancel = document.createElement('button');
      cancel.className = 'btn'; cancel.textContent = '取消';
      const ok = document.createElement('button');
      ok.className = 'btn ' + (danger ? 'danger' : 'primary'); ok.textContent = '确认';
      foot.append(cancel, ok);
      const modal = this.modal({
        title,
        body: `<p style="padding:6px 0;line-height:1.7">${API.esc(msg)}</p>`,
        foot,
      });
      cancel.onclick = () => this.close(modal);
      ok.onclick = () => { this.close(modal); resolve(true); };
    });
  },

  /* ── 表单弹窗 → Promise<values|null>（取消返回 null） ──
     fields: [{name,label,type:'text|number|select|textarea|checkbox',value,options:[{v,l}],placeholder,required,full}] */
  formModal({ title, fields, submitText = '保存', wide = false }) {
    return new Promise((resolve) => {
      const body = document.createElement('div');
      body.className = 'form-grid';
      if (wide) body.style.gridTemplateColumns = '1fr';
      const inputs = {};
      for (const f of fields) {
        const wrap = document.createElement('div');
        wrap.className = 'field' + (f.full ? ' full' : '');
        const label = document.createElement('label');
        label.textContent = f.label || f.name;
        wrap.appendChild(label);
        let el;
        if (f.type === 'select') {
          el = document.createElement('select');
          for (const o of (f.options || [])) {
            const op = document.createElement('option');
            op.value = o.v; op.textContent = o.l;
            el.appendChild(op);
          }
          if (f.value !== undefined) el.value = f.value;
        } else if (f.type === 'textarea') {
          el = document.createElement('textarea');
          el.value = f.value ?? ''; el.placeholder = f.placeholder || '';
        } else if (f.type === 'checkbox') {
          el = document.createElement('input');
          el.type = 'checkbox'; el.checked = !!f.value;
        } else {
          el = document.createElement('input');
          el.type = f.type || 'text';
          el.value = f.value ?? '';
          el.placeholder = f.placeholder || '';
        }
        if (f.required) el.required = true;
        wrap.appendChild(el);
        inputs[f.name] = el;
        body.appendChild(wrap);
      }
      const foot = document.createElement('div');
      foot.className = 'modal-foot';
      const cancel = document.createElement('button');
      cancel.className = 'btn'; cancel.textContent = '取消';
      const ok = document.createElement('button');
      ok.className = 'btn primary'; ok.textContent = submitText;
      foot.append(cancel, ok);
      const modal = this.modal({ title, body, foot });
      cancel.onclick = () => this.close(modal);
      ok.onclick = () => {
        const values = {};
        let invalid = false;
        for (const f of fields) {
          const el = inputs[f.name];
          values[f.name] = f.type === 'checkbox' ? el.checked : el.value;
          if (f.required && f.type !== 'checkbox' && String(values[f.name] ?? '').trim() === '') {
            invalid = true;
          }
        }
        if (invalid) { this.toast('请填写必填项', 'err'); return; }
        this.close(modal);
        resolve(values);
      };
    });
  },

  /* ── 分页条 ── */
  pager({ page, pageSize, total, onChange }) {
    page = page || 0;
    pageSize = pageSize || 100;
    const pages = Math.max(1, Math.ceil(total / pageSize));
    const wrap = document.createElement('div');
    wrap.className = 'pager';
    const info = document.createElement('span');
    info.textContent = `共 ${total} 条 · 第 ${page + 1} / ${pages} 页`;
    const prev = document.createElement('button');
    prev.className = 'btn small'; prev.textContent = '‹ 上一页';
    prev.disabled = page <= 0;
    const next = document.createElement('button');
    next.className = 'btn small'; next.textContent = '下一页 ›';
    next.disabled = page >= pages - 1;
    prev.onclick = () => onChange(page - 1);
    next.onclick = () => onChange(page + 1);
    wrap.append(info, prev, next);
    return wrap;
  },

  badge(text, cls = 'gray') {
    const s = document.createElement('span');
    s.className = 'badge ' + cls;
    s.textContent = text;
    return s;
  },

  empty(msg) {
    const d = document.createElement('div');
    d.className = 'empty';
    d.textContent = msg || '暂无数据';
    return d;
  },

  spin(msg = '加载中…') {
    const d = document.createElement('div');
    d.className = 'empty';
    d.textContent = msg;
    return d;
  },

  /* 文件类型中文名 */
  ftype(key) {
    const m = {
      image: '图片', document: '文档', code: '代码', video: '视频', audio: '音频',
      archive: '压缩包', executable: '可执行文件', font: '字体', other: '其他',
    };
    return m[key] || key || '其他';
  },
};
