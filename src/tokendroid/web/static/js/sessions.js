import DataManager from './data.js';
import Comp from './components.js';

const { fmt, fmtUSD } = DataManager;
const { mkCard, mkSortTable, paginate, renderPagination } = Comp;

let _allRows = [];
let _filteredRows = [];
let _currentPage = 1;
let _searchTerm = '';
const PER_PAGE = 50;

function build(pane, D, CD) {
  pane.innerHTML = '';
  _currentPage = 1;
  _searchTerm = '';

  const modelCostRate = {};
  if (CD && CD.by_model) {
    const modelTokens = {};
    D.models.forEach(m => { modelTokens[m.name] = (m.input || 0) + (m.cache || 0) + (m.output || 0) || 1; });
    CD.by_model.filter(m => m.matched).forEach(m => {
      const t = modelTokens[m.name] || 1;
      modelCostRate[m.name] = m.total_cost / t;
    });
  }

  _allRows = D.top.map((s, i) => {
    const t = (s.input || 0) + (s.output || 0) + (s.cache || 0);
    const cost = modelCostRate[s.model] ? fmtUSD(t * modelCostRate[s.model]) : '--';
    return { i: i + 1, project: s.project, model: s.model, total: t, input: s.input || 0, cache: s.cache || 0, output: s.output || 0, cost, date: s.date, title: s.title, _costVal: modelCostRate[s.model] ? t * modelCostRate[s.model] : 0 };
  });
  _filteredRows = [..._allRows];

  const search = document.createElement('input');
  search.type = 'text';
  search.className = 'search-input';
  search.placeholder = 'Search project, model, title...';
  search.value = _searchTerm;
  search.oninput = () => {
    _searchTerm = search.value.toLowerCase();
    _currentPage = 1;
    applyFilter();
    renderBody(pane);
  };
  pane.appendChild(search);

  const card = mkCard('w');
  card.id = 'sess-table-card';
  pane.appendChild(card);

  renderBody(pane);
}

function applyFilter() {
  if (!_searchTerm) { _filteredRows = [..._allRows]; return; }
  _filteredRows = _allRows.filter(r =>
    r.project.toLowerCase().includes(_searchTerm) ||
    r.model.toLowerCase().includes(_searchTerm) ||
    (r.title || '').toLowerCase().includes(_searchTerm)
  );
}

function renderBody(pane) {
  const card = document.getElementById('sess-table-card');
  if (!card) return;
  card.innerHTML = '';

  const p = paginate(_filteredRows, _currentPage, PER_PAGE);

  const headers = ['#', 'Project', 'Model', 'Total', 'Input', 'Cache', 'Output', 'Cost', 'Date', 'Title'];
  const rows = p.rows.map(r => [
    r.i,
    r.project.split('/').slice(-2).join('/'),
    r.model,
    fmt(r.total),
    fmt(r.input),
    fmt(r.cache),
    fmt(r.output),
    r.cost,
    r.date,
    r.title,
  ]);

  const t = mkSortTable(headers, rows, [0, 3, 4, 5, 6, 7]);
  card.appendChild(t);

  renderPagination(card, p.page, p.totalPages, p.total, (newPage) => {
    _currentPage = newPage;
    renderBody(pane);
  });
}

export default { build };
