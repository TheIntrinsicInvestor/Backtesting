# ruff: noqa
"""
charts.py
---------
The page's JavaScript: Chart.js configs, the barrier slider, section navigation.
Plain string (not an f-string) so no brace doubling is needed. Reads the embedded const D.
"""

JS = r"""
const INK='#0f2220', TEAL='#1a5c52', BLUE='#2563eb', RED='#E02424', AMBER='#E3A008',
      HINT='#8aa49e', BORDER='#e2ddd0', MUT='#4a6460';
Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.font.size = 11;
Chart.defaults.color = MUT;
Chart.defaults.plugins.legend.display = false;
const GRID = { color: 'rgba(15,34,32,.07)', drawTicks: false };
const pct = v => v.toFixed(1) + '%';
const axis = (title, extra) => Object.assign({ grid: GRID, border: { color: BORDER },
  title: { display: !!title, text: title, color: HINT, font: { size: 10 } } }, extra || {});

/* ---------- 1. Smile ---------- */
const barrierLines = {
  id: 'barrierLines',
  afterDatasetsDraw(c) {
    const { ctx, chartArea: a, scales: { x } } = c;
    ctx.save();
    [[0.6,'60%'],[0.7,'70%'],[0.8,'80%']].forEach(([m, lab]) => {
      const px = x.getPixelForValue(m);
      if (px < a.left || px > a.right) return;
      ctx.strokeStyle = 'rgba(224,36,36,.35)'; ctx.lineWidth = 1; ctx.setLineDash([4,3]);
      ctx.beginPath(); ctx.moveTo(px, a.top); ctx.lineTo(px, a.bottom); ctx.stroke();
      ctx.setLineDash([]); ctx.fillStyle = 'rgba(224,36,36,.8)'; ctx.font = '600 10px JetBrains Mono, monospace';
      ctx.textAlign = 'center'; ctx.fillText(lab, px, a.top + 11);
    });
    ctx.restore();
  }
};
new Chart(document.getElementById('smileChart'), {
  data: {
    datasets: [
      { type: 'line', label: 'Fitted', data: D.smile.fitted.map(p => ({ x: p.m, y: p.iv })),
        borderColor: TEAL, borderWidth: 2, pointRadius: 0, tension: .25 },
      { type: 'scatter', label: 'Grid', data: D.smile.grid.map(p => ({ x: p.m, y: p.iv })),
        backgroundColor: INK, pointRadius: 3 },
      { type: 'scatter', label: 'Listed quotes', data: D.smile.quotes.map(p => ({ x: p.m, y: p.iv })),
        backgroundColor: 'rgba(227,160,8,.55)', pointRadius: 2.5 }
    ]
  },
  options: {
    scales: {
      x: axis('Strike as a share of spot', { type: 'linear', min: .45, max: 1.25,
        ticks: { callback: v => (v * 100).toFixed(0) + '%' } }),
      y: axis('Implied volatility', { ticks: { callback: v => v + '%' } })
    },
    plugins: { tooltip: { callbacks: { label: c => (c.parsed.x * 100).toFixed(0) + '% strike: ' + pct(c.parsed.y) } } }
  },
  plugins: [barrierLines]
});

/* ---------- 2. Barrier slider ---------- */
const simChart = new Chart(document.getElementById('simChart'), {
  type: 'bar',
  data: { labels: ['Flat, ATM', 'Fitted skew', 'Flat, barrier'],
          datasets: [{ data: [0,0,0], backgroundColor: [BLUE, TEAL, RED], borderWidth: 0, barPercentage: .62 }] },
  options: {
    indexAxis: 'y',
    scales: { x: axis('Chance of touching the barrier in one year', { min: 0, suggestedMax: 60,
                ticks: { callback: v => v + '%' } }),
              y: axis(null, { grid: { display: false } }) },
    plugins: { tooltip: { callbacks: { label: c => pct(c.parsed.x) } } }
  }
});
const simSlider = document.getElementById('simSlider');
function simUpdate() {
  const b = (+simSlider.value) / 100;
  const row = D.slider.find(r => Math.abs(r.barrier - b) < 1e-9);
  document.getElementById('simBarrier').textContent = (b * 100).toFixed(0) + '%';
  simChart.data.datasets[0].data = [row.atm_p, row.lv_p, row.bar_p];
  simChart.update('none');
  document.getElementById('simAtm').textContent = pct(row.atm_p);
  document.getElementById('simLv').textContent = pct(row.lv_p);
  document.getElementById('simBar').textContent = pct(row.bar_p);
  document.getElementById('simAtmVol').textContent = 'vol ' + pct(row.atm_vol) + ', price ' + row.atm_dip.toFixed(2) + '%';
  document.getElementById('simLvPrice').textContent = 'price ' + row.lv_dip.toFixed(2) + '% of notional';
  document.getElementById('simBarVol').textContent = 'vol ' + pct(row.bar_vol) + ', price ' + row.bar_dip.toFixed(2) + '%';
}
simSlider.addEventListener('input', simUpdate);
simUpdate();

/* ---------- 3. Price and equivalent-vol series ---------- */
const lineOpts = (yTitle) => ({
  scales: { x: axis(null, { ticks: { maxTicksLimit: 10, callback(v) { const s = this.getLabelForValue(v); return s ? s.slice(0,4) : ''; } } }),
            y: axis(yTitle, { ticks: { callback: v => v + '%' } }) },
  plugins: { tooltip: { mode: 'index', intersect: false,
             callbacks: { label: c => c.dataset.label + ': ' + pct(c.parsed.y) } } },
  interaction: { mode: 'index', intersect: false },
  elements: { point: { radius: 0 } }
});
const ser = b => D.series[b];
const priceChart = new Chart(document.getElementById('priceChart'), {
  type: 'line',
  data: { labels: ser('0.7').map(p => p.d), datasets: [
    { label: 'Local volatility', data: ser('0.7').map(p => p.lv), borderColor: TEAL, borderWidth: 1.6, tension: .2 },
    { label: 'Flat, at the money', data: ser('0.7').map(p => p.atm), borderColor: BLUE, borderWidth: 1.3, tension: .2 },
    { label: 'Flat, at the barrier', data: ser('0.7').map(p => p.bar), borderColor: RED, borderWidth: 1.3, tension: .2 }
  ] },
  options: lineOpts('Price, % of notional')
});
const volChart = new Chart(document.getElementById('volChart'), {
  type: 'line',
  data: { labels: ser('0.7').map(p => p.d), datasets: [
    { label: 'Equivalent flat vol', data: ser('0.7').map(p => p.eq_vol), borderColor: INK, borderWidth: 1.8, tension: .2 },
    { label: 'At the money vol', data: ser('0.7').map(p => p.atm_vol), borderColor: BLUE, borderWidth: 1.3, tension: .2 },
    { label: 'Barrier strike vol', data: ser('0.7').map(p => p.bar_vol), borderColor: RED, borderWidth: 1.3, tension: .2 }
  ] },
  options: lineOpts('Implied volatility')
});

/* ---------- 4. Realised vs model, and the gap ---------- */
const SETS = [['SPX', 'S&P 500'], ['SX5E', 'Euro Stoxx 50'], ['SN', 'Single stocks']];
const realChart = new Chart(document.getElementById('realChart'), {
  type: 'bar',
  data: { labels: SETS.map(s => s[1]), datasets: [
    { label: 'Actually knocked in', backgroundColor: INK, data: [] },
    { label: 'Local volatility', backgroundColor: TEAL, data: [] },
    { label: 'Flat, at the money', backgroundColor: BLUE, data: [] },
    { label: 'Flat, at the barrier', backgroundColor: RED, data: [] }
  ] },
  options: {
    scales: { x: axis(null, { grid: { display: false } }),
              y: axis('Probability of knocking in', { ticks: { callback: v => v + '%' } }) },
    plugins: { tooltip: { callbacks: { label: c => c.dataset.label + ': ' + pct(c.parsed.y) } } }
  }
});
const gapChart = new Chart(document.getElementById('gapChart'), {
  data: { labels: [], datasets: [
    { type: 'bar', label: '95% interval', data: [], backgroundColor: 'rgba(26,92,82,.22)',
      borderColor: 'rgba(26,92,82,.5)', borderWidth: 1, barPercentage: .5 },
    { type: 'scatter', label: 'Estimate', data: [], backgroundColor: INK, pointRadius: 4 }
  ] },
  options: {
    indexAxis: 'y',
    scales: { x: axis('Model minus realised, percentage points', { grid: GRID }),
              y: axis(null, { grid: { display: false }, ticks: { font: { size: 10 }, autoSkip: false } }) },
    plugins: { tooltip: { callbacks: { label(c) {
      return c.datasetIndex === 1 ? 'estimate ' + c.parsed.x.toFixed(1) + ' pts'
                                  : 'interval ' + c.raw[0].toFixed(1) + ' to ' + c.raw[1].toFixed(1) + ' pts'; } } } }
  }
});
function setBarrier(b) {
  [ [priceChart, ['lv','atm','bar']], [volChart, ['eq_vol','atm_vol','bar_vol']] ].forEach(([ch, keys]) => {
    keys.forEach((k, i) => { ch.data.datasets[i].data = ser(b).map(p => p[k]); });
    ch.update('none');
  });
  const models = ['lv','atm','bar'];
  realChart.data.datasets[0].data = SETS.map(s => D.summary[s[0]][b].realised);
  models.forEach((m, i) => { realChart.data.datasets[i+1].data = SETS.map(s => D.summary[s[0]][b][m].p_ki); });
  realChart.update('none');
  const labels = [], ranges = [], pts = [];
  SETS.forEach(s => models.forEach((m, i) => {
    const row = D.summary[s[0]][b][m];
    labels.push(s[1] + ' / ' + ['local vol','ATM flat','barrier flat'][i]);
    ranges.push([row.gap_lo, row.gap_hi]);
    pts.push({ x: row.gap, y: labels.length - 1 });
  }));
  gapChart.data.labels = labels;
  gapChart.data.datasets[0].data = ranges;
  gapChart.data.datasets[1].data = pts;
  gapChart.update('none');
}

/* ---------- 5. Premium kept and terciles ---------- */
new Chart(document.getElementById('keptChart'), {
  type: 'bar',
  data: { labels: SETS.map(s => s[1]), datasets: [
    { label: '60%', backgroundColor: TEAL, data: SETS.map(s => D.summary[s[0]]['0.6'].lv.kept) },
    { label: '70%', backgroundColor: BLUE, data: SETS.map(s => D.summary[s[0]]['0.7'].lv.kept) },
    { label: '80%', backgroundColor: AMBER, data: SETS.map(s => D.summary[s[0]]['0.8'].lv.kept) }
  ] },
  options: {
    scales: { x: axis(null, { grid: { display: false } }),
              y: axis('Premium kept after realised losses', { ticks: { callback: v => v + '%' } }) },
    plugins: { tooltip: { callbacks: { label: c => c.dataset.label + ' barrier: ' + pct(c.parsed.y) } } }
  }
});
const T = ['low','mid','high'].map(t => D.terciles.find(r => r.barrier === 0.7 && r.tercile === t));
new Chart(document.getElementById('tercileChart'), {
  data: { labels: T.map(t => t.tercile === 'low' ? 'Calmest third (' + t.vol.toFixed(0) + '% vol)'
                          : t.tercile === 'mid' ? 'Middle third (' + t.vol.toFixed(0) + '% vol)'
                          : 'Most volatile third (' + t.vol.toFixed(0) + '% vol)'),
          datasets: [
    { type: 'bar', label: 'Actually knocked in', backgroundColor: INK, data: T.map(t => t.realised), order: 2 },
    { type: 'bar', label: 'Local volatility said', backgroundColor: TEAL, data: T.map(t => t.lv_p), order: 2 },
    { type: 'line', label: 'Premium kept', data: T.map(t => t.kept), borderColor: AMBER, borderWidth: 2,
      pointRadius: 4, pointBackgroundColor: AMBER, yAxisID: 'y1', order: 1 }
  ] },
  options: {
    scales: { x: axis(null, { grid: { display: false } }),
              y: axis('Knock-in probability', { ticks: { callback: v => v + '%' } }),
              y1: axis('Premium kept', { position: 'right', grid: { display: false },
                       ticks: { callback: v => v + '%' }, min: 0, max: 80 }) },
    plugins: { tooltip: { callbacks: { label: c => c.dataset.label + ': ' + pct(c.parsed.y) } } }
  }
});

/* ---------- 6. Episodes and calibration ---------- */
const epiChart = new Chart(document.getElementById('epiChart'), {
  type: 'bar',
  data: { labels: [], datasets: [{ label: 'Knocked in', backgroundColor: TEAL, data: [], borderWidth: 0 }] },
  options: {
    scales: { x: axis('Year the product started', { grid: { display: false }, ticks: { maxTicksLimit: 15 } }),
              y: axis('Share of that year\'s products', { ticks: { callback: v => v + '%' } }) },
    plugins: { tooltip: { callbacks: { label: c => pct(c.parsed.y) + ' of ' + D.episodes[epiSet]['0.7'][c.dataIndex].n + ' products' } } }
  }
});
let epiSet = 'SPX';
function setEpi(s) {
  epiSet = s;
  const rows = D.episodes[s]['0.7'];
  epiChart.data.labels = rows.map(r => r.y);
  epiChart.data.datasets[0].data = rows.map(r => r.rate);
  epiChart.update('none');
}
const cal = D.calibration.SN['0.7'];
new Chart(document.getElementById('calChart'), {
  data: { datasets: [
    { type: 'line', data: [{x:0,y:0},{x:70,y:70}], borderColor: HINT, borderWidth: 1, borderDash: [5,4],
      pointRadius: 0 },
    { type: 'scatter', data: cal.map(c => ({ x: c.model * 100, y: c.realised * 100, n: c.n })),
      backgroundColor: TEAL, pointRadius: cal.map(c => Math.max(5, Math.min(16, Math.sqrt(c.n) / 2.2))) }
  ] },
  options: {
    scales: { x: axis('Local volatility said', { type: 'linear', min: 0, max: 70, ticks: { callback: v => v + '%' } }),
              y: axis('Actually knocked in', { min: 0, max: 70, ticks: { callback: v => v + '%' } }) },
    plugins: { tooltip: { callbacks: { label: c => c.raw.n ? 'model ' + pct(c.parsed.x) + ', realised ' + pct(c.parsed.y) + ' (' + c.raw.n + ' products)' : '' } } }
  }
});

/* ---------- 7. Fees ---------- */
new Chart(document.getElementById('feeChart'), {
  type: 'bar',
  data: { labels: ['S&P 500 put', 'Single stock put', 'Fee: Vokata', 'Fee: Henderson-Pearson',
                   'Fee: Wallmeier-Diethelm', 'Fee: Stoimenov-Wilkens'],
          datasets: [{ data: [D.summary.SPX['0.7'].lv.pnl, D.summary.SN['0.7'].lv.pnl, -6.5, -8, -3.4, -3.04],
            backgroundColor: [TEAL, TEAL, 'rgba(15,34,32,.28)', 'rgba(15,34,32,.28)', 'rgba(15,34,32,.28)', 'rgba(15,34,32,.28)'],
            borderWidth: 0, barPercentage: .62 }] },
  options: {
    indexAxis: 'y',
    scales: { x: axis('% of notional per year: earned by the option, charged by the note',
              { ticks: { callback: v => v + '%' } }),
              y: axis(null, { grid: { display: false } }) },
    plugins: { tooltip: { callbacks: { label: c => c.parsed.x.toFixed(2) + '%' } } }
  }
});

/* ---------- 8. Controls, nav, progress ---------- */
document.querySelectorAll('.ctrl-btn').forEach(btn => btn.addEventListener('click', () => {
  const group = btn.dataset.group;
  document.querySelectorAll('.ctrl-btn[data-group="' + group + '"]').forEach(b => b.classList.remove('on'));
  btn.classList.add('on');
  if (group === 'epi') setEpi(btn.dataset.set); else setBarrier(btn.dataset.bar);
}));
setBarrier('0.7');
setEpi('SPX');

const _nav = document.querySelector('nav');
window.addEventListener('scroll', () => {
  const el = document.getElementById('progress-bar');
  const pct = window.scrollY / (document.body.scrollHeight - window.innerHeight) * 100;
  el.style.width = Math.min(pct, 100) + '%';
  _nav.classList.toggle('scrolled', window.scrollY > 40);
}, { passive: true });

const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) e.target.classList.add('visible'); }),
  { threshold: 0.07 });
document.querySelectorAll('.section').forEach(s => io.observe(s));

const NAV_LABELS = ['The Put Inside the Note', 'What the Skew Costs', 'Implied Against Realised',
                    'Where the Premium Lives', 'A Price, Not a Forecast', "The Note Buyer's Side",
                    'Methodology', 'Conclusions'];
const sideNav = document.getElementById('side-nav');
const sections = document.querySelectorAll('.section[id]');
sections.forEach((s, i) => {
  const a = document.createElement('a');
  a.href = '#' + s.id;
  a.innerHTML = '<span class="sn-label">' + (NAV_LABELS[i] || '') + '</span><span class="sn-dot"></span>';
  sideNav.appendChild(a);
});
const navItems = sideNav.querySelectorAll('a');
const navIo = new IntersectionObserver(es => es.forEach(e => {
  if (e.isIntersecting) {
    const i = [...sections].indexOf(e.target);
    navItems.forEach((a, j) => a.classList.toggle('active', i === j));
  }
}), { threshold: 0.25 });
sections.forEach(s => navIo.observe(s));
"""
