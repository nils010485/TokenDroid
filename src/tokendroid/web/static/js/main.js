import DataManager from './data.js';
import Comp from './components.js';
import Router from './router.js';
import Overview from './overview.js';
import Models from './models.js';
import Projects from './projects.js';
import Sessions from './sessions.js';
import CostPage from './cost.js';
import Patterns from './patterns.js';

const { renderKPIs } = Comp;

const PAGE_BUILDERS = {
  overview: Overview.build,
  models: Models.build,
  projects: Projects.build,
  sessions: Sessions.build,
  cost: CostPage.build,
  patterns: Patterns.build,
};

let _builtPages = new Set();

function buildKPIs(D, CD) {
  const ti = DataManager.tot(D.daily, 'input');
  const tc = D.daily.reduce((s, d) => s + (d.cache || 0), 0);
  const to = DataManager.tot(D.daily, 'output');
  const ta = DataManager.tot(D.daily, 'active_h');
  const ts = DataManager.tot(D.daily, 'sessions');
  const tm = DataManager.tot(D.daily, 'messages');
  const tt = ti + tc + to;
  const costV = CD && CD.total ? DataManager.fmtUSD(CD.total.total_cost) : '--';

  document.getElementById('date-range').textContent =
    D.daily.length ? D.daily[0].date + ' → ' + D.daily[D.daily.length - 1].date : '';

  renderKPIs(document.getElementById('kpi-grid'), [
    ['Sessions', ts.toLocaleString(), 'var(--blue)'],
    ['Total Tokens', DataManager.fmt(tt), 'var(--accent)'],
    ['Cost', costV, 'var(--pink)'],
    ['Input', DataManager.fmt(ti), 'var(--green)'],
    ['Cache', DataManager.fmt(tc), 'var(--yellow)'],
    ['Output', DataManager.fmt(to), 'var(--teal)'],
    ['Active', ta.toFixed(1) + 'h', 'var(--purple)'],
    ['Messages', tm.toLocaleString(), 'var(--orange)'],
    ['Projects', D.projects.length, 'var(--orange)'],
    ['Models', D.models.length, 'var(--red)'],
  ]);
}

function buildPage(pageId) {
  const { dashboard: D, cost: CD } = DataManager.getData();
  if (!D) return;

  const pane = document.getElementById('p-' + pageId);
  if (!pane) return;

  const builder = PAGE_BUILDERS[pageId];
  if (builder) {
    pane.innerHTML = '';
    builder(pane, D, CD);
  }
}

function buildAll() {
  const { dashboard: D, cost: CD } = DataManager.getData();
  if (!D) return;

  const scrollEl = document.querySelector('.content');
  const savedScroll = scrollEl ? scrollEl.scrollTop : 0;

  buildKPIs(D, CD);

  const activeTab = document.querySelector('.nav-item.on');
  if (activeTab) {
    buildPage(activeTab.dataset.tab);
  }

  if (scrollEl) scrollEl.scrollTop = savedScroll;
}

function applyFilters() {
  const project = document.getElementById('filter-project')?.value || '';
  const model = document.getElementById('filter-model')?.value || '';

  const params = new URLSearchParams(window.location.search);
  if (project) params.set('project', project); else params.delete('project');
  if (model) params.set('model', model); else params.delete('model');
  window.history.replaceState({}, '', '?' + params.toString());
}

async function init() {
  Router.buildSidebar();
  Router.buildPanes();

  await DataManager.load();

  const { dashboard: D } = DataManager.getData();
  populateFilters(D);

  const { cost: CD } = DataManager.getData();
  if (D) buildKPIs(D, CD);

  document.addEventListener('pageActivate', (e) => {
    buildPage(e.detail.pageId);
  });

  const initialPage = Router.getInitialPage();
  Router.navigate(initialPage);

  DataManager.startAutoRefresh();

  document.addEventListener('dataUpdated', () => {
    const { dashboard: D } = DataManager.getData();
    populateFilters(D);
    buildAll();

    const ts = document.getElementById('timestamp');
    if (ts) ts.textContent = 'Updated ' + new Date().toLocaleTimeString();
  });

  document.getElementById('filter-project')?.addEventListener('change', applyFilters);
  document.getElementById('filter-model')?.addEventListener('change', applyFilters);
}

init();
