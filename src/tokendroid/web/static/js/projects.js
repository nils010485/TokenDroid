import DataManager from './data.js';
import Comp from './components.js';

const { fmt, hitP } = DataManager;
const { C, GC, mkCard, mkTable, bar } = Comp;

let _charts = {};

function build(pane, D, CD) {
  pane.innerHTML = '';
  _charts = {};

  const c1 = mkCard('w');
  c1.innerHTML = '<h3>Sessions by Project</h3><canvas id="pj-sessions" height="300"></canvas>';
  pane.appendChild(c1);

  _charts.sessions = new Chart(document.getElementById('pj-sessions'), {
    type: 'bar',
    data: {
      labels: D.projects.map(p => p.name.split('/').slice(-2).join('/')),
      datasets: [{ data: D.projects.map(p => p.sessions), backgroundColor: C.gn + 'bb', borderRadius: 3 }],
    },
    options: { indexAxis: 'y', plugins: { legend: { display: false } }, scales: { x: { grid: { color: GC } }, y: { grid: { display: false }, ticks: { font: { size: 9 } } } } },
  });

  const ps = D.projects[0]?.sessions || 1;
  const ct = mkCard('w');
  ct.appendChild(mkTable(
    ['Project', 'Sess', 'Input', 'Cache', 'Hit%', 'Output', 'Active', 'Top Models', ''],
    D.projects.map(p => [
      p.name, p.sessions, fmt(p.input), fmt(p.cache || 0), hitP(p.cache || 0, p.input),
      fmt(p.output), (p.active_h || 0).toFixed(1) + 'h',
      (p.top_models || []).slice(0, 3).join(', '),
      bar(p.sessions, ps, 40, C.gn),
    ]),
  ));
  pane.appendChild(ct);
}

export default { build };
