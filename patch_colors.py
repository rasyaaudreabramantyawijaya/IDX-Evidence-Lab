import os

def patch_file(path, replacements):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        for old, new in replacements:
            content = content.replace(old, new)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Patched {path}")
    except Exception as e:
        print(f"Error on {path}: {e}")

# 030-dashboard.js
patch_file('frontend/legacy/scripts/030-dashboard.js', [
    ('#36c99a', '#22c07a'), # IHSG
    ("color=z<0?'#e4777b':'#49c99e'", "color=z<0?'var(--down,#f0475a)':'var(--up,#22c07a)'"), # Unusual Flow
    ('var(--cyan)', 'var(--link,#5b8cff)'), # Flow KPI
    ('#62bcf7', 'var(--link,#5b8cff)'), # Cap KPI
    ('#8192a7', 'var(--ink-muted,#8a8f98)'), # Cap empty
    ('#44cdb4', 'var(--up,#22c07a)'), # Signal up
    ('#ed8589', 'var(--down,#f0475a)'), # Signal down
    ('#6aa9ed', 'var(--link,#5b8cff)'), # IHSG baseline
    ('#7c92a6', 'var(--ink-muted,#8a8f98)'), # Signal grid
    ('#284054', 'var(--line,#2a2a30)'), # Signal zero
    ('#9aacbf', 'var(--ink-muted,#8a8f98)') # Signal ticks
])

# 120-market-overview-screener.js
patch_file('frontend/legacy/scripts/120-market-overview-screener.js', [
    ('#aab6c2', 'var(--ink-muted,#8a8f98)'),
    ('#405165', 'var(--line-strong,#4a4e57)'),
    ('#a5b5c8', 'var(--ink-muted,#8a8f98)'),
    ('#dbe7f3', 'var(--ink,#f4f5f7)'),
    ('#d7e1ed', 'var(--ink,#f4f5f7)'),
    ('#ff9d36', 'var(--price,#f2c14e)'),
    ('#08111d', 'var(--bg-000,#050507)'),
    ('stroke-width="1.25"', 'stroke-width="2"'),
    ('r="4"', 'r="5.5"')
])

# 130-portfolio-lab-factor-zoo.js
patch_file('frontend/legacy/scripts/130-portfolio-lab-factor-zoo.js', [
    ('#6aa9ed', 'var(--link,#5b8cff)'), # Market return
    ('#44cdb4', 'var(--up,#22c07a)'),   # Long return
    ('#ed8589', 'var(--down,#f0475a)'), # Short return
    ('#7c92a6', 'var(--ink-muted,#8a8f98)'),
    ('#284054', 'var(--line,#2a2a30)'),
    ('#9aacbf', 'var(--ink-muted,#8a8f98)')
])

# 100-news-graph-history.js
patch_file('frontend/legacy/scripts/100-news-graph-history.js', [
    ('#9ab2c8', 'var(--ink-muted,#8a8f98)'),
    ('#233547', 'var(--line,#2a2a30)'),
    ('#466887', 'var(--line-strong,#4a4e57)'),
    ('#6aa9ed', 'var(--link,#5b8cff)'),
    ('#44cdb4', 'var(--up,#22c07a)'),
    ('#0c1a29', 'var(--bg-100,#0e0e11)')
])
