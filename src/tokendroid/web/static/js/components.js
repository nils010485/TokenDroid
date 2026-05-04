import DataManager from './data.js';

const { fmt, fmtUSD, hitP, pct, tot } = DataManager;

const C = {
  ac: '#6366f1', gn: '#22c55e', tl: '#14b8a6', yl: '#eab308',
  rd: '#ef4444', pr: '#a855f7', or: '#f97316', dm: '#6b7280',
  bl: '#3b82f6', pk: '#f472b6',
};
const CL = [C.ac, C.gn, C.tl, C.yl, C.rd, C.pr, C.or, C.dm];
const GC = 'rgba(255,255,255,0.02)';

Chart.defaults.color = C.dm;
Chart.defaults.borderColor = 'rgba(255,255,255,0.06)';
Chart.defaults.font.family = "'Inter',system-ui,sans-serif";
Chart.defaults.plugins.tooltip.backgroundColor = '#11131c';
Chart.defaults.plugins.tooltip.titleColor = '#e2e5ec';
Chart.defaults.plugins.tooltip.bodyColor = '#9ca3af';
Chart.defaults.plugins.tooltip.borderColor = '#1e2130';
Chart.defaults.plugins.tooltip.borderWidth = 1;
Chart.defaults.plugins.tooltip.padding = 10;
Chart.defaults.plugins.tooltip.cornerRadius = 8;
Chart.defaults.plugins.tooltip.displayColors = true;
Chart.defaults.plugins.tooltip.boxWidth = 8;
Chart.defaults.animation = false;

function renderKPIs(container, items) {
  container.innerHTML = items.map(([label, value, color]) =>
    `<div class="kpi" style="--kpi-color:${color}"><div class="kpi-label">${label}</div><div class="kpi-value">${value}</div></div>`
  ).join('');
}

function mkCard(cls) {
  const d = document.createElement('div');
  d.className = 'cd' + (cls ? ' ' + cls : '');
  return d;
}

function renderCostStrip(items) {
  const strip = document.createElement('div');
  strip.className = 'cost-strip';
  strip.innerHTML = items.map(([label, value, color]) =>
    `<div class="cost-item" style="--ci-color:${color}"><div><div class="ci-lbl">${label}</div><div class="ci-val">${value}</div></div></div>`
  ).join('');
  return strip;
}

function mkCtrlBar(options) {
  const bar = document.createElement('div');
  bar.className = 'ctrl-bar';
  options.forEach(({ label, value, on }) => {
    const btn = document.createElement('button');
    btn.className = 'ctrl-btn' + (on ? ' on' : '');
    btn.textContent = label;
    btn.dataset.value = value;
    bar.appendChild(btn);
  });
  return bar;
}

function bar(v, mx, w = 60, c = C.ac) {
  const p = Math.min(v / Math.max(mx, 1), 1);
  return `<span class="bar" style="width:${Math.round(p * w)}px;background:${c}"></span>`;
}

function mkTable(headers, rows, footer) {
  const t = document.createElement('table');
  t.innerHTML = '<thead><tr>' + headers.map(h => `<th>${h}</th>`).join('') + '</tr></thead>';
  const tb = document.createElement('tbody');
  rows.forEach(row => {
    const tr = document.createElement('tr');
    tr.innerHTML = row.map(c => `<td>${c}</td>`).join('');
    tb.appendChild(tr);
  });
  t.appendChild(tb);
  if (footer) {
    const tf = document.createElement('tfoot');
    const tr = document.createElement('tr');
    tr.innerHTML = footer.map(c => `<td>${c}</td>`).join('');
    tf.appendChild(tr);
    t.appendChild(tf);
  }
  return t;
}

function mkSortTable(headers, rows, numCols, footer) {
  const t = document.createElement('table');
  const th = document.createElement('thead');
  const tr = document.createElement('tr');
  headers.forEach((x, i) => {
    const e = document.createElement('th');
    e.innerHTML = x + ' <span class="sort-arrow">&#9650;</span>';
    e.onclick = () => doSort(t, i, numCols.includes(i));
    tr.appendChild(e);
  });
  th.appendChild(tr);
  t.appendChild(th);
  const tb = document.createElement('tbody');
  rows.forEach(row => {
    const tr2 = document.createElement('tr');
    tr2.innerHTML = row.map(c => `<td>${c}</td>`).join('');
    tb.appendChild(tr2);
  });
  t.appendChild(tb);
  if (footer) {
    const tf = document.createElement('tfoot');
    const ftr = document.createElement('tr');
    ftr.innerHTML = footer.map(c => `<td>${c}</td>`).join('');
    tf.appendChild(ftr);
    t.appendChild(tf);
  }
  return t;
}

function doSort(t, col, isNum) {
  const tb = t.querySelector('tbody');
  const rows = [...tb.querySelectorAll('tr')];
  const asc = t.dataset.sc == col && t.dataset.sd !== 'a';
  t.dataset.sc = col;
  t.dataset.sd = asc ? 'a' : 'd';
  t.querySelectorAll('th').forEach((th, i) => {
    th.className = i === col ? 'on' : '';
    th.querySelector('.sort-arrow').innerHTML = i === col ? (asc ? '&#9650;' : '&#9660;') : '&#9650;';
  });
  rows.sort((a, b) => {
    let va = a.cells[col].textContent, vb = b.cells[col].textContent;
    if (isNum) {
      va = parseFloat(va.match(/[\d.]+/)?.[0] || 0);
      vb = parseFloat(vb.match(/[\d.]+/)?.[0] || 0);
      return asc ? va - vb : vb - va;
    }
    return asc ? va.localeCompare(vb) : vb.localeCompare(va);
  });
  rows.forEach(r => tb.appendChild(r));
}

function paginate(rows, page, perPage) {
  const total = rows.length;
  const totalPages = Math.max(1, Math.ceil(total / perPage));
  const p = Math.min(page, totalPages);
  return {
    rows: rows.slice((p - 1) * perPage, p * perPage),
    page: p,
    totalPages,
    total,
  };
}

function renderPagination(container, currentPage, totalPages, total, onPageChange) {
  const div = document.createElement('div');
  div.className = 'pagination';

  const prev = document.createElement('button');
  prev.textContent = 'Prev';
  prev.disabled = currentPage <= 1;
  prev.onclick = () => onPageChange(currentPage - 1);
  div.appendChild(prev);

  const info = document.createElement('span');
  info.className = 'page-info';
  info.textContent = `Page ${currentPage} / ${totalPages}  (${total} rows)`;
  div.appendChild(info);

  const next = document.createElement('button');
  next.textContent = 'Next';
  next.disabled = currentPage >= totalPages;
  next.onclick = () => onPageChange(currentPage + 1);
  div.appendChild(next);

  container.appendChild(div);
}

export default {
  C, CL, GC,
  renderKPIs, mkCard, renderCostStrip, mkCtrlBar, bar,
  mkTable, mkSortTable, doSort, paginate, renderPagination,
};
