/* 轻量 SVG 图表组件（环形图 / 折线图）——零第三方依赖，主题自适应 */
'use strict';

const Charts = {
  PALETTE: ['#4f8cff', '#34d399', '#fbbf24', '#a78bfa',
    '#f87171', '#22d3ee', '#f472b6', '#94a3b8'],

  /* 文件类型固定配色（与桌面端 chart_widgets 一致） */
  TYPE_COLORS: {
    image: '#f59e0b', document: '#3b82f6', video: '#8b5cf6', audio: '#10b981',
    archive: '#ef4444', code: '#06b6d4', other: '#6b7280',
  },

  /** 环形图。rows: [{label, value, color?}] */
  pie(rows, opts) {
    const { size = 190, donut = 0.58 } = opts || {};
    const wrap = document.createElement('div');
    wrap.className = 'pie-wrap';
    const total = rows.reduce((s, r) => s + (r.value || 0), 0);
    if (!total) { wrap.appendChild(UI.empty('暂无数据')); return wrap; }

    const cx = size / 2, cy = size / 2, r = size / 2 - 4, inner = r * donut;
    const pt = (rad, ang) =>
      `${(cx + rad * Math.cos(ang)).toFixed(2)} ${(cy + rad * Math.sin(ang)).toFixed(2)}`;
    let angle = -Math.PI / 2;
    const paths = [];
    rows.forEach((row, i) => {
      const frac = (row.value || 0) / total;
      if (frac <= 0) return;
      const color = row.color || this.PALETTE[i % this.PALETTE.length];
      const a2 = angle + frac * Math.PI * 2;
      const large = frac > 0.5 ? 1 : 0;
      const d = frac >= 1
        ? `M ${cx} ${cy - r} A ${r} ${r} 0 1 1 ${cx - 0.01} ${cy - r} Z`
        : `M ${pt(inner, angle)} L ${pt(r, angle)} A ${r} ${r} 0 ${large} 1 ${pt(r, a2)}`
          + ` L ${pt(inner, a2)} A ${inner} ${inner} 0 ${large} 0 ${pt(inner, angle)} Z`;
      paths.push(`<path d="${d}" fill="${color}" class="pie-seg">`
        + `<title>${API.esc(row.label)}：${row.value}（${(frac * 100).toFixed(1)}%）</title></path>`);
      angle = a2;
    });

    const holder = document.createElement('div');
    holder.className = 'pie-svg';
    holder.innerHTML = `<svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}">`
      + paths.join('') + '</svg>';
    holder.innerHTML += `<div class="pie-center"><b>${total}</b><small>总计</small></div>`;
    wrap.appendChild(holder);

    const legend = document.createElement('div');
    legend.className = 'legend col';
    for (const row of rows) {
      const frac = total ? (row.value || 0) / total : 0;
      const i = rows.indexOf(row);
      const color = row.color || this.PALETTE[i % this.PALETTE.length];
      const li = document.createElement('div');
      li.className = 'legend-item';
      li.innerHTML = `<i style="background:${color}"></i>`
        + `<span class="lg-lbl">${API.esc(row.label)}</span>`
        + `<span class="lg-val">${(frac * 100).toFixed(1)}%</span>`;
      legend.appendChild(li);
    }
    wrap.appendChild(legend);
    return wrap;
  },

  /** 折线图。labels: [string]；series: [{name, values:[number], color}] */
  line(labels, series, opts) {
    const { width = 560, height = 210, pad = 34 } = opts || {};
    const wrap = document.createElement('div');
    wrap.className = 'line-wrap';
    const n = labels.length;
    if (!n || !series.length) { wrap.appendChild(UI.empty('暂无数据')); return wrap; }

    const maxV = Math.max(1, ...series.flatMap(s => s.values));
    const plotW = width - pad * 2;
    const plotH = height - pad - 22;
    const x = (i) => pad + (n === 1 ? plotW / 2 : (plotW * i) / (n - 1));
    const y = (v) => pad + plotH - (Math.max(0, v) / maxV) * plotH;

    let svg = `<svg viewBox="0 0 ${width} ${height}" class="charts-svg" style="width:100%;height:auto">`;
    for (let g = 0; g <= 3; g++) {
      const gy = pad + (plotH * g) / 3;
      svg += `<line x1="${pad}" y1="${gy.toFixed(1)}" x2="${width - pad}" `
        + `y2="${gy.toFixed(1)}" class="grid-line"/>`;
      svg += `<text x="${pad - 7}" y="${(gy + 3).toFixed(1)}" class="axis-txt" `
        + `text-anchor="end">${Math.round(maxV * (1 - g / 3))}</text>`;
    }
    const step = Math.max(1, Math.ceil(n / 6));
    labels.forEach((lb, i) => {
      if (i % step !== 0 && i !== n - 1) return;
      svg += `<text x="${x(i).toFixed(1)}" y="${height - 6}" class="axis-txt" `
        + `text-anchor="middle">${API.esc(lb)}</text>`;
    });
    for (const s of series) {
      const pts = s.values.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
      svg += `<polyline points="${pts}" fill="none" stroke="${s.color}" stroke-width="2" `
        + `stroke-linejoin="round" stroke-linecap="round"/>`;
      s.values.forEach((v, i) => {
        svg += `<circle cx="${x(i).toFixed(1)}" cy="${y(v).toFixed(1)}" r="2.6" `
          + `fill="${s.color}"><title>${API.esc(s.name)} ${API.esc(labels[i])}: ${v}</title></circle>`;
      });
    }
    svg += '</svg>';
    wrap.innerHTML = svg;

    const legend = document.createElement('div');
    legend.className = 'legend';
    legend.innerHTML = series.map(s =>
      `<span class="legend-item"><i style="background:${s.color}"></i>${API.esc(s.name)}</span>`
    ).join('');
    wrap.appendChild(legend);
    return wrap;
  },
};
