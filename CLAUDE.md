# CLAUDE.md — The Intrinsic Investor

This file gives Claude full context on this project. Read it at the start of every session before doing anything.

---

## About the Site

**URL:** theintrinsicinvestor.com
**Owner:** Brian Liew — BSc Accounting & Finance student at the London School of Economics (LSE)
**Hosting:** GitHub Pages (custom domain via CNAME), auto-deploys on push to `main`
**Repo:** https://github.com/TheIntrinsicInvestor/Backtesting.git
**DNS:** Managed via WordPress.com — A records point to GitHub Pages IPs (185.199.108-111.153), CNAME record `www` → `theintrinsicInvestor.github.io`

**Purpose:** A systematic quantitative research platform publishing honest backtests on institutional data (WRDS / OptionMetrics / Compustat / IBES). Targets finance recruiters and investment professionals. Every report discloses methodology, limitations, and statistical caveats — no cherry-picking.

**Brian does not write code himself.** Deliver complete, runnable scripts one at a time.

---

## File Structure

```
theintrinsicinvestor/
├── index.html                          # Homepage
├── about.html                          # About page
├── research/
│   ├── index.html                      # Research listing page
│   ├── leveraged-etf-strategy/
│   │   ├── index.html                  # Report: AVGO/AVL leveraged ETF carry trade
│   │   ├── 01_pull_prices.py
│   │   ├── 02_strategy.py
│   │   └── 03_analysis.py
│   ├── wheel-strategy/
│   │   ├── index.html                  # Report: SPY wheel strategy (2018–2025)
│   │   ├── 01_pull_options.py
│   │   ├── 02_backtest.py
│   │   └── 03_analysis.py
│   ├── short-straddle/
│   │   ├── index.html                  # Report: Mag7 short straddle on earnings
│   │   ├── 01_pull_earnings.py
│   │   ├── 02_pull_options.py
│   │   └── 03_strategy.py
│   └── iran-iv-study/
│       ├── index.html                  # Report: Iran IV event study (published)
│       ├── events.py
│       ├── 01_data_check.py
│       ├── 02_secid_mapper.py
│       ├── 03_iv_pull.py
│       ├── 04_price_pull.py
│       ├── 05_event_study.py
│       └── 06_analysis_charts.py
├── options-payoff/
│   └── index.html                      # Options payoff visualiser tool
├── CNAME                               # → theintrinsicinvestor.com
├── .nojekyll                           # Prevents Jekyll processing
├── .gitignore                          # Excludes _backups/, __pycache__/, *.pyc, .claude/, *.parquet
├── README.md
└── _backups/                           # Local dated backups — NEVER committed to git
    └── 2026-03-24/
```

---

## Design System — "Parchment & Teal"

### Colours
| Variable | Hex | Use |
|---|---|---|
| `--bg` | `#f7f4ec` | Page background (parchment) |
| `--bg2` | `#f0ece2` | Sidebar / alternate surface |
| `--bg3` | `#e8e3d8` | Borders, table headers |
| `--ink` | `#0f2220` | Primary text, headings |
| `--muted` | `#4a6460` | Body text |
| `--hint` | `#8aa49e` | Labels, captions |
| `--border` | `#e2ddd0` | All borders |
| `--card` | `#fff` | Card backgrounds |
| `--accent` | `#1a5c52` | Teal — interactive elements, underlines |
| `--accent2` | `#144a42` | Darker teal — hover states |

### Fonts
- **Fraunces** (serif) — headings, logo, pull quotes, italic accents
- **Inter** (sans-serif) — body text, nav, labels, UI
- **JetBrains Mono** (monospace) — metrics, code, KPI numbers, hero-meta

All loaded from Google Fonts. Always include all three.

### Design Principles
- Parchment warmth — never cold or sterile
- Understated but considered — no flashy effects, no aggressive animations
- Editorial feel — like a well-designed research journal
- Every visual choice must earn its place

---

## Global CSS Patterns (apply to every page)

```css
/* Paper grain overlay — always present */
body::after {
  content: '';
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 9999;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='250' height='250'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.80' numOctaves='4' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='250' height='250' filter='url(%23noise)' opacity='0.07'/%3E%3C/svg%3E");
  mix-blend-mode: multiply;
  opacity: 0.5;
}

/* Frosted glass nav — light pages */
nav {
  background: rgba(247, 244, 236, 0.92);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  transition: box-shadow 0.3s;
}
nav.scrolled { box-shadow: 0 1px 24px rgba(15, 34, 32, 0.06); }

/* Frosted glass nav — dark pages (iran-iv-study) */
nav { background: rgba(15, 34, 32, 0.95); }

/* Animated nav underlines */
.nav-links a { position: relative; padding-bottom: 2px; }
.nav-links a::after {
  content: '';
  position: absolute;
  bottom: -1px; left: 0; right: 0;
  height: 1px;
  background: var(--accent);
  transform: scaleX(0);
  transform-origin: left;
  transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}
.nav-links a:hover::after { transform: scaleX(1); }

/* prefers-reduced-motion — always include */
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

### Report Pages — Additional Patterns

```css
/* Reading progress bar */
#progress-bar {
  position: fixed; top: 0; left: 0;
  height: 2px; width: 0%;
  background: linear-gradient(90deg, #1a5c52, #2d9d8f);
  z-index: 9998;
  transition: width 0.1s linear;
}

/* Hero entrance animations */
@keyframes fadeUp {
  from { opacity: 0; transform: translateY(18px); }
  to   { opacity: 1; transform: translateY(0); }
}
.hero-tag  { animation: fadeUp .6s ease both; }
.hero h1   { animation: fadeUp .6s .1s ease both; }
.hero p    { animation: fadeUp .6s .2s ease both; }
.hero-meta { animation: fadeUp .6s .3s ease both; }

