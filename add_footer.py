import os

DISCLAIMER_TEXT = "For research purposes only. Not financial advice."

# 1. Update index.html and research/index.html (flex layout)
flex_files = [
    "index.html",
    "research/index.html"
]

for f in flex_files:
    if os.path.exists(f):
        with open(f, 'r', encoding='utf-8') as file:
            content = file.read()
        
        if DISCLAIMER_TEXT not in content:
            old_footer = '<div class="footer-copy">© Brian Liew · BSc Accounting & Finance, London School of Economics</div>'
            new_footer = f'''<div style="text-align: right;">
    <div class="footer-copy">© Brian Liew · BSc Accounting & Finance, London School of Economics</div>
    <div class="footer-copy" style="margin-top: 4px;">{DISCLAIMER_TEXT}</div>
  </div>'''
            if old_footer in content:
                content = content.replace(old_footer, new_footer)
                with open(f, 'w', encoding='utf-8') as file:
                    file.write(content)
                print(f"Updated flex footer in {f}")
            else:
                print(f"Could not find old_footer in {f}")

# 2. Update all report HTMLs and PY generators (stack layout)
stack_files = [
    "research/leveraged-etf-strategy/index.html",
    "research/short-straddle/index.html",
    "research/wheel-strategy/index.html",
    "research/0dte-gamma-trap/06_build_report.py",
    "research/congressional-herd/05_build_report.py",
    "research/earnings-vol-cycle/07_build_report.py",
    "research/etf-factor-sector-rotation-strategy/01_factor_rotation.py",
    "research/fomc-iv-study/08_build_report.py",
    "research/iran-iv-study/07_build_report.py"
]

NEW_DISCLAIMER_HTML = f'\n  <div style="text-align:center;font-size:0.75rem;color:rgba(255,255,255,0.4);margin-top:1.5rem;font-family:var(--font, \\\'Inter\\\', sans-serif);width:100%;">{DISCLAIMER_TEXT}</div>\n</footer>'

for f in stack_files:
    if os.path.exists(f):
        with open(f, 'r', encoding='utf-8') as file:
            content = file.read()
        
        if DISCLAIMER_TEXT not in content:
            content = content.replace("</footer>", NEW_DISCLAIMER_HTML)
            with open(f, 'w', encoding='utf-8') as file:
                file.write(content)
            print(f"Updated stack footer in {f}")
