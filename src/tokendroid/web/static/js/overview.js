import DataManager from './data.js';
import Comp from './components.js';

const { fmt, fmtUSD, hitP, tot, sumCost } = DataManager;
const { C, CL, GC, mkCard, mkTable, mkSortTable, bar, mkCtrlBar } = Comp;

let _charts = {};
let _built = {};

function build(pane, D, CD) {
  pane.innerHTML = '';
  _charts = {};

  const ctrl = mkCtrlBar([
    { label: 'Daily', value: 'daily', on: true },
    { label: 'Weekly', value: 'weekly', on: false },
    { label: 'Monthly', value: 'monthly', on: false },
  ]);
  pane.appendChild(ctrl);

  const content = document.createElement('div');
  content.id = 'ov-content';
  pane.appendChild(content);

  ctrl.querySelectorAll('.ctrl-btn').forEach(btn => {
    btn.onclick = () => {
      ctrl.querySelectorAll('.ctrl-btn').forEach(b => b.classList.remove('on'));
      btn.classList.add('on');
      renderPeriod(content, btn.dataset.value, D, CD);
    };
  });

  const tl = mkCard('w');
  tl.innerHTML = '<h3>Model Usage Over Time</h3><canvas id="ov-timeline" height="280"></canvas>';
  pane.appendChild(tl);
  buildTimeline(D);

  renderPeriod(content, 'daily', D, CD);
}

