      function toast(msg){const t=root.querySelector('#idxel-toast');t.textContent=msg;t.classList.remove('hidden');clearTimeout(toast.timer);toast.timer=setTimeout(()=>t.classList.add('hidden'),2300)}
      function closeSearchResults(){clearTimeout(searchTimer);searchSequence++;if(searchController)searchController.abort();root.querySelector('#idxel-search-results').classList.add('hidden')}
      function newsTopicMatches(item){
        const topics={acquisition:/akuisisi|acquisition|acquire|takeover|pengambilalihan|tender offer/i,merger:/merger|penggabungan/i,dividend:/dividen|dividend/i,rights:/hmetd|rights? issue|penambahan modal/i,buyback:/buyback|pembelian kembali/i};
        return !newsFilters.topic||Boolean(topics[newsFilters.topic]?.test((item.title||'')+' '+(item.body||'')));
      }
      function groupNewsCards(items){
        const groups=new Map();items.forEach(item=>{const symbols=(item.symbols||[]).filter(s=>!newsFilters.symbol||s.toUpperCase().replace('.JK','')===newsFilters.symbol.toUpperCase());(symbols.length?symbols:['Tidak ada ticker tertaut']).forEach(symbol=>{if(!groups.has(symbol))groups.set(symbol,[]);groups.get(symbol).push(item)})});
        return Array.from(groups).sort((a,b)=>a[0].localeCompare(b[0])).map(([symbol,articles])=>'<div class="news-ticker-group"><h3>'+escapeHTML(symbol)+' · '+articles.length+' berita</h3>'+articles.map(item=>'<button class="news-item" data-action="select-news" data-news-id="'+escapeHTML(item.news_id)+'"><strong>'+escapeHTML(item.title)+'</strong><small>'+escapeHTML(item.timestamp)+' · '+escapeHTML(item.source||'Snapshot lokal')+'</small></button>').join('')+'</div>').join('');
      }
      function addSearchText(parent,tag,text,className){const el=document.createElement(tag);if(className)el.className=className;el.textContent=String(text||'');parent.appendChild(el);return el}
      let searchSequence=0,searchTimer,searchController;
      const searchPages=[['dashboard','Dashboard','ringkasan pasar IHSG'],['screener','Screener','filter saham sektor'],['watchlist','Watchlist','pantauan'],['studies','Studies','studi dossier'],['research','Issuer Research','akuisisi aksi korporasi'],['portfolio-lab','Portfolio Lab','portofolio optimasi alokasi risiko faktor simulasi'],['market','Market overview','IHSG sektor heatmap EVT'],['news-universe','News Universe','berita'],['sources','Sumber & metode PDF','hukum dokumen provenance'],['settings','Settings','pengaturan koneksi OpenRouter']];
      let taskNavigation=null,taskScreenMode='',recentAppQueries=[];
      function taskScreenerSection(){
        if(!taskScreenMode)return '';
        const data=factorZooState.data,key=taskScreenMode==='value'?'value':'low_volatility';
        const explanation=key==='value'?'Valuasi relatif: earnings/dividend yield. Bukan estimasi nilai intrinsik atau kepastian undervalued.':'Karakteristik risiko rendah: beta IHSG dan volatilitas residual harian. Bukan volatilitas realized total atau prediksi risiko.';
        if(!data)return section('Filter Results '+(key==='value'?'valuasi relatif':'risiko rendah'),'<p class="note">'+escapeHTML(factorZooState.error||'Memuat artefak faktor lokal…')+'</p>');
        const records=data.records.filter(r=>r.scores?.[key]?.status==='AVAILABLE'&&Number.isFinite(r.scores[key].score)&&(!screenerFilters.query||r.ticker===screenerFilters.query)).sort((a,b)=>b.scores[key].score-a.scores[key].score);
        return section(key==='value'?'Valuasi relatif · skor tertinggi':'Risiko rendah · proxy beta/residual','<p class="note">'+explanation+' Harga as-of: '+escapeHTML(data.as_of?.price||'—')+'; laporan: '+escapeHTML((data.as_of?.company_report_dates||[]).join(', '))+' · '+escapeHTML(data.formula_version)+' · hanya skor lengkap; '+records.length+' emiten. Universe quality: '+escapeHTML(data.universe?.quality||'UNKNOWN')+'.</p><div class="table-wrap"><table><thead><tr><th>Ticker</th><th>Relative Score</th><th>Beta IHSG</th><th>Daily Residual Volatility</th><th>Earnings yield</th></tr></thead><tbody>'+records.map(r=>'<tr data-action="open-issuer" data-ticker="'+escapeHTML(r.ticker)+'"><td>'+escapeHTML(r.ticker)+'</td><td>'+r.scores[key].score.toFixed(3)+'</td><td>'+taskMetric(r.components?.beta_ihsg?.value)+'</td><td>'+taskMetric(r.components?.idiosyncratic_volatility?.value,true)+'</td><td>'+taskMetric(r.components?.earnings_yield?.value,true)+'</td></tr>').join('')+'</tbody></table></div><p class="note">Snapshot Sectors.app; bukan rekomendasi. Skor parsial tidak dimasukkan. Provenance dan audit artefak tersedia di Portfolio Lab.</p>','LOKAL · DESKRIPTIF');
      }
      function taskMetric(value,percent=false){return Number.isFinite(value)?(value*(percent?100:1)).toFixed(3)+(percent?'%':''):'—'}
      function applyWorkspacePlan(plan,query,provider,notice){
        if(!plan||!validPages.has(plan.page))throw new Error('Tujuan workspace tidak valid');
        const symbols=(plan.tickers||[]).filter(s=>lq45Tickers.includes(s));
        page=plan.page;taskNavigation={page,query,provider:provider||'Local',notice:notice||''};taskScreenMode='';
        if(page==='issuer'&&symbols.length){ticker=symbols[0];issuerTab='Overview';dossierReport=false;dossierEvent=''}
        if(page==='screener'){taskScreenMode=['low_volatility','value'].includes(plan.screen_mode)?plan.screen_mode:'';screenerFilters={sector:'',regime:'',query:symbols[0]||''};if(taskScreenMode)loadFactorZooData()}
        if(page==='news-universe'){newsFilters={sector:'',date:'',symbol:symbols[0]||'',topic:plan.news_topic||'',grouped:true};selectedNewsId=null;newsGraph={nodes:[],edges:[]}}
        if(page==='studies'){studySector='';studyTargets=symbols;studySearchText=query;const allowed=new Set(studyCatalog.map(w=>w.id));studyPanels=(plan.widgets||[]).filter(w=>allowed.has(w)).map((w,i)=>makeStudyPanel(w,i));if(!studyPanels.length)studyPanels=[makeStudyPanel('evidence_trace',0)];autoArrangeStudyPanels()}
        if(page==='portfolio-lab'&&symbols.length)portfolioState.selected=symbols;
        if(page==='research'){if(researchChat.loading){++researchChat.requestGeneration;researchChat={sessionId:null,revision:0,messages:[],context:null,loading:false,error:null,requestGeneration:researchChat.requestGeneration}}researchQuestion=query;if(symbols.length)researchTicker=symbols[0]}
        render();
        if(page==='research')sendResearchMessage(query);
        if(page==='studies'){studyRunner.invalidate();studyRunner.runAll(studyPanels)}
      }
      async function navigateFromSearch(query){
        const clean=String(query||'').trim();if(!clean)return;closeSearchResults();const sequence=searchSequence;
        const symbol=clean.toUpperCase();if(lq45Tickers.includes(symbol)){applyWorkspacePlan({page:'issuer',tickers:[symbol]},clean,'Local');return}
        const input=root.querySelector('.search');input.setAttribute('aria-busy','true');toast(researchUseModel?'Memahami tujuan dengan OpenRouter dan aturan lokal…':'Memahami tujuan dengan aturan lokal…');
        const controller=new AbortController();searchController=controller;const timeout=setTimeout(()=>controller.abort(),30000);
        try{const response=await fetch('/api/search',{method:'POST',headers:{'Content-Type':'application/json'},signal:controller.signal,body:JSON.stringify({query:clean,use_model:researchUseModel===true,navigate:true,history:recentAppQueries.slice(-6)})});const payload=await response.json();if(!response.ok)throw new Error(payload.error||'Navigasi gagal');if(sequence!==searchSequence)return;recentAppQueries.push(clean);recentAppQueries=recentAppQueries.slice(-6);applyWorkspacePlan(payload.navigation,clean,payload.plan?.provider,payload.notice)}
        catch(error){if(sequence===searchSequence)toast(error.name==='AbortError'?'OpenRouter terlalu lama. Coba kembali.':error.message)}finally{clearTimeout(timeout);if(sequence===searchSequence)input.removeAttribute('aria-busy')}
      }
      function searchLink(parent,label,destination,symbol){
        const button=document.createElement('button');button.type='button';button.className='search-link';button.textContent=label;
        button.addEventListener('click',()=>{closeSearchResults();page=destination;if(symbol){ticker=symbol;issuerTab='Overview';dossierReport=false;dossierEvent=''}render()});parent.appendChild(button);
      }
      async function submitUnifiedSearch(query,useModel=false){
        const clean=String(query||'').trim(),sequence=++searchSequence;
        if(searchController)searchController.abort();
        const panel=root.querySelector('#idxel-search-results');panel.replaceChildren();
        if(!clean){panel.classList.add('hidden');return}panel.classList.remove('hidden');
        const head=document.createElement('div');head.className='search-results-head';addSearchText(head,'strong','Cari di prototype');
        const status=addSearchText(head,'span','Menelusuri indeks lokal…','search-status');
        const close=document.createElement('button');close.type='button';close.className='action ghost search-close';close.textContent='Close';close.addEventListener('click',closeSearchResults);head.appendChild(close);panel.appendChild(head);
        const normalized=clean.toLocaleLowerCase(),shortcuts=document.createElement('div');
        screenerRows().filter(item=>((item.ticker||'')+' '+(item.company||'')).toLocaleLowerCase().includes(normalized)).slice(0,6).forEach(item=>searchLink(shortcuts,item.ticker+' · '+item.company,'issuer',item.ticker));
        searchPages.filter(item=>item.slice(1).join(' ').toLocaleLowerCase().includes(normalized)).forEach(item=>searchLink(shortcuts,item[1],item[0]));panel.appendChild(shortcuts);
        const results=document.createElement('div');panel.appendChild(results);
        searchController=new AbortController();const controller=searchController,timeout=setTimeout(()=>controller.abort(),30000);
        async function retrieve(model){
          const response=await fetch('/api/search',{method:'POST',headers:{'Content-Type':'application/json'},signal:controller.signal,body:JSON.stringify({query:clean,use_model:model})});
          const payload=await response.json();if(!response.ok)throw new Error(payload.error||'Pencarian belum tersedia');return payload;
        }
        function show(payload){
          if(sequence!==searchSequence||panel.classList.contains('hidden'))return;results.replaceChildren();
          status.textContent=(payload.plan?.provider==='OpenRouter'?'OpenRouter aktif':'Indeks lokal')+' · '+payload.results.length+' hasil';
          payload.results.forEach(item=>{const card=document.createElement('article');card.className='search-result';if(item.page&&validPages.has(item.page))searchLink(card,item.title,item.page,item.ticker);else addSearchText(card,'h3',item.title);addSearchText(card,'p',item.snippet);addSearchText(card,'small',item.source_class+' · '+item.source_id);results.appendChild(card)});
          if(!payload.results.length&&!shortcuts.childElementCount)addSearchText(results,'p','Belum ada kecocokan pada snapshot dan dokumen yang terindeks. Coba ticker, halaman, atau istilah yang lebih spesifik.','search-empty');
          addSearchText(results,'p',payload.notice,'search-empty');
        }
        try{
          show(await retrieve(false));
          if(useModel&&!lq45Tickers.includes(clean.toUpperCase())&&sequence===searchSequence&&!panel.classList.contains('hidden')){
            status.textContent='Hasil lokal tersedia · OpenRouter memahami pertanyaan…';show(await retrieve(true));
          }
        }catch(error){if(sequence!==searchSequence||panel.classList.contains('hidden'))return;status.textContent='Hasil lokal / pintasan tetap tersedia';addSearchText(results,'p',error.name==='AbortError'?'Permintaan terlalu lama; coba lagi.':error.message,'search-empty')}
        finally{clearTimeout(timeout)}
      }
      function openModal(title,copy,kind){const m=root.querySelector('#idxel-modal');m.dataset.kind=kind||'generic';m.querySelector('#idxel-modal-title').textContent=title;m.querySelector('#idxel-modal-copy').textContent=copy;m.classList.remove('hidden')}
      function closeModal(){root.querySelector('#idxel-modal').classList.add('hidden')}
      root.addEventListener('change',e=>{const input=e.target.closest('[data-news-filter]');if(!input)return;newsFilters[input.dataset.newsFilter]=input.value;render()});
      root.addEventListener('click',e=>{if(e.target.id==='watchlist-picker'){e.target.classList.add('hidden');return}const b=e.target.closest('[data-action],[data-page]');if(!b)return;
        if(b.dataset.page){page=b.dataset.page;render();return}
        const a=b.dataset.action;
        if(a==='watchlist-open-picker'){openWatchlistPicker();return}
        if(a==='watchlist-close-picker'||(b.id==='watchlist-picker'&&e.target===b)){root.querySelector('#watchlist-picker').classList.add('hidden');return}
        if(a==='watchlist-toggle'){const code=b.dataset.ticker;if(watchlistTickers.includes(code))watchlistTickers=watchlistTickers.filter(item=>item!==code);else watchlistTickers.push(code);watchlistPersist();if(page==='watchlist')render();renderWatchlistPicker();return}
        if(a==='watchlist-remove'){watchlistTickers=watchlistTickers.filter(item=>item!==b.dataset.ticker);watchlistPersist();render();return}
        if(a==='watchlist-sort'){const key=b.dataset.sortKey;if(watchlistSort.key===key)watchlistSort.direction=watchlistSort.direction==='asc'?'desc':'asc';else watchlistSort={key,direction:'asc'};render();return}
        if(a==='portfolio-toggle-ticker'){const code=b.dataset.portfolioTicker;portfolioState.selected=portfolioState.selected.includes(code)?portfolioState.selected.filter(t=>t!==code):[...portfolioState.selected,code];invalidatePortfolioResult();render();return}
        if(a==='portfolio-profile'){portfolioState.profile=b.dataset.portfolioProfile;invalidatePortfolioResult();render();return}
        if(a==='portfolio-retry-catalog'){portfolioState.catalogAttempted=false;portfolioState.catalogError=null;loadPortfolioData();render();return}
        if(a==='portfolio-run'){if(!portfolioState.selected.length){portfolioState.error='Pilih setidaknya satu emiten LQ45.';render();return}runPortfolioAnalysis({...portfolioState});return}
        if(a==='factor-zoo-retry'){factorZooState.attempted=false;factorZooState.error=null;loadFactorZooData();render();return}
        if(a==='history-back'){travelViewHistory(-1);return}if(a==='history-forward'){travelViewHistory(1);return}
        if(a==='select-news'){selectNewsStory(b.dataset.newsId);return}if(a==='open-news'){openNewsFromDashboard(b.dataset.newsTitle);return}if(a==='toggle-news-list'){newsExpanded=!newsExpanded;render();return}
        if(a==='screener-reset'){screenerFilters={sector:'',regime:'',query:''};render();return}
        if(a==='news-zoom-in'||a==='news-zoom-out'){graphView.zoom=Math.max(.35,Math.min(2.5,graphView.zoom+(a==='news-zoom-in'?.15:-.15)));drawNewsGraph(root.querySelector('.news-graph canvas'),newsGraph);return}
        if(a==='news-graph-reset'){graphView={rotateX:-.25,rotateY:.45,zoom:1,graphOffsetX:0,graphOffsetY:0,panMode:false};render();return}
        if(a==='news-pan-toggle'){graphView.panMode=!graphView.panMode;b.setAttribute('aria-pressed',String(graphView.panMode));b.textContent='Pan: '+(graphView.panMode?'on':'off');return}
        if(a==='news-tree-toggle'){const tree=root.querySelector('.news-layout details');if(tree)tree.open=!tree.open;return}
        if(a==='issuer-range'){issuerPriceRange=b.dataset.range;render();return}
        if(a==='dossier-cost'){dossierCost=Number(b.dataset.cost);render();return}
        if(a==='broker-window'){const n=Number(b.dataset.window);if([1,5,20,0].includes(n))dossierBrokerWindow=n;render();return}
        if(a==='dossier-report'){dossierReport=true;render();return}
        if(a==='dossier-report-close'){dossierReport=false;render();return}
        if(a==='refresh-dashboard'){refreshDashboardData();return}
        if(a==='open-issuer'){ticker=b.dataset.ticker||'BBCA';page='issuer';issuerTab='Overview';dossierReport=false;dossierEvent='';render();return}
        if(a==='go-screener'||a==='open-screener'){page='screener';render();return}if(a==='go-market'){page='market';render();return}if(a==='go-library'||a==='go-ledger'||a==='go-sources'){page='sources';sourceReport=null;render();loadSourceReport();return}if(a==='go-studies'){page='studies';render();return}if(a==='go-research'){page='research';render();return}
        if(a==='send-research-chat'){sendResearchMessage(root.querySelector('#research-question')?.value);return}
        if(a==='research-add-file'){root.querySelector('#research-files')?.click();return}
        if(a==='research-remove-file'){if(researchChat.loading||researchUploading)return;const id=e.target.closest('[data-action]').dataset.attachmentId;(async()=>{try{await researchPost('/api/research-attachments',{session_id:researchChat.sessionId,remove_id:id});researchAttachments=researchAttachments.filter(f=>f.id!==id)}catch(error){researchChat.error='Gagal melepas lampiran: '+error.message}render()})();return}
        if(a==='cancel-research-chat'){cancelResearchMessage();return}
        if(a==='new-research-session'){newResearchSession();return}
        if(a==='research-mode'){researchUseModel=b.dataset.researchMode==='agent';render();return}
        if(a==='run-issuer-research'){sendResearchMessage(root.querySelector('#research-question')?.value);return}
        if(a==='research-prompt'){const field=root.querySelector('#research-question');if(field)field.value=b.dataset.question||'';runIssuerResearch(b.dataset.question||'');return}
        if(a==='load-source-report'){sourceReport=null;loadSourceReport();return}
        if(a==='print-source-report'){root.querySelectorAll('.source-manifest').forEach(function(item){item.open=true;mountSourceManifest(item)});window.addEventListener('afterprint',function(){root.querySelectorAll('.source-manifest').forEach(function(item){item.open=false;item.dataset.loaded='false';const host=item.querySelector('.source-manifest-table');if(host){const note=document.createElement('p');note.className='note';note.textContent='Rincian akan dimuat saat lampiran dibuka.';host.replaceChildren(note)}})},{once:true});requestAnimationFrame(function(){window.print()});return}
        if(a==='issuer-tab'){issuerTab=b.dataset.tab;page='issuer';dossierReport=false;render();main.scrollTop=0;return}
        if(a==='tab-flow'){page='issuer';issuerTab='Flow';render();return}if(a==='tab-evidence'){page='issuer';issuerTab='Evidence';render();return}
        if(a==='watch'){if(!watchlistTickers.includes(ticker)){watchlistTickers.push(ticker);watchlistPersist();toast(ticker+' ditambahkan ke Watchlist.')}else toast(ticker+' sudah ada di Watchlist.');return}if(a==='save-study'||a==='new-study'){openModal(a==='save-study'?'Simpan study':'Buat study','Study akan menyimpan filter dan definisi cohort. Hasil analisis belum otomatis tervalidasi.','save');return}
        if(a==='build-study'){buildStudyFromQuery(root.querySelector('#study-query-input').value);return}
        if(a==='run-study-panel'){const panel=studyPanels.find(p=>p.id===b.dataset.panelId);if(panel)studyRunner.run(panel);return}
        if(a==='run-all-studies'){studyRunner.runAll(studyPanels);return}
        if(a==='cancel-study-panel'){studyRunner.cancel(b.dataset.panelId);return}
        if(a==='study-show-all'){const id=b.closest('[data-study-panel]')?.dataset.studyPanel;const panel=studyPanels.find(p=>p.id===id);if(panel){panel.showAll=true;render()}return}
        if(a==='preview-custom-formula'){toast('Preview: '+studyCustomTransform+'('+studyCustomField+', '+studyWindow+' sesi). Hanya definisi; belum dihitung.');return}
        if(a==='add-study-panel'){addStudyPanel(b.dataset.panel);return}
        if(a==='filter-study-catalog'){studyGroup=b.dataset.group;render();return}
        if(a==='add-study-ticker'){const input=root.querySelector('#study-ticker-input');addStudyTicker(input&&input.value);return}
        if(a==='remove-study-ticker'){studyTargets=studyTargets.filter(function(t){return t!==b.dataset.ticker});render();return}
        if(a==='save-study-layout'){saveStudyLayout();return}
        if(a==='apply-study-layout'){applyStudyPreset(b.dataset.layout);studyRunner.runAll(studyPanels);return}
        if(a==='study-zoom-in'){setStudyZoom(studyZoom+.1);return}
        if(a==='study-zoom-out'){setStudyZoom(studyZoom-.1);return}
        if(a==='study-zoom-reset'){setStudyZoom(1);return}
        if(a==='remove-study-panel'){studyPanels=studyPanels.filter(function(p){return p.id!==b.dataset.panelId});autoArrangeStudyPanels();render();return}
        if(a==='move-study-panel'){const p=studyPanels.find(function(x){return x.id===b.dataset.panelId}),dir=b.dataset.direction;if(p){p.x=Math.max(1,Math.min(51,(p.x||1)+(dir==='left'?-3:dir==='right'?3:0)));p.y=Math.max(8,(p.y||14)+(dir==='up'?-28:dir==='down'?28:0));render()}return}
        if(a==='resize-study-panel'){const p=studyPanels.find(function(x){return x.id===b.dataset.panelId});if(p){p.w=(p.w||620)+160;p.h=(p.h||250)+70;render()}return}
        if(a==='load-study-layout'){const item=studySaved.find(function(x){return x.id===b.dataset.layoutId});if(item){studyRunner.invalidate();studySector='';studyPanels=item.panels.map(function(p){const panel=Object.assign({},p);if(panel.x<100)panel.x=16+panel.x*13;if(panel.w<100)panel.w=620;return panel});studyTargets=item.targets.slice();studyWindow=item.window;studyCustomField=item.customField||'close';studyCustomTransform=item.customTransform||'rolling_std';growStudyWorld();render();toast('Konfigurasi dimuat; jalankan ulang agar hasil sesuai input.')}return}
        if(a==='delete-study-layout'){studySaved=studySaved.filter(function(x){return x.id!==b.dataset.layoutId});localStorage.setItem('idxel-study-layouts',JSON.stringify(studySaved));render();return}
        if(a==='export'&&page==='issuer'){dossierReport=true;render();return}
        if(a==='export'||a==='snapshot'){openModal(a==='export'?'Export evidence snapshot':'Capture snapshot','Snapshot akan memuat status data dan provenance yang tersedia saat ini.','export');return}
        if(a==='close-modal'){closeModal();return}if(a==='confirm-modal'){const kind=root.querySelector('#idxel-modal').dataset.kind;closeModal();if(kind==='logout'){root.classList.add('is-loggedout');root.querySelector('#idxel-loggedout').classList.remove('hidden')}else if(kind==='account'){page='settings';render()}else if(kind==='dataset'){return}else toast('Aksi dicatat pada prototype.');return}
        if(a==='login-again'){root.classList.remove('is-loggedout');root.querySelector('#idxel-loggedout').classList.add('hidden');page='dashboard';render();return}
        if(a==='logout'){openModal('Keluar dari IDX Evidence Lab','Sesi lokal akan ditutup. Simpan atau ekspor evidence terlebih dahulu jika diperlukan.','logout');return}
        if(a.startsWith('dataset-')){const labels={universe:['Universe LQ45','Snapshot 45 anggota yang menjadi cakupan fitur saat ini; bukan rekonstruksi konstituen historis.'],daily:['Daily OHLCV','Bar harian tersimpan per ticker. Dipakai untuk return, RSI, risiko harga, dan chart. Periode mulai mengikuti ketersediaan masing-masing emiten.'],report:['Company report','Laporan snapshot per emiten untuk fundamental dan valuasi. Tanggal report dapat berbeda dari daily; field kosong tidak diisi dengan nol atau tebakan.'],foreign:['Foreign flow','Arus beli/jual asing harian dari Sectors.app. Ini bukan transaksi intraday dan bukan pemetaan broker ke pemilik manfaat.'],broker:['Broker activity','Hanya bukti issuer-level yang sudah tersimpan dan dipetakan. Arsip broker terpisah tidak dipakai sebagai proxy per emiten.'],filings:['Filings','Dokumen keterbukaan yang tersimpan dalam rentang penarikan per emiten; cocok untuk menelusuri peristiwa dan waktu publikasi.'],news:['News','Artikel lokal dari jendela query tertentu, bukan feed lengkap. Hubungan ke ticker hanya dipakai bila ada simbol terkait yang jelas.'],actions:['Corporate actions','Catatan aksi yang dikembalikan snapshot per emiten. Riwayat yang ada tidak otomatis berarti ada aksi mendatang.'],suspensions:['Suspensions','Riwayat peristiwa suspensi untuk konteks; bukan model prediksi suspensi.'],ihsg:['IHSG','Snapshot indeks harian lokal. Dipakai sebagai konteks pasar dan benchmark setelah tanggal disejajarkan.'],legal:['Korpus hukum','PDF lokal untuk retrieval aturan dan konteks hukum; perlu cek versi berlaku dan applicability oleh manusia. Bukan opini hukum otomatis.']};const detail=labels[a.replace('dataset-','')]||['Dataset','Snapshot lokal'];openModal(detail[0],detail[1]+' Sumber detail dan inventaris ada di halaman Sumber & metode.', 'dataset');return}
        if(a.startsWith('filter-')||a==='clear-filters'||a==='flow-period'||a==='horizon'||a==='select-index'){toast('Kontrol filter dibuka. Pilihan hanya mengubah tampilan lokal prototype.');return}
        if(a==='run-study'){toast('Perlu menjalankan pipeline offline untuk menghasilkan metrik.');return}
        if(a==='account'){openModal('Menu akun','Lanjutkan ke pengaturan akun. Tombol Keluar tersedia di halaman Settings.','account');return}
        if(a==='notif-toggle'){root.querySelector('#idxel-notif-dropdown')?.classList.toggle('hidden');return}
        if(a==='preferences'||a==='audit-data'){toast('Panel pengaturan/audit lokal dibuka.');return}
      });
      root.addEventListener('change',e=>{if(e.target.matches('[data-screener-filter]')){screenerFilters[e.target.dataset.screenerFilter]=e.target.value;render();return}if(e.target.matches('#research-ticker')){researchTicker=e.target.value;researchResult=null}if(e.target.matches('#study-sector-select')){studySector=e.target.value;studyRunner.invalidate();render()}if(e.target.matches('#study-window-select')){studyWindow=e.target.value;studyRunner.invalidate();render()}if(e.target.matches('[data-action="custom-field"]')){studyCustomField=e.target.value;studyRunner.invalidate();render()}if(e.target.matches('[data-action="custom-transform"]')){studyCustomTransform=e.target.value;studyRunner.invalidate();render()}});
      root.addEventListener('click',e=>{
        if(e.target.closest('[data-action="add-study-ticker"],[data-action="remove-study-ticker"]')){studySector='';studyRunner.invalidate()}
        if(e.target.closest('[data-action="expand-section"]')){e.target.closest('.fade-section')?.classList.add('is-expanded')}
        if(!e.target.closest('[data-action="notif-toggle"], #idxel-notif-dropdown')){root.querySelector('#idxel-notif-dropdown')?.classList.add('hidden')}
      });
      root.addEventListener('keydown',e=>{if(e.key==='Enter'&&e.target.matches('#research-question')&&!e.shiftKey){e.preventDefault();sendResearchMessage(e.target.value)}if(e.key==='Enter'&&e.target.matches('#study-query-input'))buildStudyFromQuery(e.target.value);if(e.key==='Enter'&&e.target.matches('#study-ticker-input'))addStudyTicker(e.target.value);if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)&&e.target.matches('.tabbar [role="tab"]')){const tabs=[...main.querySelectorAll('.tabbar [role="tab"]')],index=tabs.indexOf(e.target);if(index<0)return;e.preventDefault();const next=e.key==='Home'?0:e.key==='End'?tabs.length-1:(index+(e.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length;issuerTab=tabs[next].dataset.tab;page='issuer';render();main.querySelectorAll('.tabbar [role="tab"]')[next]?.focus()}});
      let dragState=null,resizeState=null,canvasPan=null,sidebarResize=null;
      root.querySelector('.side-splitter').addEventListener('pointerdown',e=>{sidebarResize={pointerId:e.pointerId};e.currentTarget.setPointerCapture(e.pointerId);e.preventDefault()});
      root.querySelector('.side-splitter').addEventListener('pointermove',e=>{if(!sidebarResize)return;const width=e.clientX-root.getBoundingClientRect().left;if(width<105){root.classList.add('is-side-collapsed');navWidth=72}else{root.classList.remove('is-side-collapsed');navWidth=Math.max(180,Math.min(420,width));root.style.setProperty('--side-width',navWidth+'px')}localStorage.setItem('idxel-sidebar-width',String(navWidth))});
      root.querySelector('.side-splitter').addEventListener('pointerup',()=>{sidebarResize=null});
      root.querySelector('.side-splitter').addEventListener('keydown',e=>{if(!['ArrowLeft','ArrowRight'].includes(e.key))return;e.preventDefault();navWidth=e.key==='ArrowLeft'?Math.max(180,navWidth-24):Math.min(420,navWidth+24);root.classList.remove('is-side-collapsed');root.style.setProperty('--side-width',navWidth+'px');localStorage.setItem('idxel-sidebar-width',String(navWidth))});
      root.addEventListener('pointerdown',e=>{const card=e.target.closest('.study-window'),viewport=e.target.closest('#study-canvas'),resizeHandle=e.target.closest('[data-resize-handle]'),handle=e.target.closest('[data-drag-handle]');if(resizeHandle&&card){const panel=studyPanels.find(function(p){return p.id===card.dataset.studyPanel});if(!panel)return;resizeState={id:panel.id,startX:e.clientX,startY:e.clientY,w:panel.w||620,h:panel.h||250};resizeHandle.setPointerCapture(e.pointerId);e.preventDefault();e.stopPropagation();return}if(handle&&card&&!e.target.closest('button')){const panel=studyPanels.find(function(p){return p.id===card.dataset.studyPanel});if(!panel)return;dragState={id:panel.id,startX:e.clientX,startY:e.clientY,x:panel.x||16,y:panel.y||20};handle.setPointerCapture(e.pointerId);e.preventDefault();return}if(viewport&&!card&&!e.target.closest('button,input,select,details,summary')){canvasPan={pointerId:e.pointerId,startX:e.clientX,startY:e.clientY,left:viewport.scrollLeft,top:viewport.scrollTop,viewport:viewport};viewport.classList.add('is-panning');viewport.setPointerCapture(e.pointerId);e.preventDefault()}});
      root.addEventListener('pointermove',e=>{if(resizeState){const panel=studyPanels.find(function(p){return p.id===resizeState.id});if(!panel)return;panel.w=Math.max(360,resizeState.w+(e.clientX-resizeState.startX)/studyZoom);panel.h=Math.max(190,resizeState.h+(e.clientY-resizeState.startY)/studyZoom);const card=root.querySelector('[data-study-panel="'+panel.id+'"]');if(card){card.style.width=panel.w+'px';card.style.height=panel.h+'px'}growStudyWorld()}else if(dragState){const panel=studyPanels.find(function(p){return p.id===dragState.id});if(!panel)return;panel.x=Math.max(0,dragState.x+(e.clientX-dragState.startX)/studyZoom);panel.y=Math.max(0,dragState.y+(e.clientY-dragState.startY)/studyZoom);const card=root.querySelector('[data-study-panel="'+panel.id+'"]');if(card){card.style.left=panel.x+'px';card.style.top=panel.y+'px'}growStudyWorld()}else if(canvasPan){let left=canvasPan.left-(e.clientX-canvasPan.startX),top=canvasPan.top-(e.clientY-canvasPan.startY);if(left<0){const shift=Math.ceil(-left/(900*studyZoom))*900;shiftStudyOrigin(shift,0);canvasPan.left+=shift*studyZoom;left=canvasPan.left-(e.clientX-canvasPan.startX)}if(top<0){const shift=Math.ceil(-top/(700*studyZoom))*700;shiftStudyOrigin(0,shift);canvasPan.top+=shift*studyZoom;top=canvasPan.top-(e.clientY-canvasPan.startY)}canvasPan.viewport.scrollLeft=left;canvasPan.viewport.scrollTop=top}});
