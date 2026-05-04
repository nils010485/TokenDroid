import DataManager from './data.js';
import Comp from './components.js';

const { fmtUSD, tot, sumCost } = DataManager;
const { C, CL, GC, mkCard, mkSortTable, bar, renderCostStrip, mkCtrlBar } = Comp;

let _tlChart = null;
let _selPeriod = 'daily';
let _selModels = new Set();

function build(pane, D, CD) {
  pane.innerHTML = '';
  _tlChart = null;

  if (!CD || !CD.total) {
    pane.innerHTML = '<p class="empty-state">No cost data available</p>';
    return;
  }

  const t = CD.total;

  pane.appendChild(renderCostStrip([
    ['Total Cost', fmtUSD(t.total_cost), 'var(--accent)'],
    ['Input Cost', fmtUSD(t.input_cost), 'var(--green)'],
    ['Output Cost', fmtUSD(t.output_cost), 'var(--teal)'],
    ['Cache Cost', fmtUSD(t.cache_cost), 'var(--yellow)'],
    ['Reasoning', fmtUSD(t.reasoning_cost), 'var(--purple)'],
  ]));

  const now = new Date();
  const dl = CD.daily || [];
  const today = now.toISOString().slice(0, 10);
  const sumDays = (from) => {
    const cut = new Date(now);
    cut.setDate(cut.getDate() - from);
    return dl.filter(d => new Date(d.date) >= cut).reduce((a, d) => a + d.total_cost, 0);
  };
  const todayCost = (dl.find(d => d.date === today) || {}).total_cost || 0;

  pane.appendChild(renderCostStrip([
    ['Today', fmtUSD(todayCost), 'var(--pink)'],
    ['Last 7d', fmtUSD(sumDays(7)), 'var(--teal)'],
    ['Last 30d', fmtUSD(sumDays(30)), 'var(--green)'],
    ['Last 90d', fmtUSD(sumDays(90)), 'var(--orange)'],
  ]));

  const g = document.createElement('div');
  g.className = 'g2';
  pane.appendChild(g);

  const c1 = mkCard('w');
  c1.innerHTML = '<h3>Cost Timeline by Model</h3><div id="cost-ctrl"></div><div style="position:relative;height:320px"><canvas id="cost-timeline"></canvas></div>';
  g.appendChild(c1);

  const ctrlArea = document.getElementById('cost-ctrl');
  buildTimelineControls(ctrlArea, CD);
  drawTimeline(CD);

  const g2 = document.createElement('div');
  g2.className = 'g2';
  pane.appendChild(g2);

  const c2 = mkCard();
  c2.innerHTML = '<h3>Cost by Model</h3><canvas id="cost-model-bar" height="260"></canvas>';
  g2.appendChild(c2);

  const c3 = mkCard();
  c3.innerHTML = '<h3>Cost Share</h3><canvas id="cost-model-donut" height="260"></canvas>';
  g2.appendChild(c3);

  const matched = (CD.by_model || []).filter(m => m.matched);
  new Chart(document.getElementById('cost-model-bar'), {
    type: 'bar',
    data: {
      labels: matched.map(m => m.name),
      datasets: [
        { label: 'Input', data: matched.map(m => m.input_cost), backgroundColor: C.gn + '77', borderRadius: 2 },
        { label: 'Output', data: matched.map(m => m.output_cost), backgroundColor: C.tl + '77', borderRadius: 2 },
        { label: 'Cache', data: matched.map(m => m.cache_cost), backgroundColor: C.yl + '77', borderRadius: 2 },
      ],
    },
    options: { indexAxis: 'y', responsive: true, plugins: { legend: { labels: { boxWidth: 8 } } }, scales: { x: { grid: { color: GC }, stacked: true, ticks: { callback: v => fmtUSD(v) } }, y: { grid: { display: false }, stacked: true } } },
  });

  new Chart(document.getElementById('cost-model-donut'), {
    type: 'doughnut',
    data: { labels: matched.map(m => m.name), datasets: [{ data: matched.map(m => m.total_cost), backgroundColor: CL, borderWidth: 0 }] },
    options: { maintainAspectRatio: false, aspectRatio: 1, plugins: { legend: { position: 'right', labels: { boxWidth: 8, font: { size: 10 } } } } },
  });

  const mxModel = Math.max(...matched.map(m => m.total_cost), 1);
  const ct1 = mkCard('w');
  ct1.innerHTML = '<h3>Cost by Model</h3>';
  ct1.appendChild(mkSortTable(
    ['Model', 'Input', 'Output', 'Cache', 'Reasoning', 'Total', 'Matched', ''],
    matched.map(m => [m.name, fmtUSD(m.input_cost), fmtUSD(m.output_cost), fmtUSD(m.cache_cost), fmtUSD(m.reasoning_cost), fmtUSD(m.total_cost), m.matched ? 'Yes' : 'No', bar(m.total_cost, mxModel, 50, C.ac)]),
    [1, 2, 3, 4, 5],
    ['<b>Total</b>', fmtUSD(matched.reduce((a, m) => a + m.input_cost, 0)), fmtUSD(matched.reduce((a, m) => a + m.output_cost, 0)), fmtUSD(matched.reduce((a, m) => a + m.cache_cost, 0)), fmtUSD(matched.reduce((a, m) => a + m.reasoning_cost, 0)), fmtUSD(matched.reduce((a, m) => a + m.total_cost, 0)), '', ''],
  ));
  pane.appendChild(ct1);

  const bp = (CD.by_project || []).filter(p => p.total_cost > 0);
  if (bp.length) {
    const mxP = Math.max(...bp.map(p => p.total_cost), 1);
    const ct2 = mkCard('w');
    ct2.innerHTML = '<h3>Cost by Project</h3>';
    ct2.appendChild(mkSortTable(
      ['Project', 'Input', 'Output', 'Cache', 'Reasoning', 'Total', ''],
      bp.map(p => [p.name, fmtUSD(p.input_cost), fmtUSD(p.output_cost), fmtUSD(p.cache_cost), fmtUSD(p.reasoning_cost), fmtUSD(p.total_cost), bar(p.total_cost, mxP, 50, C.gn)]),
      [1, 2, 3, 4, 5],
      ['<b>Total</b>', fmtUSD(bp.reduce((a, p) => a + p.input_cost, 0)), fmtUSD(bp.reduce((a, p) => a + p.output_cost, 0)), fmtUSD(bp.reduce((a, p) => a + p.cache_cost, 0)), fmtUSD(bp.reduce((a, p) => a + p.reasoning_cost, 0)), fmtUSD(bp.reduce((a, p) => a + p.total_cost, 0)), ''],
    ));
    pane.appendChild(ct2);
  }

  const mo = CD.monthly || [];
  if (mo.length) {
    const ct3 = mkCard('w');
    ct3.innerHTML = '<h3>Monthly Cost</h3>';
    ct3.appendChild(mkSortTable(
      ['Month', 'Input', 'Output', 'Cache', 'Reasoning', 'Total'],
      mo.slice().reverse().map(m => [m.month, fmtUSD(m.input_cost), fmtUSD(m.output_cost), fmtUSD(m.cache_cost), fmtUSD(m.reasoning_cost), fmtUSD(m.total_cost)]),
      [1, 2, 3, 4, 5],
      ['<b>Total</b>', fmtUSD(mo.reduce((a, m) => a + m.input_cost, 0)), fmtUSD(mo.reduce((a, m) => a + m.output_cost, 0)), fmtUSD(mo.reduce((a, m) => a + m.cache_cost, 0)), fmtUSD(mo.reduce((a, m) => a + m.reasoning_cost, 0)), fmtUSD(mo.reduce((a, m) => a + m.total_cost, 0))],
    ));
    pane.appendChild(ct3);
  }
}

