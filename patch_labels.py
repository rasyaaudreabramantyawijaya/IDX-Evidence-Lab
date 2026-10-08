path = 'frontend/legacy/scripts/030-dashboard.js'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old = 'const label=`Sinyal ${pct(row.signal_wealth-1)} \u00b7 IHSG ${pct(row.market_wealth-1)} \u00b7 Selisih ${((row.signal_wealth-row.market_wealth)*100).toFixed(1)} pp \u00b7 ${row.position==null?\'Awal evaluasi\':row.position?\'Eksposur IHSG\':\'Kas\'}${row.signal_date?\' \u00b7 Observasi sinyal \'+row.signal_date:\'\'}`;'
new = 'const label=`<ul style=\"margin:2px 0 0;padding-left:14px\"><li>Sinyal: <strong style=\"color:var(--up,#22c07a)\">${pct(row.signal_wealth-1)}</strong></li><li>IHSG: <strong style=\"color:var(--link,#5b8cff)\">${pct(row.market_wealth-1)}</strong></li><li>Selisih: <strong>${((row.signal_wealth-row.market_wealth)*100).toFixed(1)} pp</strong></li><li>Posisi: <strong>${row.position==null?\'Awal evaluasi\':row.position?\'Eksposur IHSG\':\'Kas\'}</strong></li>${row.signal_date?\'<li>Observasi sinyal: <strong>\'+row.signal_date+\'</strong></li>\':\'\'}</ul>`;'

if old in content:
    content = content.replace(old, new)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Dashboard label replaced")
else:
    print("Dashboard label NOT found")

# Fix button link for news
path2 = 'frontend/legacy/scripts/030-dashboard.js'
with open(path2, 'r', encoding='utf-8') as f:
    content2 = f.read()
# Replace <button type="button" class="dashboard-news-open" data-action="open-news" data-news-title="${escapeHTML(item.title)}">${escapeHTML(item.title)}</button>
# with <a href="${escapeHTML(item.source)}" target="_blank" rel="noopener noreferrer">${escapeHTML(item.title)}</a>
old2 = '<button type=\"button\" class=\"dashboard-news-open\" data-action=\"open-news\" data-news-title=\"${escapeHTML(item.title)}\">${escapeHTML(item.title)}</button>'
new2 = '<a href=\"${escapeHTML(item.source)}\" target=\"_blank\" rel=\"noopener noreferrer\">${escapeHTML(item.title)}</a>'
if old2 in content2:
    content2 = content2.replace(old2, new2)
    with open(path2, 'w', encoding='utf-8') as f:
        f.write(content2)
    print("News link replaced")
else:
    print("News link NOT found")