function renderPeriod(container, period, D, CD) {
  container.innerHTML = '';
  _charts = {};

  let data, labelKey, periodLabel;
  if (period === 'daily') {
    data = D.daily;
    labelKey = 'date';
    periodLabel = 'Day';
  } else if (period === 'weekly') {
    data = D.weekly && D.weekly.length ? D.weekly : DataManager.deriveWeekly(D.daily);
    labelKey = 'week';
    periodLabel = 'Week';
  } else {
    data = D.monthly && D.monthly.length ? D.monthly : DataManager.deriveMonthly(D.daily);
    labelKey = 'month';
    periodLabel = 'Month';
  }

  const labels = data.map(d => d[labelKey]);

  const g = document.createElement('div');
  g.className = 'g2';
  container.appendChild(g);

  const c1 = mkCard('w');
  c1.innerHTML = `<h3>Tokens / ${periodLabel}</h3><canvas id="ov-tokens" height="300"></canvas>`;
  g.appendChild(c1);

  const c2 = mkCard();
  c2.innerHTML = `<h3>Sessions</h3><canvas id="ov-sessions" height="200"></canvas>`;
  g.appendChild(c2);

  const c3 = mkCard();
  c3.innerHTML = `<h3>Active Hours</h3><canvas id="ov-active" height="200"></canvas>`;
  g.appendChild(c3);

  if (period === 'daily') {
    _charts.tokens = new Chart(document.getElementById('ov-tokens'), {
      type: 'line',
      data: {
        labels,
        datasets: [
          { label: 'Input', data: data.map(d => d.input), borderColor: C.gn, backgroundColor: C.gn + '18', fill: true, tension: 0.4, pointRadius: 3, pointHoverRadius: 5, borderWidth: 2 },
          { label: 'Cache', data: data.map(d => d.cache || 0), borderColor: C.yl, backgroundColor: C.yl + '18', fill: true, tension: 0.4, pointRadius: 3, pointHoverRadius: 5, borderWidth: 2 },
          { label: 'Output', data: data.map(d => d.output), borderColor: C.tl, backgroundColor: C.tl + '18', fill: true, tension: 0.4, pointRadius: 3, pointHoverRadius: 5, borderWidth: 2 },
        ],
      },
      options: { responsive: true, plugins: { legend: { labels: { boxWidth: 8 } } }, scales: { x: { grid: { color: GC }, offset: true, ticks: { maxRotation: 0 } }, y: { type: 'logarithmic', grid: { color: GC }, ticks: { callback: v => fmt(v) } } } },
    });
  } else {
    _charts.tokens = new Chart(document.getElementById('ov-tokens'), {
      type: 'bar',
      data: {
        labels,
        datasets: [
          { label: 'Input', data: data.map(d => d.input), backgroundColor: C.gn + '77', borderRadius: 3 },
          { label: 'Cache', data: data.map(d => d.cache || 0), backgroundColor: C.yl + '77', borderRadius: 3 },
          { label: 'Output', data: data.map(d => d.output), backgroundColor: C.tl + '77', borderRadius: 3 },
        ],
      },
      options: { responsive: true, plugins: { legend: { labels: { boxWidth: 8 } } }, scales: { x: { grid: { color: GC }, offset: true, ticks: { maxRotation: 0 } }, y: { type: 'logarithmic', grid: { color: GC }, ticks: { callback: v => fmt(v) } } } },
    });
  }

  _charts.sessions = new Chart(document.getElementById('ov-sessions'), {
    type: 'bar',
    data: { labels, datasets: [{ data: data.map(d => d.sessions), backgroundColor: C.ac + 'aa', borderRadius: 3 }] },
    options: { responsive: true, plugins: { legend: { display: false } }, scales: { x: { grid: { color: GC }, offset: true, ticks: { maxRotation: 0 } }, y: { grid: { color: GC } } } },
  });

  _charts.active = new Chart(document.getElementById('ov-active'), {
    type: 'bar',
    data: { labels, datasets: [{ data: data.map(d => d.active_h), backgroundColor: C.pr + 'aa', borderRadius: 3 }] },
    options: { responsive: true, plugins: { legend: { display: false } }, scales: { x: { grid: { color: GC }, offset: true, ticks: { maxRotation: 0 } }, y: { grid: { color: GC } } } },
  });

  const c4 = mkCard();
  c4.innerHTML = `<h3>Cache Hit Rate</h3><canvas id="ov-cache" height="200"></canvas>`;
  g.appendChild(c4);

  _charts.cache = new Chart(document.getElementById('ov-cache'), {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Cache %', data: data.map(d => { const t = d.input + (d.cache || 0); return t ? ((d.cache || 0) / t * 100).toFixed(1) : 0; }),
        borderColor: C.yl, backgroundColor: C.yl + '18', fill: true, tension: 0.4, pointRadius: 3, pointHoverRadius: 5, borderWidth: 2,
      }],
    },
    options: { responsive: true, plugins: { legend: { display: false } }, scales: { x: { grid: { color: GC }, offset: true, ticks: { maxRotation: 0 } }, y: { grid: { color: GC }, min: 0, max: 100, ticks: { callback: v => v + '%' } } } },
  });

  const costPeriod = CD ? (CD[period] || []) : [];
  if (costPeriod.length) {
    const costKey = labelKey;
    const c5 = mkCard();
    c5.innerHTML = `<h3>Cost / ${periodLabel}</h3><canvas id="ov-cost" height="200"></canvas>`;
    g.appendChild(c5);

    _charts.cost = new Chart(document.getElementById('ov-cost'), {
      type: period === 'daily' ? 'line' : 'bar',
      data: {
        labels: costPeriod.map(d => d[costKey]),
        datasets: [
          { label: 'Input', data: costPeriod.map(d => d.input_cost), borderColor: C.gn, backgroundColor: C.gn + '18', fill: period === 'daily', tension: 0.4, pointRadius: 2, pointHoverRadius: 4, borderWidth: 2 },
          { label: 'Output', data: costPeriod.map(d => d.output_cost), borderColor: C.tl, backgroundColor: C.tl + '18', fill: period === 'daily', tension: 0.4, pointRadius: 2, pointHoverRadius: 4, borderWidth: 2 },
          { label: 'Cache', data: costPeriod.map(d => d.cache_cost), borderColor: C.yl, backgroundColor: C.yl + '18', fill: period === 'daily', tension: 0.4, pointRadius: 2, pointHoverRadius: 4, borderWidth: 2 },
          ...(period === 'daily' ? [{ label: 'Total', data: costPeriod.map(d => d.total_cost), borderColor: C.ac, backgroundColor: C.ac + '08', fill: false, tension: 0.4, pointRadius: 2, pointHoverRadius: 4, borderWidth: 2, borderDash: [4, 3] }] : []),
        ],
      },
      options: {
        responsive: true, plugins: { legend: { labels: { boxWidth: 8 } } },
        scales: {
          x: { grid: { color: GC }, offset: true, ticks: { maxRotation: 0, maxTicksLimit: 20 } },
          y: { grid: { color: GC }, ticks: { callback: v => fmtUSD(v) }, ...(period !== 'daily' ? { stacked: true } : {}) },
          ...(period !== 'daily' ? { x: { grid: { color: GC }, offset: true, ticks: { maxRotation: 0 }, stacked: true } } : {}),
        },
      },
    });
  }

  const mx = Math.max(...data.map(d => d.sessions), 1);
  const costMap = costPeriod.length ? Object.fromEntries(costPeriod.map(d => [d[labelKey], d.total_cost])) : {};
  const totalCost = sumCost(costPeriod);

  const headers = [periodLabel, 'Sess', 'Input', 'Cache', 'Hit%', 'Output', 'Active', 'Cost', 'Msgs', ''];
  const rows = data.slice().reverse().map(d => [
    d[labelKey], d.sessions, fmt(d.input), fmt(d.cache || 0), hitP(d.cache || 0, d.input),
    fmt(d.output), d.active_h.toFixed(1) + 'h', costMap[d[labelKey]] != null ? fmtUSD(costMap[d[labelKey]]) : '--',
    d.messages.toLocaleString(), bar(d.sessions, mx, 50, C.ac),
  ]);
  const footerRow = [
    '<b>Total</b>',
    tot(data, 'sessions'),
    fmt(tot(data, 'input')),
    fmt(data.reduce((s, d) => s + (d.cache || 0), 0)),
    '',
    fmt(tot(data, 'output')),
    data.reduce((s, d) => s + (d.active_h || 0), 0).toFixed(1) + 'h',
    fmtUSD(totalCost),
    tot(data, 'messages').toLocaleString(),
    '',
  ];

  const ct = mkCard('w');
  ct.appendChild(mkTable(headers, rows, footerRow));
  container.appendChild(ct);
}