function buildTimelineControls(container, CD) {
  _selPeriod = 'daily';
  const periods = [['daily', 'Daily'], ['weekly', 'Weekly'], ['monthly', 'Monthly']];

  const ctrlBar = document.createElement('div');
  ctrlBar.className = 'ctrl-bar';
  periods.forEach(([k, l]) => {
    const btn = document.createElement('button');
    btn.className = 'ctrl-btn' + (k === _selPeriod ? ' on' : '');
    btn.textContent = l;
    btn.onclick = () => {
      _selPeriod = k;
      ctrlBar.querySelectorAll('.ctrl-btn').forEach(b => b.classList.remove('on'));
      btn.classList.add('on');
      drawTimeline(CD);
    };
    ctrlBar.appendChild(btn);
  });
  container.appendChild(ctrlBar);

  const modelMap = { daily: CD.daily_by_model || {}, weekly: CD.weekly_by_model || {}, monthly: CD.monthly_by_model || {} };
  function _cmn(n) { return n.replace(/^custom:/, '').replace(/-\d+$/, '').replace(/\[.*?\]/g, '').replace(/^-/, '').trim() || n; }
  const nameMap = {};
  Object.values(modelMap).forEach(m => Object.keys(m).forEach(k => { nameMap[k] = _cmn(k); }));
  const revMap = Object.fromEntries(Object.entries(nameMap).map(([k, v]) => [v, k]));
  const matchedNames = [...new Set(Object.values(nameMap))];
  const modelTotal = matchedNames.map(n => {
    const k = revMap[n];
    let t = 0;
    Object.values(modelMap).forEach(m => { (m[k] || []).forEach(r => { t += r.total_cost; }); });
    return t;
  });
  const sortedIdx = matchedNames.map((_, i) => i).sort((a, b) => modelTotal[b] - modelTotal[a]);
  const allModels = sortedIdx.map(i => matchedNames[i]).filter(n => modelTotal[matchedNames.indexOf(n)] > 0);
  const mColors = allModels.map((_, i) => CL[i % CL.length]);
  _selModels = new Set(allModels);

  const md = document.createElement('div');
  md.className = 'model-checks';

  const toggleAll = document.createElement('label');
  toggleAll.className = 'cm-check';
  toggleAll.innerHTML = '<input type="checkbox" checked><span>All</span>';
  toggleAll.querySelector('input').onchange = function () {
    _selModels = this.checked ? new Set(allModels) : new Set();
    md.querySelectorAll('.cm-m').forEach((c, i) => {
      c.querySelector('input').checked = this.checked;
      if (this.checked) _selModels.add(allModels[i]); else _selModels.delete(allModels[i]);
    });
    drawTimeline(CD);
  };
  md.appendChild(toggleAll);

  allModels.forEach((m, i) => {
    const l = document.createElement('label');
    l.className = 'cm-check cm-m';
    l.innerHTML = `<input type="checkbox" checked><span style="color:${mColors[i]}">●</span><span>${m}</span>`;
    l.querySelector('input').onchange = function () {
      if (this.checked) _selModels.add(m); else _selModels.delete(m);
      drawTimeline(CD);
    };
    md.appendChild(l);
  });
  container.appendChild(md);

  container._allModels = allModels;
  container._revMap = revMap;
  container._mColors = mColors;
  container._modelMap = modelMap;
}

