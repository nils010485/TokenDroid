const ICONS = {
  overview: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>',
  models: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>',
  projects: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>',
  sessions: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>',
  cost: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>',
  patterns: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/><path d="M3 15h18"/><path d="M9 3v18"/><path d="M15 3v18"/></svg>',
};

const NAV = [
  { group: 'OVERVIEW', items: [{ id: 'overview', label: 'Overview' }] },
  { group: 'BREAKDOWN', items: [
    { id: 'models', label: 'Models' },
    { id: 'projects', label: 'Projects' },
    { id: 'sessions', label: 'Sessions' },
  ]},
  { group: 'INSIGHTS', items: [
    { id: 'cost', label: 'Cost' },
    { id: 'patterns', label: 'Patterns' },
  ]},
];

const PAGE_TITLES = {
  overview: 'Overview',
  models: 'Models',
  projects: 'Projects',
  sessions: 'Sessions',
  cost: 'Cost',
  patterns: 'Patterns',
};

function buildSidebar() {
  const nav = document.getElementById('sidebar-nav');
  nav.innerHTML = '';
  NAV.forEach(group => {
    const label = document.createElement('div');
    label.className = 'nav-group-label';
    label.textContent = group.group;
    nav.appendChild(label);

    group.items.forEach(item => {
      const btn = document.createElement('button');
      btn.className = 'nav-item';
      btn.dataset.tab = item.id;
      btn.innerHTML = `<span class="nav-icon">${ICONS[item.id]}</span><span class="nav-label">${item.label}</span>`;
      btn.onclick = () => navigate(item.id);
      nav.appendChild(btn);
    });
  });
}

function navigate(pageId) {
  document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('on'));
  const btn = document.querySelector(`.nav-item[data-tab="${pageId}"]`);
  if (btn) btn.classList.add('on');

  const title = document.getElementById('page-title');
  if (title) title.textContent = PAGE_TITLES[pageId] || pageId;

  document.querySelectorAll('.pane').forEach(p => p.classList.remove('on'));
  const pane = document.getElementById('p-' + pageId);
  if (pane) {
    pane.classList.add('on');
    const event = new CustomEvent('pageActivate', { detail: { pageId } });
    document.dispatchEvent(event);
  }

  const params = new URLSearchParams(window.location.search);
  params.set('tab', pageId);
  window.history.replaceState({}, '', '?' + params.toString());

  requestAnimationFrame(() => window.dispatchEvent(new Event('resize')));
}

function getInitialPage() {
  const params = new URLSearchParams(window.location.search);
  return params.get('tab') || 'overview';
}

function buildPanes() {
  const container = document.getElementById('panes');
  container.innerHTML = '';
  NAV.forEach(group => {
    group.items.forEach(item => {
      const p = document.createElement('div');
      p.className = 'pane';
      p.id = 'p-' + item.id;
      container.appendChild(p);
    });
  });
}

const Router = { buildSidebar, buildPanes, navigate, getInitialPage, PAGE_TITLES };

export default Router;
