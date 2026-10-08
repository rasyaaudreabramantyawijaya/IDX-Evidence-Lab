      function sectorHeatmapPanel(){
        const data=dashboardData.sectorHeatmap;
        if(!data)return section('Sector heatmap','<p class="note">Memuat hasil dari snapshot Sectors.app lokal…</p>');
        const monthly=data.monthly_heatmap||{};
        const rows=Array.isArray(monthly.sectors)?monthly.sectors:[];
        const dates=Array.isArray(monthly.dates)?monthly.dates:[];
        const scale=Math.max(Number(monthly.color_scale_abs_pct)||0.25,0.25);
        function colorForReturn(value){
          const t=Math.max(-1,Math.min(1,value/scale));
          const stops=t<0?[[34,34,40],[236,123,123],[217,58,71],[122,31,34]]:[[34,34,40],[63,191,127],[29,107,67]];
          const p=Math.abs(t)*(stops.length-1),i=Math.min(stops.length-2,Math.floor(p)),f=p-i;
          return 'rgb('+stops[i].map(function(channel,index){return Math.round(channel+(stops[i+1][index]-channel)*f)}).join(',')+')';
        }
        const bodyRows=rows.map(function(row,rowIndex){
          const label=String(row.sector||'Sector');
          const count=Number(row.universe_count)||0;
          const note=count+' emiten'+(row.single_issuer_proxy?' · proxy KLBF':'');
          const cells=dates.map(function(day,dayIndex){
            const cell=(row.cells||[])[dayIndex]||{};
            const value=cell.return_pct;
            const measured=Number.isFinite(value)&&cell.data_quality!=='INSUFFICIENT_EVIDENCE';
            const pct=measured?(value>0?'+':'')+Number(value).toFixed(2)+'%':'Not Available';
            const coverage=Number(cell.observation_count||0)+'/'+Number(cell.universe_count||count);
            const aria=label+' · '+day+' · '+pct+' · '+coverage+' emiten terukur';
            return '<td><button type="button" class="sector-heatmap-cell'+(measured?'':' unavailable')+'" data-sector-row="'+rowIndex+'" data-sector-day="'+dayIndex+'" '+(measured?'style="background:'+colorForReturn(Number(value))+'" ':'')+'aria-label="'+escapeHTML(aria)+'"></button></td>';
          }).join('');
          return '<tr><th scope="row" class="sector-row-label"><strong>'+escapeHTML(label)+'</strong><small>'+escapeHTML(note)+'</small></th>'+cells+'</tr>';
        }).join('');
        const dateAxis=dates.map(function(day,index){
          const firstOfMonth=day.slice(8)==='01';
          const show=index===0||index===dates.length-1||firstOfMonth||index%4===0;
          const label=show?(firstOfMonth||index===0?day.slice(8)+' '+(day.slice(5,7)==='08'?'Agu':'Sep'):day.slice(8)):'';
          return '<th scope="col" aria-label="'+escapeHTML(day)+'">'+escapeHTML(label)+'</th>';
        }).join('');
        const grid=dates.length&&rows.length?
          '<div class="sector-heatmap-shell"><div class="sector-heatmap-kicker"><span>Sector Performance · Daily Close</span><span>'+dates.length+' sesi · '+rows.length+' sektor</span></div>'+
          '<div class="sector-heatmap-scroll"><table class="sector-heatmap-table" aria-label="Heatmap return harian sektor LQ45"><colgroup><col><col span="'+dates.length+'"></colgroup><tbody>'+bodyRows+'</tbody><tfoot><tr><th scope="row">Date</th>'+dateAxis+'</tr></tfoot></table></div>'+
          '<div class="sector-heatmap-legend"><span>Positive</span><i aria-hidden="true"></i><span>Negative</span></div><p class="sector-heatmap-legend-note">Abu-abu ≈ 0% · skala simetris persentil ke-95 return harian</p><div class="sector-heatmap-tooltip" role="status" hidden></div></div>':
          '<div class="dashboard-placeholder"><div><strong>Heatmap belum tersedia</strong>Snapshot lokal belum memiliki pasangan harga harian yang cukup untuk jendela bulanan.</div></div>';
        const description='<p class="note sector-heatmap-intro">Return harian equal-weighted dari harga penutupan emiten LQ45 · '+escapeHTML(monthly.start_date||'—')+' s.d. '+escapeHTML(monthly.end_date||'—')+' ('+dates.length+' sesi bursa dalam '+escapeHTML(monthly.window_calendar_days||30)+' hari kalender). Bukan indeks sektor resmi IDX. Arahkan atau fokuskan kotak untuk tanggal, return, dan cakupan. Healthcare adalah proxy KLBF satu emiten. Sumber: '+escapeHTML(data.snapshot_count||0)+' file snapshot lokal Sectors.app.</p>';
        return section('Sector Heatmap · 1-Month Daily Performance',description+grid);
      }
      function mountSectorHeatmap(){
        const shell=main.querySelector('.sector-heatmap-shell');
        if(!shell)return;
        const tooltip=shell.querySelector('.sector-heatmap-tooltip');
        const rows=dashboardData.sectorHeatmap?.monthly_heatmap?.sectors||[];
        let active=null;
        let tooltipWidth=0,tooltipHeight=0;
        function hide(){tooltip.hidden=true;active=null}
        function position(x,y){
          const margin=12;
          tooltip.style.left=Math.max(margin,Math.min(x+14,window.innerWidth-tooltipWidth-margin))+'px';
          tooltip.style.top=Math.max(margin,Math.min(y+14,window.innerHeight-tooltipHeight-margin))+'px';
        }
        function show(button,x,y){
          const row=rows[Number(button.dataset.sectorRow)];
          const cell=row?.cells?.[Number(button.dataset.sectorDay)];
          if(!row||!cell){hide();return}
          if(active!==button){
            const value=cell.return_pct;
            const measured=Number.isFinite(value)&&cell.data_quality!=='INSUFFICIENT_EVIDENCE';
            const pct=measured?(value>0?'+':'')+Number(value).toFixed(2)+'%':'Not Available';
            const status=cell.data_quality||'MISSING';
            const coverage=Number(cell.observation_count||0)+'/'+Number(cell.universe_count||row.universe_count||0)+' emiten terukur';
            const extra=row.single_issuer_proxy?' · proxy KLBF':'';
            const members=(row.member_tickers||[]).join(', ');
            const tone=Number(value)<0?'negative':Number(value)>0?'positive':'neutral';
            tooltip.innerHTML='<strong>'+escapeHTML(row.sector)+'</strong><small>'+escapeHTML(cell.date||'—')+'</small><b class="'+tone+'">'+escapeHTML(pct)+'</b><small>'+escapeHTML(coverage+extra+' · '+status)+'</small>'+(members?'<small>'+escapeHTML(members)+'</small>':'');
            tooltip.hidden=false;
            tooltipWidth=tooltip.offsetWidth;
            tooltipHeight=tooltip.offsetHeight;
            active=button;
          }
          position(x,y);
        }
        shell.addEventListener('pointerover',function(event){const button=event.target.closest('.sector-heatmap-cell');if(button)show(button,event.clientX,event.clientY)});
        shell.addEventListener('pointermove',function(event){const button=event.target.closest('.sector-heatmap-cell');if(button)show(button,event.clientX,event.clientY);else hide()});
        shell.addEventListener('pointerleave',hide);
        shell.addEventListener('focusin',function(event){const button=event.target.closest('.sector-heatmap-cell');if(!button)return;const rect=button.getBoundingClientRect();show(button,rect.right,rect.top)});
        shell.addEventListener('focusout',hide);
      }
      async function loadSectorHeatmap(){if(sectorHeatmapLoading||dashboardData.sectorHeatmap)return;sectorHeatmapLoading=true;try{const response=await fetch('/api/sector-heatmap',{cache:'no-store'});if(!response.ok)throw new Error('HTTP '+response.status);dashboardData.sectorHeatmap=await response.json()}catch(_error){dashboardData.sectorHeatmap={data_quality:'MISSING',sectors:[],issues:['Tidak dapat membaca endpoint data lokal.']}}finally{sectorHeatmapLoading=false;if(page==='market')render()}}
      function newsUniverse(){loadNewsUniverse();const articles=newsData?.articles||[];const matches=articles.filter(function(item){return(!newsFilters.sector||item.sector===newsFilters.sector)&&(!newsFilters.symbol||item.symbols.some(function(s){return s.toLowerCase().includes(newsFilters.symbol.toLowerCase())}))&&(!newsFilters.date||item.timestamp.slice(0,10)===newsFilters.date)});const selected=articles.find(function(item){return item.news_id===selectedNewsId});const visible=newsExpanded?matches:matches.slice(0,10);const sectors=[...new Set(articles.map(function(a){return a.sector}).filter(Boolean))].sort();const cards=visible.map(function(item){return '<button class="news-item '+(item.news_id===selectedNewsId?'selected':'')+'" data-action="select-news" data-news-id="'+escapeHTML(item.news_id)+'"><strong>'+escapeHTML(item.title)+'</strong><small>'+escapeHTML(item.timestamp)+' · '+escapeHTML(item.source.replace('https://',''))+' · '+escapeHTML(item.symbols.join(', ')||item.sector||'IDX')+'</small></button>'}).join('');const detail=selected?'<h3>'+escapeHTML(selected.title)+'</h3><p class="note">'+escapeHTML(selected.timestamp)+' · '+escapeHTML(selected.sector||'Sektor tidak tersedia')+' · '+escapeHTML(selected.symbols.join(', ')||'Tidak ada ticker tertaut')+'</p><p class="news-story-body">'+escapeHTML(selected.body||'Isi artikel tidak tersedia pada snapshot lokal.')+'</p><a class="action" href="'+escapeHTML(selected.source)+'" target="_blank" rel="noopener noreferrer">Buka sumber asli ↗</a>':'<p class="note">Pilih berita dari daftar untuk membaca isi dan menampilkan peta di samping.</p>';const filterHtml='<div class="filters"><select class="filter news-filter" data-news-filter="sector" aria-label="Filter sektor"><option value="">All Sectors</option>'+sectors.map(function(s){return '<option value="'+escapeHTML(s)+'" '+(newsFilters.sector===s?'selected':'')+'>'+escapeHTML(s)+'</option>'}).join('')+'</select><input class="filter news-filter" data-news-filter="symbol" value="'+escapeHTML(newsFilters.symbol)+'" placeholder="Ticker / symbol" aria-label="Filter ticker"><input class="filter news-filter" data-news-filter="date" type="date" value="'+escapeHTML(newsFilters.date)+'" aria-label="Filter tanggal"></div>';const listHtml='<div class="news-layout"><div>'+filterHtml+'<div class="news-items">'+(cards||'<p class="note">Tidak ada berita yang cocok dengan filter atau belum ada snapshot lokal.</p>')+'</div>'+(matches.length>10?btn(newsExpanded?'Tampilkan lebih sedikit':'Tampilkan semua ('+matches.length+')','toggle-news-list'):'')+'</div><div>'+section('News Detail',detail,selected?'Sumber tertaut':'Pilih berita')+section('Root-cause map · 3D','<div class="news-graph"><div class="news-root"><strong>'+(selected?escapeHTML(selected.title):'Pilih satu berita')+'</strong><p class="note">PENDING_MODEL_APPROVAL · hubungan sebab-akibat belum dihasilkan atau diverifikasi.</p></div></div><p class="note">Graph hanya akan menampilkan cabang bersumber setelah inferensi ditinjau; judul berita bukan bukti kausalitas.</p>',selected?'Terpilih · '+escapeHTML(selected.news_id):'Menunggu pilihan')+'</div></div>';return pageHead('News Universe','Berita dari snapshot lokal Sectors.app · bukan feed real-time')+section('Top 5 · You Must Know in 10 Minutes','<p><span class="state warn">PENDING_MODEL_APPROVAL</span></p><p class="note">Daftar ranking belum tersedia karena belum ada persetujuan terpisah untuk inferensi. Tidak ada berita yang dilabeli Top 5 secara otomatis.</p>','Belum diranking','news-briefing')+section('All Local News',listHtml,(newsData?.articles||[]).length+' artikel · '+escapeHTML(newsData?.data_quality||'memuat'))}
      function selectNewsStory(newsId){const article=(newsData?.articles||[]).find(function(item){return item.news_id===newsId});if(!article)return;selectedNewsId=newsId;newsGraph.news_id=newsId;newsGraph.nodes=[{id:newsId,label:article.title,kind:'source_article',source:article.source}];newsGraph.edges=[];newsGraph.status='PENDING_MODEL_APPROVAL';newsGraph.provenance=[{source_file:article.source_file,source:article.source,timestamp:article.timestamp}];render();const graph=root.querySelector('.news-graph');if(graph)graph.dataset.graphNewsId=newsGraph.news_id}
      async function loadNewsUniverse(){
        if(newsLoading||newsData)return;
        newsLoading=true;
        try{
          const response=await fetch('/api/news-universe',{cache:'no-store'});
          if(!response.ok)throw new Error('local API HTTP '+response.status);
          newsData=await response.json();
        }catch(apiError){
          try{
            const response=await fetch('/docs/prototypes/news-universe.json',{cache:'no-store'});
            if(!response.ok)throw new Error('static export HTTP '+response.status);
            newsData=await response.json();
            newsData.runtime_source='verified static snapshot';
          }catch(staticError){
            newsData={data_quality:'MISSING',articles:[],issues:['Snapshot berita tidak ditemukan. Jalankan scripts/export_news_universe_static.py untuk Live Server, atau gunakan server aplikasi lokal.']};
          }
        }finally{
          newsLoading=false;
          const availableDates=new Set((newsData?.articles||[]).map(item=>String(item.timestamp||'').slice(0,10)));
          if(newsFilters.date&&!availableDates.has(newsFilters.date))newsFilters.date='';
          if(page==='news-universe')render();
        }
      }
