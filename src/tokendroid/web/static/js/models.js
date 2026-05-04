import DataManager from './data.js';
import Comp from './components.js';

const { fmt, hitP, pct, tot } = DataManager;
const { C, CL, GC, mkCard, mkTable, bar } = Comp;

let _charts = {};

function build(pane, D, CD) {
  pane.innerHTML = '';
  _charts = {};

  const g = document.createElement('div');
  g.className = 'g2';
  pane.appendChild(g);

  const c1 = mkCard();
  c1.innerHTML = '<h3>Sessions by Model</h3><canvas id="md-sessions" height="250"></canvas>';
  g.appendChild(c1);

  const c2 = mkCard();
  c2.innerHTML = '<h3>Output by Model</h3><canvas id="md-output" height="250"></canvas>';
  g.appendChild(c2);

  const c3 = mkCard();
  c3.innerHTML = '<h3>Cache Hit %</h3><canvas id="md-cache"></canvas>';
  g.appendChild(c3);

  const c4 = mkCard();
  c4.innerHTML = '<h3>Token Share</h3><canvas id="md-share" height="250"></canvas>';
  g.appendChild(c4);

  const ms = D.models[0]?.sessions || 1;

  _charts.sessions = new Chart(document.getElementById('md-sessions'), {
    type: 'bar',
    data: { labels: D.models.map(m => m.name), datasets: [{ data: D.models.map(m => m.sessions), backgroundColor: CL, borderRadius: 3 }] },
    options: { indexAxis: 'y', plugins: { legend: { display: false } }, scales: { x: { grid: { color: GC } }, y: { grid: { display: false } } } },
  });

  _charts.output = new Chart(document.getElementById('md-output'), {
    type: 'bar',
    data: { labels: D.models.map(m => m.name), datasets: [{ data: D.models.map(m => m.output), backgroundColor: CL, borderRadius: 3 }] },
    options: { indexAxis: 'y', plugins: { legend: { display: false } }, scales: { x: { grid: { color: GC }, ticks: { callback: v => fmt(v) } }, y: { grid: { display: false } } } },
  });

  _charts.cache = new Chart(document.getElementById('md-cache'), {
    type: 'bar',
    data: { labels: D.models.map(m => m.name), datasets: [{ data: D.models.map(m => { const t = (m.input || 0) + (m.cache || 0); return t ? ((m.cache || 0) / t * 100).toFixed(1) : 0; }), backgroundColor: C.yl + 'aa', borderRadius: 3 }] },
    options: { indexAxis: 'y', plugins: { legend: { display: false } }, scales: { x: { grid: { color: GC }, min: 0, max: 100, ticks: { callback: v => v + '%' } }, y: { grid: { display: false } } } },
  });

  _charts.share = new Chart(document.getElementById('md-share'), {
    type: 'doughnut',
    data: { labels: D.models.map(m => m.name), datasets: [{ data: D.models.map(m => m.input + m.cache + m.output), backgroundColor: CL, borderWidth: 0 }] },
    options: { maintainAspectRatio: false, aspectRatio: 1, plugins: { legend: { position: 'right', labels: { boxWidth: 8, font: { size: 10 } } } } },
  });

  const totalTokens = tot(D.models.map(x => (x.input || 0) + (x.cache || 0) + (x.output || 0)), 0) || 1;
  const ct = mkCard('w');
  ct.appendChild(mkTable(
    ['Model', 'Sess', 'Input', 'Cache', 'Hit%', 'Output', 'Active', 'Share', ''],
    D.models.map(m => {
      const t = (m.input || 0) + (m.cache || 0) + (m.output || 0);
      return [m.name, m.sessions, fmt(m.input || 0), fmt(m.cache || 0), hitP(m.cache || 0, m.input || 0), fmt(m.output), (m.active_h || 0).toFixed(1) + 'h', pct(t, totalTokens).toFixed(1) + '%', bar(m.sessions, ms, 40, C.ac)];
    }),
  ));
  pane.appendChild(ct);
}

export default { build };