function drawTimeline(CD) {
  const ctrlArea = document.getElementById('cost-ctrl');
  if (!ctrlArea) return;
  const allModels = ctrlArea._allModels || [];
  const revMap = ctrlArea._revMap || {};
  const mColors = ctrlArea._mColors || [];
  const modelMap = ctrlArea._modelMap || {};

  const pKey = _selPeriod === 'daily' ? 'date' : _selPeriod === 'weekly' ? 'week' : 'month';
  const agg = CD[_selPeriod] || [];
  const labels = agg.map(d => d[pKey]);
  const datasets = [];

  _selModels.forEach(m => {
    const ok = revMap[m];
    const rows = (modelMap[_selPeriod] || {})[ok] || [];
    const rMap = Object.fromEntries(rows.map(r => [r[pKey], r.total_cost]));
    datasets.push({
      label: m, data: labels.map(l => rMap[l] || 0),
      borderColor: mColors[allModels.indexOf(m)] || C.ac,
      backgroundColor: (mColors[allModels.indexOf(m)] || C.ac) + '18',
      fill: false, tension: 0.4, pointRadius: 2, pointHoverRadius: 4, borderWidth: 2,
    });
  });

  if (_selModels.size > 0) {
    datasets.push({
      label: 'Total', data: labels.map((_, li) => datasets.reduce((s, ds) => s + (ds.data[li] || 0), 0)),
      borderColor: C.ac, fill: false, tension: 0.4, pointRadius: 2, borderWidth: 2, borderDash: [4, 3],
    });
  }

  const data = { labels, datasets };
  if (!_tlChart) {
    _tlChart = new Chart(document.getElementById('cost-timeline'), {
      type: 'line', data,
      options: {
        responsive: true, maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { labels: { boxWidth: 8, usePointStyle: true } } },
        scales: { x: { grid: { color: GC }, offset: true, ticks: { maxRotation: 0, maxTicksLimit: _selPeriod === 'daily' ? 20 : undefined } }, y: { grid: { color: GC }, ticks: { callback: v => fmtUSD(v) } } },
      },
    });
  } else {
    _tlChart.data = data;
    _tlChart.options.scales.x.ticks.maxTicksLimit = _selPeriod === 'daily' ? 20 : undefined;
    _tlChart.update();
  }
}

export default { build };