/* Hero diagonal texture */
.hero { position: relative; overflow: hidden; }
.hero::before {
  content: '';
  position: absolute; inset: 0;
  background-image: repeating-linear-gradient(
    -55deg, transparent, transparent 40px,
    rgba(255,255,255,0.013) 40px, rgba(255,255,255,0.013) 41px
  );
  pointer-events: none;
}

/* Section scroll-reveal */
.section { opacity: 0; transform: translateY(16px); transition: opacity .55s ease, transform .55s ease; }
.section.visible { opacity: 1; transform: none; }

/* Dot section navigation */
#dot-nav {
  position: fixed; right: 1.5rem; top: 50%;
  transform: translateY(-50%);
  display: flex; flex-direction: column; gap: 8px;
  z-index: 50;
}
#dot-nav a { width: 8px; height: 8px; border-radius: 50%; background: var(--border); display: block; transition: background .2s, transform .2s; }
#dot-nav a.active { background: var(--accent); transform: scale(1.35); }
@media (max-width: 860px) { #dot-nav { display: none; } }
```

### Standard JS Block (all report pages, before `</body>`)

```html
<div id="progress-bar"></div>
<div id="dot-nav"></div>
<script>
const pb = document.getElementById('progress-bar');
window.addEventListener('scroll', () => {
  const max = document.documentElement.scrollHeight - window.innerHeight;
  pb.style.width = (window.scrollY / max * 100) + '%';
}, { passive: true });

const navEl = document.querySelector('nav');
window.addEventListener('scroll', () => {
  navEl.classList.toggle('scrolled', window.scrollY > 10);
}, { passive: true });

const sections = document.querySelectorAll('.section');
const dotNav = document.getElementById('dot-nav');
if (dotNav && sections.length) {
  sections.forEach((s, i) => {
    if (!s.id) s.id = 'sec-' + i;
    const a = document.createElement('a');
    a.href = '#' + s.id;
    dotNav.appendChild(a);
  });
}

const io = new IntersectionObserver((entries) => {
  entries.forEach(e => {
    if (e.isIntersecting) {
      e.target.classList.add('visible');
      e.target.querySelectorAll('tbody tr').forEach((tr, i) => {
        setTimeout(() => tr.classList.add('visible'), i * 40);
      });
      e.target.querySelectorAll('.callout').forEach((c, i) => {
        setTimeout(() => c.classList.add('visible'), i * 80);
      });
    }
  });
}, { threshold: 0.08 });
sections.forEach(s => io.observe(s));

const dotLinks = dotNav ? dotNav.querySelectorAll('a') : [];
const ioNav = new IntersectionObserver((entries) => {
  entries.forEach(e => {
    const idx = Array.from(sections).indexOf(e.target);
    if (idx >= 0 && dotLinks[idx]) dotLinks[idx].classList.toggle('active', e.isIntersecting);
  });
}, { threshold: 0.3 });
sections.forEach(s => ioNav.observe(s));
</script>
```

---

## Site Pages

### Navigation (all pages)
```html
<nav>
  <div class="nav-logo">The Intrinsic Investor</div>
  <ul class="nl">
    <li><a href="/">Home</a></li>
    <li><a href="/research">Research</a></li>
    <li><a href="/about">About</a></li>
  </ul>
</nav>
```
Active link gets class `on`. Logo is never a link — just a div.

### Published Reports

| Report | Path | Status |
|---|---|---|
| Exploiting Leveraged ETF Decay | `/research/leveraged-etf-strategy/` | Published |
| SPY Wheel Strategy Backtest | `/research/wheel-strategy/` | Published |
| Selling Earnings Volatility (Mag7 Straddles) | `/research/short-straddle/` | Published |
| Iran Geopolitical IV Event Study | `/research/iran-iv-study/` | Published |

**WIP reports are NOT shown on the homepage or research listing page** until published. Filter by `status === 'published'` in the JS render functions.

---

## Iran IV Study — Completed

**Title:** "IV Behaviour in Energy Sector Options Around Iran-Related Geopolitical Events"
**Status:** Published at `/research/iran-iv-study/`

All 6 scripts completed. Report live on the site.

---

## Data & Infrastructure

**WRDS access:** Python `wrds` library — username set via `WRDS_USERNAME` environment variable.
Before running any WRDS script, set this in your terminal first:
```
set WRDS_USERNAME=hoovyalert
```
Then run the Python script as normal. The password is stored locally in pgpass and never touches the code.
**Data sources used:** OptionMetrics (IV surfaces), IBES (earnings dates), Compustat (fundamentals), yfinance (price data for ETF study)
**Parquet caching:** Every WRDS pull is cached immediately — never re-pull if cache exists
**Charts:** Chart.js (all reports) and Plotly.js (iran-iv-study)

---

## Git / Deployment Workflow

```bash
# Standard deploy
git add <specific files>
git commit -m "description"
git push
# GitHub Pages auto-deploys — live within ~60 seconds
```

**Never use `git add .` or `git add -A`** — risk of committing sensitive files.
**Never commit:** `_backups/`, `*.parquet`, `.claude/`, `__pycache__/`
**Always stage specific files by name.**

---

## Brian's Preferences & Working Style

- **No code written by Brian** — deliver complete, runnable scripts
- **One script at a time** — don't write the next script until Brian confirms the previous one ran
- **Honest reporting** — anomalies flagged, conclusions never overstated, statistical limits disclosed
- **Design changes** — never alter text content or report data; only add/modify CSS and JS
- **Backup before major changes** — `_backups/YYYY-MM-DD/` (excluded from git)
- **Concise responses** — skip preamble, get to the point
- **No emojis** unless explicitly asked
