'use strict';
const $ = s => document.querySelector(s);
const escapeHtml = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels = {created:'Создано',kept:'Сохранено',transformed:'Преобразовано',abolished:'Упразднено',moved:'Перенесено',reworded:'Переформулировано',lost:'Возможная потеря',added:'Добавлено',duplicated:'Дублирование'};
let report;
const badge = status => `<span class="badge ${status}">${labels[status] || status}</span>`;
function render() {
  $('#report').hidden = false;
  $('#units-content').innerHTML = `<div class="unit-list">${report.units.map(u => `<div class="unit-row"><span>${escapeHtml(u.name)}${u.after_name && u.after_name!==u.name ? `<br>→ ${escapeHtml(u.after_name)}`:''}</span>${badge(u.status)}</div>`).join('')}</div>`;
  $('#summary-content').innerHTML = `<p>Извлечено подразделений и ролей: ${report.units.length}.</p>`;
  $('#execution').textContent = 'Режим: детерминированный. Документы обрабатываются на этом компьютере.';
}
async function run(demo) {
  const controls = [...document.querySelectorAll('#upload-form button')];
  controls.forEach(b => b.disabled = true);
  $('#error').hidden = true; $('#progress').hidden = false; $('#report').hidden = true;
  $('#progress').textContent = 'Разбор документов и сопоставление редакций…';
  try {
    const start=performance.now();
    const response = await fetch(demo?'/api/demo':'/api/analyze',{method:'POST',headers:{Accept:'application/x-ndjson'},signal:AbortSignal.timeout(120000),body:demo?undefined:new FormData($('#upload-form'))});
    let data;
    if (response.headers.get('Content-Type')?.includes('application/x-ndjson')) {
      const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='';const steps=[];
      while(true){const chunk=await reader.read();if(chunk.done)break;buffer+=decoder.decode(chunk.value,{stream:true});let split;while((split=buffer.indexOf('\n'))>=0){const item=JSON.parse(buffer.slice(0,split));buffer=buffer.slice(split+1);if(item.error)throw new Error(item.error);if(item.progress){steps.push(item.progress);$('#progress').textContent=steps.map((s,i)=>`${i+1}. ${s}`).join(' → ');}if(item.report)data=item.report;}}
      if(!data)throw new Error('Ответ сервера прерван. Повторите анализ.');
    } else {data=await response.json();if(!response.ok)throw new Error(data.error || 'Не удалось обработать документы. Попробуйте другой формат.');}
    report = data; render();
    $('#progress').textContent = `Готово. Время обработки: ${new Intl.NumberFormat('ru',{maximumFractionDigits:1}).format((performance.now()-start)/1000)} с.`;
    if (demo) { $('#before-info').textContent = 'Демо: редакция 8'; $('#after-info').textContent = 'Демо: редакция 9'; }
    $('#summary').scrollIntoView({behavior:'instant'});
  } catch(e) { $('#progress').hidden = true; $('#error').hidden = false; $('#error').textContent=e.name==='TimeoutError'?'Анализ занял больше двух минут. Уменьшите комплект и повторите загрузку.':e.message; $('#error').focus(); }
  finally { controls.forEach(b => b.disabled = false); }
}
$('#upload-form').setAttribute('novalidate','');
$('#upload-form').addEventListener('submit',e=>{
  e.preventDefault();
  const missing=['before','after'].filter(side=>!$(`#${side}`).files.length);
  if(missing.length){
    $('#progress').hidden=true;$('#error').hidden=false;
    $('#error').textContent=missing.length===2?'Выберите документы «до» и «после» реорганизации или нажмите «Загрузить демо-комплект».':`Не выбраны документы «${missing[0]==='before'?'до':'после'} реорганизации».`;
    $(`#${missing[0]}`).focus();
    return;
  }
  run(false);
});
$('#demo').addEventListener('click',()=>run(true));
for (const side of ['before','after']) $(`#${side}`).addEventListener('change',e=>{$(`#${side}-info`).textContent=[...e.target.files].map(f=>f.name).join(', ') || 'Выберите документы';});
$('#close-dialog').addEventListener('click',()=>$('#evidence-dialog').close());
document.querySelectorAll('nav a').forEach(a=>a.addEventListener('click',()=>{document.querySelectorAll('nav a').forEach(n=>n.removeAttribute('aria-current'));a.setAttribute('aria-current','page');}));
const nf = new Intl.NumberFormat('ru',{maximumFractionDigits:0});
function quote(ref, other) {
  const words = new Set((other?.quote || '').toLocaleLowerCase('ru').match(/[\p{L}\p{N}]+/gu) || []);
  const html = ref.quote.split(/([\p{L}\p{N}]+)/gu).map(w=>words.has(w.toLocaleLowerCase('ru')) || !/[\p{L}\p{N}]/u.test(w)?escapeHtml(w):`<mark>${escapeHtml(w)}</mark>`).join('');
  return `<article><h3>${ref.side==='after'?'После':'До'} · §${escapeHtml(ref.clause)}</h3><p class="muted source-name">${escapeHtml(ref.doc)}<br>Абзац ${ref.paragraph} · ${escapeHtml(ref.unit)}</p>${ref.relation!=='direct'?'<p class="context-note">Контекст / ближайший кандидат. Не подтверждает наличие или отсутствие функции.</p>':''}<blockquote>${html}</blockquote></article>`;
}
function showEvidence(title, before, after, note='') {
  $('#evidence-title').textContent=title;
  $('#evidence-content').innerHTML=`${note?`<p class="context-note">${escapeHtml(note)}</p>`:''}<div class="quote-pair">${quote(before,after)}${quote(after,before)}</div>`;
  $('#evidence-dialog').showModal();
}
function renderFunctions() {
  const params=new URLSearchParams(location.search);
  const status=params.get('status') || 'all';
  const unit=params.get('unit') || '';
  const search=params.get('q') || '';
  $('#functions-content').innerHTML=`<div class="filters"><label>Статус<select id="status-filter" name="status"><option value="all">Все функции</option>${['kept','moved','reworded','lost','added','duplicated'].map(s=>`<option value="${s}" ${s===status?'selected':''}>${labels[s]}</option>`).join('')}</select></label><label class="search">Поиск по функции<input type="search" name="q" id="function-search" autocomplete="off" placeholder="Например, субъекты СВК…" value="${escapeHtml(search)}"></label><button id="reset-filters" type="button">Сбросить фильтры</button></div><p id="function-count" class="muted" aria-live="polite"></p><div id="function-table"></div>`;
  function update() {
    const s=$('#status-filter').value,q=$('#function-search').value;
    const selected=report.functions.filter(f=>(s==='all'||f.status===s||(s==='duplicated'&&f.duplicated)) && (!unit || [f.before.unit,f.after.unit].some(v=>v===unit||v.split(' / ').includes(unit))) && f.text.toLowerCase().includes(q.toLowerCase()));
    const p=new URLSearchParams(location.search);p.set('status',s);if(q)p.set('q',q);else p.delete('q');
    history.replaceState(null,'',`${location.pathname}?${p}#functions`);
    $('#function-count').textContent=`Показано ${nf.format(selected.length)} из ${nf.format(report.functions.length)} функций${unit?' · Владелец: '+unit:''}. Уверенность — сходство текстов, не вероятность правильности.`;
    $('#function-table').innerHTML=selected.length?`<div class="table-scroll" tabindex="0" role="region" aria-label="Сопоставление функций"><table><thead><tr><th scope="col">Функция</th><th scope="col">Было</th><th scope="col">Стало</th><th scope="col">Статус</th><th scope="col">Сходство</th><th scope="col">Основания</th></tr></thead><tbody>${selected.map(f=>`<tr data-function="${f.id}"><td><button class="text-button function-title" data-evidence="${f.id}">${escapeHtml(f.text.slice(0,160))}${f.text.length>160?'…':''}</button></td><td>${escapeHtml(f.before.unit)}<small>§${escapeHtml(f.before.clause)}${f.before.relation!=='direct'?' · контекст':''}</small></td><td>${escapeHtml(f.after.unit)}<small>§${escapeHtml(f.after.clause)}${f.after.relation!=='direct'?' · кандидат':''}</small></td><td>${badge(f.status)}${f.duplicated?badge('duplicated'):''}${f.requires_review?'<small>Требует проверки</small>':''}</td><td class="numeric">${nf.format(f.confidence*100)}%</td><td><button class="text-button" data-evidence="${f.id}">Две цитаты</button></td></tr>`).join('')}</tbody></table></div>`:'<div class="empty">Функций с такими условиями нет. Сбросьте фильтры или выберите другой статус.</div>';
    document.querySelectorAll('[data-evidence]').forEach(b=>b.addEventListener('click',()=>{const f=report.functions.find(f=>f.id===b.dataset.evidence);showEvidence(labels[f.status],f.before,f.after,f.status==='lost'?'Совпадение ниже порога. Возможная потеря требует ручной проверки всего комплекта.':'Подсвечены слова, которых нет в соседнем фрагменте.');}));
  }
  $('#status-filter').addEventListener('change',update);
  $('#function-search').addEventListener('input',update);
  $('#reset-filters').addEventListener('click',()=>{history.replaceState(null,'',location.pathname+'#functions');renderFunctions();});
  update();
}
const renderH1=render;
render=function(){renderH1();renderFunctions();};
function showEvidenceList(title,evidence,note='') {
  $('#evidence-title').textContent=title;
  $('#evidence-content').innerHTML=`${note?`<p class="context-note">${escapeHtml(note)}</p>`:''}<div class="quote-pair">${evidence.map((e,i)=>quote(e,evidence[i===0?1:0])).join('')}</div>`;
  $('#evidence-dialog').showModal();
}
function renderSummary() {
  const metrics=(obj,group)=>Object.entries(obj).map(([s,n])=>`<div class="metric"><strong>${nf.format(n)}</strong><span>${group==='risk'&&s==='conflict'?'Конфликты интересов':labels[s]}</span></div>`).join('');
  $('#summary-content').innerHTML=`<div class="report-title"><p>Редакции сопоставлены. Все опубликованные ссылки прошли проверку цитат.</p><span class="verified">Цитаты проверены</span></div><h3>Подразделения</h3><div class="metrics">${metrics(report.counts.units)}</div><h3>Функции</h3><div class="metrics function-metrics">${metrics(report.counts.functions)}</div><p class="muted">Дублирование — дополнительная отметка функции. Управленческие роли показаны отдельно в схеме ниже.</p><div class="conclusion"><h3>Аналитическое заключение</h3>${report.conclusion.map(c=>`<p>${escapeHtml(c.text)} <button class="text-button" data-conclusion="${c.id}">§${escapeHtml(c.evidence[0].clause)} / основания</button></p>`).join('')||'<p>Недостаточно данных для заключения. Загрузите нумерованные положения о подразделениях.</p>'}</div>`;
  document.querySelectorAll('[data-conclusion]').forEach(b=>b.addEventListener('click',()=>{const c=report.conclusion.find(c=>c.id===b.dataset.conclusion);showEvidenceList('Основания заключения',c.evidence,c.text);}));
}
function renderUnits() {
  const nodes=side=>{
    const map=new Map();
    report.units.forEach(u=>{const r=u[side==='before'?'before_ref':'after_ref'];if(r.relation==='direct')map.set(r.unit,{name:side==='before'?u.name:u.after_name||u.name,key:r.unit,status:u.status,id:u.id});});
    report.functions.forEach(f=>{const r=f[side];if(r.relation==='direct'&&!map.has(r.unit))map.set(r.unit,{name:r.unit,key:r.unit,status:'kept'});});
    return [...map.values()];
  };
  const old=nodes('before'),fresh=nodes('after');
  const transfers=new Map();
  report.functions.filter(f=>f.status==='moved'&&f.before.unit!==f.after.unit).forEach(f=>{const key=f.before.unit+'\0'+f.after.unit;const entry=transfers.get(key)||{from:f.before.unit,to:f.after.unit,functions:[]};entry.functions.push(f);transfers.set(key,entry);});
  const height=Math.max(old.length,fresh.length)*98;
  const lines=[...transfers.values()].map(t=>{const a=old.findIndex(n=>n.key===t.from),b=fresh.findIndex(n=>n.key===t.to);return `<path d="M0 ${a*98+44} C80 ${a*98+44} 70 ${b*98+44} 150 ${b*98+44}"/><circle cx="146" cy="${b*98+44}" r="3"/>`;}).join('');
  const column=(arr,side)=>`<div class="org-column"><h3>${side==='before'?'До реорганизации':'После реорганизации'}</h3>${arr.map((n,i)=>`<button class="org-node ${n.status}" data-node-side="${side}" data-node-index="${i}"><strong>${escapeHtml(n.key)}</strong><span>${escapeHtml(n.name)}</span></button>`).join('')}</div>`;
  $('#units-content').innerHTML=report.units.length?`<p class="muted">Выберите узел, чтобы увидеть его функции. Линии обозначают переносы между владельцами.</p><div class="org-chart">${column(old,'before')}<svg class="transfer-lines" width="150" height="${height}" viewBox="0 0 150 ${height}" aria-hidden="true">${lines}</svg>${column(fresh,'after')}</div><details class="transfer-details"><summary>Переносы между владельцами (${transfers.size})</summary>${[...transfers.values()].map(t=>`<p>${escapeHtml(t.from)} → ${escapeHtml(t.to)}: ${t.functions.length} функций, §${escapeHtml(t.functions[0].before.clause)} → §${escapeHtml(t.functions[0].after.clause)}.</p>`).join('')||'<p>Переносов между владельцами не найдено.</p>'}</details><div class="unit-list">${report.units.map(u=>`<div class="unit-row"><span>${escapeHtml(u.name)}${u.after_name&&u.after_name!==u.name?` → ${escapeHtml(u.after_name)}`:''}</span>${badge(u.status)}<button class="text-button" data-unit-evidence="${u.id}">Основания</button></div>`).join('')}</div>`:'<div class="empty">Перечень подразделений не распознан. Нужны названия подразделений в списке структуры или заголовках ответственности.</div>';
  document.querySelectorAll('[data-node-index]').forEach(b=>b.addEventListener('click',()=>{const node=(b.dataset.nodeSide==='before'?old:fresh)[Number(b.dataset.nodeIndex)];const p=new URLSearchParams();p.set('unit',node.key);history.replaceState(null,'',`?${p}#functions`);renderFunctions();$('#functions').scrollIntoView({behavior:'instant'});}));
  document.querySelectorAll('[data-unit-evidence]').forEach(b=>b.addEventListener('click',()=>{const u=report.units.find(u=>u.id===b.dataset.unitEvidence);showEvidence(labels[u.status],{...u.before_ref,side:'before'},{...u.after_ref,side:'after'},u.requires_review?'Статус получен сопоставлением названий и структуры; преемственность требует проверки.':'');}));
}
function renderRisks() {
  const actual=report.risks.filter(r=>r.classification!=='safeguard'),safeguards=report.risks.filter(r=>r.classification==='safeguard');
  const card=r=>`<article class="risk"><div class="risk-heading"><h3>${r.classification==='safeguard'?'Мера предотвращения':r.type==='conflict'?'Потенциальный конфликт интересов':labels[r.type]}</h3><span class="severity">${{high:'Высокий приоритет',medium:'Требует проверки',info:'Информация'}[r.severity]}</span></div><p>${escapeHtml(r.explanation)}</p><p class="recommendation"><b>Рекомендация.</b> ${escapeHtml(r.recommendation)}</p><button class="text-button" data-risk="${r.id}">Проверить цитаты · ${r.evidence.map(e=>'§'+escapeHtml(e.clause)).join(' / ')}</button></article>`;
  $('#risks-content').innerHTML=`<p class="risk-total">${nf.format(actual.length)} кандидатов на риск, включая ${report.counts.risks.conflict} потенциальных конфликтов интересов</p>${actual.map(card).join('')||'<div class="empty">По заданным правилам рисков не найдено. Это не заменяет проверку ответственным сотрудником.</div>'}${safeguards.length?`<h3 class="safeguard-title">Меры предотвращения в документе</h3>${safeguards.map(card).join('')}`:''}`;
  document.querySelectorAll('[data-risk]').forEach(b=>b.addEventListener('click',()=>{const r=report.risks.find(r=>r.id===b.dataset.risk);showEvidenceList('Проверка риска',r.evidence,r.explanation);}));
}
const renderH2=render;
render=function(){renderH2();renderSummary();renderUnits();renderRisks();};
const renderH3=render;
render=function(){
  renderH3();
  $('#export-content').innerHTML=`<p class="muted">Заключение, таблица функций и дословные цитаты в одном файле. HTML открывается без сервера; JSON подходит для дальнейшей обработки.</p><div class="actions"><a class="download primary" href="/api/export/${report.run_id}?format=html" download>Скачать заключение HTML</a><a class="download" href="/api/export/${report.run_id}?format=json" download>Скачать JSON</a></div>`;
  $('#execution').textContent=`Режим: ${report.mode==='llm-assisted'?'LLM выбрала проверенные формулировки':'детерминированный'}. ${report.pipeline.map(s=>s.name).join(' → ')}. ${report.llm?.scope||'Документы обрабатываются на этом компьютере.'}`;
  document.querySelector('.local-mode').textContent=report.mode==='llm-assisted'?'LLM · Факты проверены':'Локальный анализ · Без API-ключа';
  document.querySelectorAll('nav a').forEach(n=>n.removeAttribute('aria-current'));
  document.querySelector('nav a[href="#summary"]').setAttribute('aria-current','page');
};
