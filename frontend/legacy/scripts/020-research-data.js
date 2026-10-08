      async function uploadResearchFiles(fileList){
        if(researchChat.loading||researchUploading)return;
        const files=Array.from(fileList);if(!files.length)return;
        if(files.length+researchAttachments.length>5){researchChat.error='Maksimum 5 lampiran per sesi.';render();return}
        if(files.some(f=>f.type.startsWith('video/')||researchVideoExtensions.test(f.name))){researchChat.error='Video tidak diizinkan. Tidak ada akses kamera.';render();return}
        if(files.some(f=>f.size>5*1024*1024||f.size===0)){researchChat.error='Setiap file harus berisi data dan maksimal 5 MB.';render();return}
        const generation=researchChat.requestGeneration;researchUploading=true;researchChat.error=null;render();
        try{
          if(!researchChat.sessionId&&!await createResearchSession(generation))return;
          for(const file of files){
            const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
            const item=await researchPost('/api/research-attachments',{session_id:researchChat.sessionId,file:{name:file.name,mime:file.type||'application/octet-stream',data:btoa(binary)}});
            if(generation!==researchChat.requestGeneration)return;
            if(!researchAttachments.some(a=>a.id===item.id))researchAttachments.push(item);
          }
        }catch(error){if(generation===researchChat.requestGeneration)researchChat.error='Lampiran gagal: '+error.message}
        finally{researchUploading=false;if(page==='research')render()}
      }
      async function loadResearchTargets(){if(researchTargetsRequested)return;researchTargetsRequested=true;try{const response=await fetch('/api/research-targets',{cache:'no-store'});if(!response.ok)throw new Error('Catalog unavailable');researchTargets=await response.json()}catch(_error){researchTargets={tickers:lq45Tickers,sectors:[]}}if(page==='research')render()}
      function selectedResearchTarget(){if(!researchTarget)return null;const split=researchTarget.indexOf(':');return {kind:researchTarget.slice(0,split),value:researchTarget.slice(split+1)}}
      async function loadResearchHealth(){if(researchHealthRequested)return;researchHealthRequested=true;try{const response=await fetch('/api/health',{cache:'no-store'});if(!response.ok)throw new Error('Server unavailable');researchHealth=await response.json()}catch(_error){researchHealth={ok:false,openrouter_configured:false}}if(page==='research')render()}
      root.addEventListener('change',e=>{if(e.target.matches('#research-use-model'))researchUseModel=e.target.checked});
      root.addEventListener('input',e=>{if(e.target.matches('#research-question'))researchQuestion=e.target.value});
      root.addEventListener('change',e=>{if(e.target.matches('#research-target')){researchTarget=e.target.value;const mode=researchUseModel,draft=researchQuestion;newResearchSession();researchUseModel=mode;researchQuestion=draft;render()}});
      let portfolioState={catalog:null,catalogLoading:false,catalogAttempted:false,catalogError:null,result:null,error:null,loading:false,selected:[],query:'',profile:'moderate',method:'integrated',lookback:252,benchmark:'IHSG',capital:'',riskFreeRatePct:'7.129',requestGeneration:0};
      let newsGraph={news_id:null,nodes:[],edges:[],status:'PENDING_MODEL_APPROVAL',provenance:[]};
      const GRAPH_NODE_LIMIT=1000;
      let graphView={rotateX:-0.25,rotateY:0.45,zoom:1,graphOffsetX:0,graphOffsetY:0,panMode:false};
      let ticker='BBCA';
      let appHistory=[],appHistoryIndex=-1,isHistoryTraversal=false;
      let issuerPriceRange='6M',marketRsiPeriod=14,marketRsiRange='24h',marketFlowMonths=12;
      const dossierCache={},dossierPending=new Set(),dossierErrors={};
      let dossierCost=10,dossierEvent='',dossierReport=false,dossierBrokerWindow=20;
      const coverage=`Universe acuan: snapshot LQ45 45 simbol • data ditampilkan sesuai tanggal dan coverage provider • data turunan belum tervalidasi`;
      const btn=(label,action,klass='action')=>`<button class="${klass}" data-action="${action}">${label}</button>`;
      const metric=(label,value,hint='')=>`<div class="metric"><label>${label}</label><strong>${value}</strong>${hint?`<div class="hint">${hint}</div>`:''}</div>`;
      const section=(title,body,tail='',klass='')=>{const addHistorical=title==='CAPM · IHSG historis';if(addHistorical){title='CAPM · asumsi pemulihan ATH IHSG';body=body.replace('Return pasar aritmetika:','Return pasar aritmetika historis (konteks):').replace('Premi = return pasar − RF manual','Premi CAPM = asumsi Rₘ berbasis ATH − RF manual').replace('Premi negatif tetap ditampilkan.','Asumsi Rₘ memakai jarak ke ATH 9.174 pada penutupan IHSG lokal terakhir. Upside ATH ini kumulatif dan tidak diannualisasi karena horizon tidak ditentukan; hurdle CAPM yang dihasilkan adalah ambang heuristik, bukan forecast tahunan atau return historis.')}return `<section class="section ${klass}"><div class="section-head"><h2>${title}</h2><span class="sub">${tail}</span></div><div class="section-body">${body}</div></section>${addHistorical?historicalCapmPanel(portfolioState.result?.historical_capm):''}`};
