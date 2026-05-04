import DataManager from './data.js';
import Comp from './components.js';

const { fmt, fmtUSD, tot } = DataManager;
const { C, GC, mkCard } = Comp;

let _charts = {};

function build(pane, D, CD) {
  pane.innerHTML = '';
  _charts = {};

  const g = document.createElement('div');
  g.className = 'g2';
  pane.appendChild(g);

  const c1 = mkCard();
  c1.innerHTML = '<h3>Hourly Distribution</h3><canvas id="pt-hourly" height="220"></canvas>';
  g.appendChild(c1);

  const c2 = mkCard();
  c2.innerHTML = '<h3>Day of Week</h3><canvas id="pt-dow" height="220"></canvas>';
  g.appendChild(c2);

  const hl = Array.from({ length: 24 }, (_, i) => i);
  const hd = hl.map(h => { const f = D.hourly.find(x => x.hour === h); return f ? f.sessions : 0; });

  _charts.hourly = new Chart(document.getElementById('pt-hourly'), {
    type: 'bar',
    data: { labels: hl.map(h => h + 'h'), datasets: [{ label: 'Sessions', data: hd, backgroundColor: C.or + '66', borderRadius: 2 }] },
    options: {
      plugins: { legend: { display: false } },
      scales: { x: { grid: { color: GC }, offset: true }, y: { title: { display: true, text: 'Sessions', color: C.dm }, grid: { color: GC } } },
    },
  });

  const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const dd = Array.from({ length: 7 }, (_, i) => { const f = D.dow.find(x => x.dow === i); return f ? f.sessions : 0; });

  _charts.dow = new Chart(document.getElementById('pt-dow'), {
    type: 'bar',
    data: { labels: dayNames, datasets: [{ label: 'Sessions', data: dd, backgroundColor: C.pr + '66', borderRadius: 2 }] },
    options: {
      plugins: { legend: { display: false } },
      scales: { x: { grid: { color: GC }, offset: true }, y: { title: { display: true, text: 'Sessions', color: C.dm }, grid: { color: GC } } },
    },
  });

  const c3 = mkCard('w');
  c3.innerHTML = '<h3>Session Length Distribution</h3><canvas id="pt-len" height="200"></canvas>';
  pane.appendChild(c3);

  const bins = ['0-1m', '1-5m', '5-15m', '15-30m', '30m-1h', '1h+'];
  const bcounts = [0, 0, 0, 0, 0, 0];
  D.top.forEach(s => {
    const h = ((s.cache || 0) + (s.input || 0) + (s.output || 0)) / 1e6;
    if (h < 0.01) bcounts[0]++;
    else if (h < 0.1) bcounts[1]++;
    else if (h < 1) bcounts[2]++;
    else if (h < 10) bcounts[3]++;
    else if (h < 100) bcounts[4]++;
    else bcounts[5]++;
  });

  _charts.len = new Chart(document.getElementById('pt-len'), {
    type: 'bar',
    data: { labels: bins, datasets: [{ data: bcounts, backgroundColor: C.ac + '77', borderRadius: 3 }] },
    options: { plugins: { legend: { display: false } }, scales: { x: { grid: { color: GC }, offset: true }, y: { grid: { color: GC } } } },
  });
}

export default { build };
