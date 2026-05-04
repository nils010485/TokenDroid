const DataManager = (() => {
  let _dashboard = null;
  let _cost = null;
  let _listeners = [];
  let _refreshTimer = null;
  const REFRESH_INTERVAL = 30000;

  function fmt(n) {
    if (n >= 1e9) return (n / 1e9).toFixed(1) + 'B';
    if (n >= 1e6) return (n / 1e6).toFixed(2) + 'M';
    if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
    return n.toString();
  }

  function fmtUSD(v) {
    if (v === 0) return '$0.00';
    if (v < 0.01) return '$' + v.toFixed(4);
    if (v < 1) return '$' + v.toFixed(3);
    return '$' + v.toFixed(2);
  }

  function pct(part, total) {
    return total ? (part / Math.max(total, 1) * 100) : 0;
  }

  function hitP(cache, input) {
    const t = input + cache;
    return t ? pct(cache, t).toFixed(0) + '%' : '-';
  }

  function tot(arr, key) {
    return arr.reduce((s, d) => s + (d[key] || 0), 0);
  }

  function sumCost(periods) {
    if (!periods) return 0;
    return periods.reduce((a, d) => a + (d.total_cost || 0), 0);
  }

  async function load() {
    const [r, rc] = await Promise.all([
      fetch('/api/dashboard'),
      fetch('/api/cost'),
    ]);
    _dashboard = await r.json();
    try { _cost = await rc.json(); } catch { _cost = null; }
    document.dispatchEvent(new CustomEvent('dataUpdated', { detail: { dashboard: _dashboard, cost: _cost } }));
    return { dashboard: _dashboard, cost: _cost };
  }

  function startAutoRefresh() {
    stopAutoRefresh();
    _refreshTimer = setInterval(load, REFRESH_INTERVAL);
  }

  function stopAutoRefresh() {
    if (_refreshTimer) { clearInterval(_refreshTimer); _refreshTimer = null; }
  }

  function getData() { return { dashboard: _dashboard, cost: _cost }; }

  function filterDaily(dashboard, dateFrom, dateTo) {
    if (!dateFrom && !dateTo) return dashboard.daily;
    return dashboard.daily.filter(d => {
      if (dateFrom && d.date < dateFrom) return false;
      if (dateTo && d.date > dateTo) return false;
      return true;
    });
  }

  function deriveWeekly(daily) {
    const ws = {};
    daily.forEach(d => {
      const k = weekId(new Date(d.date));
      if (!ws[k]) ws[k] = { s: 0, i: 0, o: 0, c: 0, a: 0, m: 0 };
      const w = ws[k];
      w.s += d.sessions;
      w.i += d.input;
      w.o += d.output;
      w.c += (d.cache || 0);
      w.a += d.active_h;
      w.m += d.messages;
    });
    return Object.keys(ws).sort().map(k => ({
      week: k, sessions: ws[k].s, input: ws[k].i, output: ws[k].o,
      cache: ws[k].c, active_h: ws[k].a, messages: ws[k].m,
    }));
  }

  function deriveMonthly(daily) {
    const ms = {};
    daily.forEach(d => {
      const k = d.date.slice(0, 7);
      if (!ms[k]) ms[k] = { s: 0, i: 0, o: 0, c: 0, a: 0, m: 0 };
      const m = ms[k];
      m.s += d.sessions;
      m.i += d.input;
      m.o += d.output;
      m.c += (d.cache || 0);
      m.a += d.active_h;
      m.m += d.messages;
    });
    return Object.keys(ms).sort().map(k => ({
      month: k, sessions: ms[k].s, input: ms[k].i, output: ms[k].o,
      cache: ms[k].c, active_h: ms[k].a, messages: ms[k].m,
    }));
  }

  function weekId(d) {
    const dt = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
    dt.setUTCDate(dt.getUTCDate() + 4 - (dt.getUTCDay() || 7));
    const y = dt.getUTCFullYear();
    return y + '-W' + String(Math.ceil(((dt - new Date(Date.UTC(y, 0, 1))) / 864e5 + 1) / 7)).padStart(2, '0');
  }

  return {
    load, startAutoRefresh, stopAutoRefresh, getData,
    filterDaily, deriveWeekly, deriveMonthly,
    fmt, fmtUSD, pct, hitP, tot, sumCost, weekId,
  };
})();

export default DataManager;