function buildTimeline(D) {
  const modelDays = {};
  D.top.forEach(s => {
    if (!s.date) return;
    const mk = s.model;
    if (!modelDays[mk]) modelDays[mk] = {};
    if (!modelDays[mk][s.date]) modelDays[mk][s.date] = { i: 0, c: 0, o: 0 };
    modelDays[mk][s.date].i += s.input || 0;
    modelDays[mk][s.date].c += s.cache || 0;
    modelDays[mk][s.date].o += s.output || 0;
  });

  const allDates = [...new Set(D.top.map(s => s.date).filter(Boolean))].sort();
  const topModels = D.models.slice(0, 6).map(m => m.name);

  new Chart(document.getElementById('ov-timeline'), {
    type: 'line',
    data: {
      labels: allDates,
      datasets: topModels.map((mk, i) => ({
        label: mk.length > 20 ? mk.slice(0, 20) + '...' : mk,
        data: allDates.map(d => (modelDays[mk] && modelDays[mk][d]) ? (modelDays[mk][d].i + (modelDays[mk][d].c || 0)) : 0),
        borderColor: CL[i % CL.length],
        backgroundColor: CL[i % CL.length] + '10',
        fill: false, tension: 0.4, pointRadius: 3, pointHoverRadius: 5, borderWidth: 2,
      })),
    },
    options: { responsive: true, plugins: { legend: { labels: { boxWidth: 8, font: { size: 10 } } } }, scales: { x: { grid: { color: GC }, offset: true, ticks: { maxRotation: 0 } }, y: { grid: { color: GC }, ticks: { callback: v => fmt(v) } } } },
  });
}

export default { build };
