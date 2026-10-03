/* Native Studies controller. No provider access; results belong to one input generation. */
globalThis.StudiesUI = (() => {
  const escape = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const label = value => value == null ? '—' : typeof value === 'object' ? JSON.stringify(value) : typeof value === 'number' ? value.toLocaleString('id-ID',{maximumSignificantDigits:8}) : String(value);
  function createController({config, changed, transport}) {
    const states = {};
    let batchGeneration=0;
    function cancel(id) { batchGeneration++;const s=states[id];if(!s)return;s.generation++;s.controller?.abort();s.status='CANCELLED';changed(); }
    function invalidate() { batchGeneration++;for(const s of Object.values(states)){s.generation++;s.controller?.abort();s.status='STALE';} changed(); }
    async function run(panel,fromBatch=false) {
      if(!fromBatch)batchGeneration++;
      const old=states[panel.id],generation=(old?.generation||0)+1;
      old?.controller?.abort();
      const controller=new AbortController(), input=config(),key=JSON.stringify(input);
      const request={widget_id:panel.type,target_kind:input.target_kind,targets:input.targets,window:input.window};
      if(panel.type==='custom_engineering')request.params={field:input.field,transform:input.transform};
      if(['portfolio_risk','capm_benchmark'].includes(panel.type)&&input.portfolio_artifact_ref)request.portfolio_artifact_ref=input.portfolio_artifact_ref;
      states[panel.id]={generation,controller,status:'RUNNING',result:null,error:null};changed();
      try {
        const result=await transport(request,controller.signal);
        const s=states[panel.id];if(!s||s.generation!==generation||key!==JSON.stringify(config()))return;
        if(result.widget_id!==panel.type||!result.request_fingerprint)throw new Error('Respons tidak cocok dengan panel.');
        s.result=result;s.status=result.status;
      } catch(error) { const s=states[panel.id];if(s?.generation===generation){s.status=error.name==='AbortError'?'CANCELLED':'ERROR';s.error=error.message;} }
      finally { if(states[panel.id]?.generation===generation)changed(); }
    }
    async function runAll(panels) {const key=JSON.stringify(config()),batch=++batchGeneration;for(const panel of [...panels]){if(batch!==batchGeneration||key!==JSON.stringify(config()))break;await run(panel,true);} }
    return {states,run,runAll,cancel,invalidate};
  }
  function chart(series) {
    const points=series.points||[], valid=points.filter(p=>Number.isFinite(p.value));if(!valid.length)return '<p>Seri belum memiliki nilai yang dapat dihitung.</p>';
    let lo=Math.min(...valid.map(p=>p.value)),hi=Math.max(...valid.map(p=>p.value));if(lo===hi){lo-=Math.max(Math.abs(lo)*.01,1);hi+=Math.max(Math.abs(hi)*.01,1);}
    const x=i=>48+i/Math.max(1,points.length-1)*490,y=v=>170-(v-lo)/(hi-lo)*145;
    let path='',gap=true;
    points.forEach((p,i)=>{if(!Number.isFinite(p.value)){gap=true;return;}path+=(gap?'M':'L')+x(i)+' '+y(p.value)+' ';gap=false;});
    return '<div class="study-chart"><svg tabindex="0" viewBox="0 0 580 206" data-chart-interaction role="img" aria-label="'+escape(series.ticker+' '+series.id+' '+series.unit)+'">'+[0,.25,.5,.75,1].map(f=>'<line x1="48" x2="538" y1="'+(170-f*145)+'" y2="'+(170-f*145)+'" stroke="#263b50"/><text x="3" y="'+(174-f*145)+'" fill="#a4b6c8" font-size="9">'+escape(label(lo+f*(hi-lo)))+'</text><line x1="'+(48+f*490)+'" x2="'+(48+f*490)+'" y1="25" y2="170" stroke="#263b50"/>').join('')+'<path d="'+path+'" fill="none" stroke="#45c5e4" stroke-width="2"/>'+points.map((p,i)=>Number.isFinite(p.value)?'<circle cx="'+x(i)+'" cy="'+y(p.value)+'" r="3" fill="transparent" data-chart-point data-chart-x="'+x(i)+'" data-chart-y="'+y(p.value)+'" data-date="'+escape(p.date)+'" data-label="'+escape(series.ticker+' '+series.id)+'" data-value="'+escape(label(p.value))+'" data-unit="'+escape(series.unit)+'"/>':'').join('')+'<text x="48" y="194" fill="#a4b6c8" font-size="10">'+escape(points[0]?.date)+'</text><text x="538" y="194" text-anchor="end" fill="#a4b6c8" font-size="10">'+escape(points.at(-1)?.date)+'</text></svg></div>';
  }
  function renderResult(result,limit=100) {
    if(!result)return '<p class="study-not-run">Pilih target dan jalankan panel untuk menghitung dari data lokal.</p>';
    const metrics=result.metrics||[],tables=result.tables||[],series=result.series||[],warnings=result.warnings||[];
    return '<p class="study-result-meta">'+escape(result.status)+' · '+escape(result.target?.targets?.join(' · ')||result.target?.entities?.join(' · ')||'LQ45')+' · '+escape(result.period?.start)+' → '+escape(result.period?.end)+'</p><p class="study-small-note">Formula: '+escape(result.formula_version)+' · Validasi: '+escape(result.verification)+' · Coverage: '+escape(result.coverage?.usable_issuers)+'/'+escape(result.coverage?.requested_issuers)+' emiten</p>'+
      (result.verification_scope?'<p class="study-small-note">Referensi: '+escape(result.verification_scope.passed_cases)+'/'+escape(result.verification_scope.reference_cases)+' kasus · '+escape(result.verification_scope.scope)+'</p>':'')+
      (metrics.length?'<div class="study-result-table"><table><thead><tr><th>Metrik</th><th>Nilai</th><th>Unit / batas</th></tr></thead><tbody>'+metrics.map(m=>'<tr tabindex="0"><td>'+escape(m.id)+'</td><td>'+escape(label(m.value))+'</td><td>'+escape(m.unit)+'<small>'+escape(m.status)+' · '+escape(m.reason)+'</small></td></tr>').join('')+'</tbody></table></div>':'')+
      series.map((s,i)=>'<details class="study-series" '+(i===0?'open':'')+'><summary>'+escape(s.ticker+' · '+s.id+' · '+s.unit)+'</summary>'+chart(s)+'<details><summary>Data dan missingness ('+s.points.length+' observasi)</summary><div class="study-result-table"><table><tbody>'+s.points.map(p=>'<tr tabindex="0"><td>'+escape(p.date)+'</td><td>'+escape(label(p.value))+'</td><td>'+escape(p.reason)+'</td></tr>').join('')+'</tbody></table></div></details></details>').join('')+
      (tables.length?'<details><summary>Data pendukung · '+tables.length+' baris</summary><div class="study-records">'+tables.slice(0,limit).map(t=>'<pre tabindex="0">'+escape(JSON.stringify(t,null,2))+'</pre>').join('')+'</div>'+(tables.length>limit?'<p>'+limit+' dari '+tables.length+' ditampilkan. <button class="action" data-action="study-show-all">Tampilkan semua</button></p>':'')+'</details>':'')+
      (warnings.length?'<details class="study-warnings" open><summary>Keterbatasan · '+warnings.length+'</summary><ul>'+warnings.map(w=>'<li>'+escape((w.ticker?w.ticker+' · ':'')+w.reason)+(w.count?' ('+escape(w.count)+')':'')+'</li>').join('')+'</ul></details>':'')+
      '<details><summary>Provenance · '+(result.sources||[]).length+' sumber</summary><p class="study-small-note">Fingerprint: '+escape(result.request_fingerprint)+'</p>'+(result.sources||[]).map(s=>'<p class="study-small-note">'+escape(s.id)+'<br>'+escape(s.sha256)+'</p>').join('')+'</details>';
  }
  return {createController,renderResult};
})();
