'use strict';
// GIDs are exact strings throughout. Only metrics and cluster IDs are numeric.
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const colors = {coordinator:'#7c65ae',consolidator:'#198b85',distributor:'#5381c4',transit:'#bc9146',terminal:'#bd746c',peripheral:'#a8b3c2'};
const queueNames = {INVESTIGATE_NOW:'ПРОВЕРИТЬ СЕЙЧАС',REQUEST_MORE_DATA:'ЗАПРОСИТЬ ДАННЫЕ',MONITOR:'НАБЛЮДАТЬ'};
const queueDescriptions = {INVESTIGATE_NOW:'Высокий приоритет и достаточные наблюдения для начала проверки.',REQUEST_MORE_DATA:'Важные узлы: ограничения данных мешают интерпретации.',MONITOR:'Ниже порога приоритета. Это не означает отсутствие риска.'};
const fmt = value => new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2}).format(value);
const fixed = value => value.toFixed(3);
const state = {queue:'INVESTIGATE_NOW',offset:0,limit:25,total:0,gid:null,nodeSeq:0,queueSeq:0,searchSeq:0,zoom:1,clusterHighlight:false};
const badge = (value, label=value) => `<span class="badge ${esc(value)}">${esc(label)}</span>`;
const dot = role => `<i class="role-dot" style="background:${colors[role] || colors.peripheral}"></i>`;
async function api(url) {
  const response = await fetch(url);
  if (!response.ok) { let message = `Ошибка ${response.status}`; try { message = (await response.json()).detail || message; } catch {} throw new Error(message); }
  return response.json();
}
function showError(error) { $('global-error').textContent = error.message || String(error); $('global-error').hidden = false; }
function clearError() { $('global-error').hidden = true; }
function attachNodeLinks(element) { element.querySelectorAll('[data-gid]').forEach(button => button.addEventListener('click', () => selectNode(button.dataset.gid))); }
async function loadQueue() {
  const request = ++state.queueSeq;
  $('queue-description').textContent = queueDescriptions[state.queue];
  $('queue-list').innerHTML = '<div class="loading">Загружаем очередь…</div>';
  document.querySelectorAll('[data-queue]').forEach(b => b.classList.toggle('active',b.dataset.queue === state.queue));
  try {
    const data = await api(`/api/queues/${state.queue}?offset=${state.offset}&limit=${state.limit}`);
    if (request !== state.queueSeq) return;
    state.total = data.total;
    $('queue-list').innerHTML = data.items.map(n => `<button class="queue-item ${n.gid===state.gid?'selected':''}" data-gid="${esc(n.gid)}"><span class="id">${esc(n.gid)}</span><span class="row"><span>${dot(n.role)}${esc(n.role)}</span><b class="score">${fixed(n.priority_score)}</b></span><span class="row"><span class="obs">OBSERVABILITY · ${esc(n.observability_level)}</span><span class="obs">${n.is_seed?'SEED':'DEPTH '+n.depth}</span></span></button>`).join('') || '<div class="loading">В очереди нет узлов</div>';
    attachNodeLinks($('queue-list'));
    $('page-label').textContent = data.total ? `${state.offset+1}–${Math.min(state.offset+state.limit,data.total)} из ${data.total}` : '0 узлов';
    $('prev-page').disabled = state.offset === 0;
    $('next-page').disabled = state.offset + state.limit >= data.total;
    if (!state.gid && data.items.length) await selectNode(data.items[0].gid);
  } catch (error) { if(request===state.queueSeq) { $('queue-list').innerHTML='<div class="loading">Очередь недоступна</div>'; showError(error); } }
}
async function selectNode(gid) {
  if (typeof gid !== 'string') throw new Error('GID must remain an exact string');
  const request = ++state.nodeSeq;
  state.gid = gid; state.zoom = 1;
  clearError(); $('search-results').hidden = true;
  $('node-card').innerHTML = '<div class="loading">Загружаем карточку…</div>';
  $('graph-empty').textContent = 'Загружаем окружение…'; $('graph-empty').hidden=false;
  $('network').replaceChildren(); $('edge-table').replaceChildren(); $('cluster-panel').replaceChildren();
  document.querySelectorAll('.queue-item').forEach(b=>b.classList.toggle('selected',b.dataset.gid===gid));
  try {
    const [node,ego] = await Promise.all([api(`/api/nodes/${encodeURIComponent(gid)}`),api(`/api/nodes/${encodeURIComponent(gid)}/ego`)]);
    if (request !== state.nodeSeq) return;
    if (node.gid !== gid || ego.center_gid !== gid) throw new Error('Несовпадение идентификатора ответа');
    renderCard(node); renderGraph(ego); renderCluster(node.cluster);
    resetAnalystNode(gid);
    history.replaceState(null,'',`?gid=${encodeURIComponent(gid)}`);
  } catch(error) {
    if(request!==state.nodeSeq) return;
    $('node-card').innerHTML='<div class="empty-card"><h3>Узел не найден или недоступен</h3><p>Проверьте GID и повторите поиск.</p></div>';
    $('graph-empty').textContent='Нет данных для отображения';
    showError(error);
  }
}
function renderStability(s) {
  if(!s) return '<div class="card-section"><p class="label">Stability · диагностика</p><p class="explanation">Не рассчитана или устарела. Основные роли и рейтинг доступны.</p></div>';
  if(s.status==='NOT_EVALUABLE') return '<div class="card-section"><p class="label">Stability · N/A</p><p class="explanation">Изолированный узел: устойчивость роли и ранга не интерпретируется.</p></div>';
  return `<div class="card-section stability"><p class="label">Stability · чувствительность</p>${[['parameter','Параметры правил'],['edge_dropout','Удаление 5% рёбер']].map(([key,title])=>{const v=s[key];return `<p><strong>${title}</strong></p><div class="facts"><div class="fact"><span>Совпадение роли</span><b>${v.role_matches} / ${v.runs} · ${esc(v.role_status)}</b></div><div class="fact"><span>Вхождение в TOP-20</span><b>${v.top20_count} / ${v.runs}</b></div>${v.rank_range?`<div class="fact"><span>Диапазон ранга</span><b>${v.rank_range[0]}–${v.rank_range[1]}</b></div>`:''}</div>${v.competing_roles.length?`<p class="explanation">Другие роли в сценариях: ${v.competing_roles.map(esc).join(', ')}</p>`:''}`;}).join('')}<p class="explanation">STABLE: роль совпала минимум в 90% сценариев этой группы. Диагностическая устойчивость к выбранным изменениям, не accuracy и не вероятность истинности роли. Удаление рёбер — стресс-тест, не модель реальной неполноты.</p></div>`;
}
function renderPatterns(p) {
  if(!p) return '<div class="card-section"><p class="label">Паттерны · N/A</p><p class="explanation">Не рассчитаны или устарели. Основные результаты доступны.</p></div>';
  const t=p.temporal,r=p.routes,a=p.anomalies;
  const val=x=>x===null?'N/A':fmt(x);
  const paths=(rows,kind)=>rows.map(v=>`<li><p>${v.gids.map(g=>`<button data-gid="${esc(g)}">${esc(g)}</button>`).join(' → ')}</p><button class="pattern-route" data-path="${esc(JSON.stringify(v.gids))}">Подсветить видимые рёбра</button>${kind==='chain'?`<p>${v.support_episodes} пар дат (каждый день на одном ребре используется один раз): ${v.episodes.map(e=>`${esc(e.in_date)} → ${esc(e.out_date)}`).join('; ')}</p>`:kind==='reciprocal'?`<p>Прямое направление ${fmt(v.forward_kzt)} KZT; обратное ${fmt(v.reverse_kzt)} KZT. Порядок не установлен.</p>`:`<p>Цикл длины ${v.length}; временной порядок не проверен.</p>`}</li>`).join('');
  const labels={in_counterparties:'Отправители',out_counterparties:'Получатели',incoming_volume_kzt:'Наблюдаемый вход, KZT',observed_volume_kzt:'Вход + выход, KZT',tx_count:'Число транзакций',max_daily_fan_in:'Максимум отправителей за день',max_daily_fan_out:'Максимум получателей за день'};
  return `<div class="card-section patterns"><p class="label">Паттерны · дополнительный слой</p><p class="explanation">Не меняют роль, рейтинг и очередь. Наблюдения не доказывают нарушение или движение тех же денег.</p>
  <details><summary>Временные · совместимость ${t.compatibility_fraction===null?'N/A':fmt(t.compatibility_fraction*100)+'%'} · gather→scatter ${val(t.gather_scatter_count)}</summary>
  <p>${t.status==='CENSORED'?'Исходящие CENSORED: depth=4. Временную совместимость нельзя оценить.':'Максимально совместимый объём при задержке +1/+2 дня, без повторного использования дневных сумм.'}</p>
  <div class="facts"><div class="fact"><span>Вход не позднее чем за 2 дня до конца периода</span><b>${fmt(t.eligible_in_kzt)} KZT</b></div><div class="fact"><span>Совместимый выход</span><b>${val(t.compatible_out_kzt)} KZT</b></div><div class="fact"><span>Вход у правой границы периода</span><b>${fmt(t.right_censored_in_kzt)} KZT</b></div><div class="fact"><span>Совпадение объёмов в один день</span><b>${val(t.same_day_overlap_kzt)} KZT · ORDER UNKNOWN</b></div></div>
  <p class="explanation">Same-day объём не суммируется с +1/+2. Начальный остаток, внешние потоки и дальнейший период неизвестны.</p>
  <p>Gather→scatter: ≥3 отправителя за день → ≥3 получателя через 1–2 дня. Всего ${val(t.gather_scatter_count)}; показано ${t.gather_scatter_samples.length}.</p><ul>${t.gather_scatter_samples.map(v=>`<li>${esc(v.date)}: ${v.senders} отправителей → ${v.following_1_2_day_recipients} получателей; вход ${fmt(v.in_kzt)} / выход ${fmt(v.following_out_kzt)} KZT.</li>`).join('')}</ul>
  <p>Всплеск активности: ${t.activity_burst.flag===null?'N/A — CENSORED':t.activity_burst.flag?'есть наблюдаемый сигнал':'порог не достигнут'} (≥5 операций и ≥50% за один день).</p>
  <details><summary>Дневные суммы · ${t.daily.length} активных дней</summary><table><thead><tr><th>Дата</th><th>Вход KZT</th><th>Выход KZT</th></tr></thead><tbody>${t.daily.map(d=>`<tr><td>${esc(d.date)}</td><td>${fmt(d.in_kzt)}</td><td>${val(d.out_kzt)}</td></tr>`).join('')}</tbody></table></details></details>
  <details><summary>Маршруты · цепочки ${r.repeated_chain_count} · взаимные ${r.reciprocal_count} · циклы ${r.short_cycle_count}${r.cycles_truncated?' (неполный поиск)':''}</summary>
  <p class="explanation">Узел может быть в любой позиции маршрута. Показано до 10 примеров каждого типа. Эпизоды разных цепочек могут разделять транзакции; не складывайте их как независимые события.</p><p class="pattern-highlight-note" role="status"></p>
  <h4>Повторяющиеся A→B→C</h4><ul>${paths(r.repeated_chain_samples,'chain')||'<li>Повторений по заданному правилу не найдено.</li>'}</ul><h4>Взаимные переводы</h4><ul>${paths(r.reciprocal_samples,'reciprocal')||'<li>Не наблюдаются.</li>'}</ul><h4>Направленные циклы 3–4</h4><ul>${paths(r.short_cycle_samples,'cycle')||'<li>Не найдены в пределах поиска.</li>'}</ul></details>
  <details><summary>Отклонения среди узлов колена ${p.depth} · ${a.flag_count} сигналов</summary><p class="explanation">Средний ранг одинаковых значений среди узлов того же depth; сигнал при ≥99-м процентиле и положительном значении. Минимум 20 участников. Это не вероятность и не норматив «нормального» поведения. У seed вход неполон; выборка ограничена.</p>
  <table><thead><tr><th>Признак</th><th>Значение</th><th>Процентиль</th></tr></thead><tbody>${Object.entries(a.peers).map(([k,v])=>`<tr><td>${labels[k]}</td><td>${val(v.value)}</td><td>${v.percentile===null?'N/A · '+esc(v.status):fmt(v.percentile*100)+(v.flag?' · СИГНАЛ':'')}<br><small>Узлов: ${v.peer_count}</small></td></tr>`).join('')}</tbody></table>
  <p>Равные суммы ≥3 получателям за день: ${val(a.equal_amount_distribution_count)}. Это не доказательство дробления; операции ниже 5000 KZT отсутствуют.</p><ul>${a.equal_amount_samples.map(v=>`<li>${esc(v.date)} · ${fmt(v.amount_kzt)} KZT · ${v.recipient_count} получателей</li>`).join('')}</ul></details></div>`;
}
function attachPatternRoutes() {
  $('node-card').querySelectorAll('.pattern-route').forEach(button=>button.addEventListener('click',()=>{
    const path=JSON.parse(button.dataset.path),wanted=new Set(path.slice(1).map((g,i)=>path[i]+'>'+g));let shown=0;
    $('network').querySelectorAll('.graph-edge').forEach(edge=>{const match=wanted.has(edge.dataset.src+'>'+edge.dataset.dst);edge.classList.toggle('pattern-highlight',match);if(match)shown++;});
    $('node-card').querySelector('.pattern-highlight-note').textContent=`Подсвечено ${shown} из ${wanted.size} рёбер маршрута. Остальные могут быть вне текущего ego-графа. Полный путь указан ниже; можно открыть любой его GID.`;
  }));
}

function renderCard(n) {
  const facts = [ ['Входящие, KZT',fmt(n.in_kzt)],['Исходящие, KZT',fmt(n.out_kzt)],['Отправители',n.in_degree],['Получатели',n.out_degree],['Достижим от seed',n.reachable_seed_count],['Колено / кластер',`${n.depth} / ${n.cluster_id}`],['Вход / выход, переводов',`${n.in_tx} / ${n.out_tx}`] ];
  $('node-card').innerHTML = `<div class="card-header"><p class="eyebrow">КАРТОЧКА УЗЛА ${n.is_seed?'· SEED':''}</p><h3 class="full-gid">${esc(n.gid)}</h3>${badge(n.investigation_queue,queueNames[n.investigation_queue])}</div>
  <div class="card-section"><p class="label">Основная гипотеза · сила признаков</p><a class="method-link" href="/methodology?gid=${encodeURIComponent(n.gid)}#${esc(n.primary_role)}">Показать расчёт этой роли ↗</a><div class="hypothesis"><strong>${dot(n.primary_role)}${esc(n.primary_role)}</strong><span class="value">${fixed(n.primary_strength)}</span></div><div class="strength-bar"><i style="width:${n.primary_strength*100}%;background:${colors[n.primary_role]}"></i></div>
  ${n.alternative_role?`<div class="alternative"><p class="label">Альтернативная гипотеза</p><div class="hypothesis"><strong>${dot(n.alternative_role)}${esc(n.alternative_role)}</strong><span class="value">${fixed(n.alternative_strength)}</span></div></div>`:'<p class="explanation">Других допущенных правилами гипотез нет.</p>'}<p class="explanation">Сила наблюдаемых признаков, не вероятность. Гипотезы могут сосуществовать.</p></div>
  <div class="card-section scores"><div><p class="label">Приоритет проверки</p><a class="method-link" href="/methodology#priority">Как рассчитано?</a><strong>${fixed(n.priority_score)}</strong></div><div><p class="label">Пригодность наблюдений</p><a class="method-link" href="/methodology#observability">Как рассчитано?</a><strong>${n.observability_score.toFixed(2)}</strong>${badge(n.observability_level)}</div></div>
  <div class="card-section"><p class="label">Почему этот узел</p><p class="body">${esc(n.evidence)}</p><p class="explanation">${esc(n.queue_reason)}</p></div>
  <div class="card-section"><p class="label">Факты наблюдаемого графа</p><div class="facts">${facts.map(([k,v])=>`<div class="fact"><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join('')}</div></div>
  <div class="card-section"><details><summary>Подробнее о расчёте</summary><p>Структурная значимость в наблюдаемом графе: PageRank ${n.pagerank.toFixed(6)}. Это показатель связей, не вероятность нарушения.</p></details></div>
  <div class="card-section"><a href="/methodology#temporal">Как рассчитаны временные признаки и маршруты?</a></div>${renderPatterns(n.patterns)}
  <div class="card-section"><a href="/methodology#stability">Как рассчитана устойчивость?</a></div>${renderStability(n.stability)}
  <div class="card-section convergence"><p class="label">Схождение seed · входящие ветви</p><a class="method-link" href="/methodology#convergence">Как рассчитано?</a><div class="facts"><div class="fact"><span>Достижим от seed</span><b>${n.seed_convergence.reachable_seed_count}</b></div><div class="fact"><span>Эффективное разнообразие последних входящих ветвей</span><b>${n.seed_convergence.effective_last_hop_branches.toFixed(2)}</b></div><div class="fact"><span>Прямых входящих ветвей</span><b>${n.in_degree}</b></div><div class="fact"><span>Ветвей от внешних seed</span><b>${n.seed_convergence.supported_predecessor_count}</b></div><div class="fact"><span>Внешних seed в расчёте</span><b>${n.seed_convergence.external_seed_count}</b></div></div><p class="explanation">Это разнообразие наблюдаемых последних входящих ветвей, а не число независимых маршрутов. Один seed может достигать нескольких ветвей. Ветви могут пересекаться upstream; показатель может быть больше числа seed.</p><p class="explanation">Возврат через сам узел исключён. ${n.seed_convergence.self_seed_excluded?'Сам seed не считается внешним источником. ':''}Ноль — нет входящей ветви от внешнего seed в выгрузке; это не доказательство отсутствия внешних связей.</p></div>
  <div class="card-section dependency"><p class="label">Зависимость наблюдаемых путей</p><a class="method-link" href="/methodology#dependency">Как рассчитано?</a><div class="facts"><div class="fact"><span>Других узлов зависят</span><b>${n.structural_dependency.dominated_nodes ?? 'N/A'}</b></div><div class="fact"><span>Кластеров среди них</span><b>${n.structural_dependency.dominated_clusters ?? 'N/A'}</b></div></div><p class="explanation">${esc(n.structural_dependency.explanation)}</p><p class="explanation">${esc(n.structural_dependency.limitation || '')}</p></div>
  <div class="card-section"><p class="label">Какие признаки можно интерпретировать</p>${Object.entries(n.evidence_details).map(([key,item])=>`<div class="availability-row" title="${esc(n.patterns&&key==='transit'?item.reason.replace('Временная согласованность не рассчитана','Временная совместимость рассчитана отдельно и не используется в роли transit'):item.reason)}"><span>${({fan_in:'Входящие связи',fan_out:'Исходящее поведение',transit:'Transit evidence',terminal:'Terminal evidence',seed_reach:'Достижимость от seed',community:'Структурный кластер',dominator:'Зависимость путей'})[key]}</span><b class="${item.status}">${item.value===null?'N/A':(typeof item.value==='number'&&!Number.isInteger(item.value)?item.value.toFixed(3):esc(item.value))} <small>${esc(item.status)}</small></b></div>`).join('')}<p class="explanation">AVAILABLE — измеримо только в наблюдаемом графе. PARTIAL — ограниченная интерпретация. CENSORED — обрезано обходом. N/A — нельзя оценить; это не ноль.</p></div>
  <div class="card-section limitations"><p class="label">${n.investigation_queue==='REQUEST_MORE_DATA'?'Почему нужны дополнительные данные':'Ограничения интерпретации'}</p><ul>${n.observability_reasons.map(r=>`<li>${esc(r)}</li>`).join('')}</ul><p class="explanation">${esc(n.data_gaps.find(g=>g.code==='GLOBAL_SAMPLING').description)}</p></div>
  <div class="card-section request"><p class="label">Следующий полезный запрос</p><p>${esc(n.next_data_request)}</p><p class="explanation">Рекомендация аналитику. Запрос не выполняется.</p></div>`;
  attachNodeLinks($('node-card')); attachPatternRoutes();
}
const NS='http://www.w3.org/2000/svg';
function svgEl(tag,attrs={},text) { const el=document.createElementNS(NS,tag); for(const [k,v] of Object.entries(attrs)) el.setAttribute(k,String(v)); if(text!==undefined) el.textContent=text; return el; }
function renderGraph(data) {
  const svg=$('network'); svg.replaceChildren();
  const selectedCluster=data.nodes.find(n=>n.gid===data.center_gid).cluster_id;
  $('cluster-toggle').textContent=`Кластер ${selectedCluster}`;
  $('graph-empty').hidden=true;
  $('graph-subtitle').textContent=`GID ${data.center_gid} · ${data.total_neighbors} соседей · ${data.edges.length} рёбер в окрестности`;
  $('graph-notice').hidden=!data.truncated;
  $('graph-notice').textContent=`Показана часть окружения: ещё ${data.omitted_neighbors} соседей не отображены. Узлы выбраны по исходному приоритету.`;
  const upstream=new Set(data.edges.filter(e=>e.dst===data.center_gid).map(e=>e.src));
  const neighbors=data.nodes.filter(n=>n.gid!==data.center_gid);
  const left=neighbors.filter(n=>upstream.has(n.gid)); const right=neighbors.filter(n=>!upstream.has(n.gid));
  const height=640, positions=new Map([[data.center_gid,{x:600,y:320}]]);
  function place(nodes,leftSide) { const columns=Math.max(1,Math.ceil(nodes.length/12)); const rows=Math.min(12,nodes.length); nodes.forEach((n,index)=>{const col=Math.floor(index/12),row=index%12; positions.set(n.gid,{x:leftSide?100+col*360/columns:1100-col*360/columns,y:rows===1?320:90+row*460/(rows-1)});}); }
  place(left,true);place(right,false);
  svg.setAttribute('viewBox',`0 0 1200 ${height}`); svg.setAttribute('aria-label',`Направленный граф узла ${data.center_gid}, соседей ${data.total_neighbors}`);
  const defs=svgEl('defs'); const marker=svgEl('marker',{id:'arrow',viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:5,markerHeight:5,orient:'auto-start-reverse'});marker.append(svgEl('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:'#8194ad'}));defs.append(marker);svg.append(defs);
  svg.append(svgEl('text',{x:110,y:40,class:'node-label'},'ОТПРАВИТЕЛИ / ВЗАИМНЫЕ СВЯЗИ'));
  svg.append(svgEl('text',{x:970,y:40,class:'node-label'},'ПОЛУЧАТЕЛИ'));
  const maxLog=Math.max(1,...data.edges.map(e=>Math.log1p(e.sum_kzt)));
  data.edges.forEach(e=>{
    const a=positions.get(e.src),b=positions.get(e.dst); const dx=b.x-a.x,dy=b.y-a.y,d=Math.hypot(dx,dy)||1;
    const radiusA=e.src===data.center_gid?26:15,radiusB=e.dst===data.center_gid?26:15;
    const reciprocal=data.edges.some(other=>other.src===e.dst&&other.dst===e.src);const offset=reciprocal?5:0;
    const x1=a.x+dx/d*radiusA-dy/d*offset,y1=a.y+dy/d*radiusA+dx/d*offset,x2=b.x-dx/d*radiusB-dy/d*offset,y2=b.y-dy/d*radiusB+dx/d*offset;
    const line=svgEl('line',{x1,y1,x2,y2,stroke:'#90a5be','stroke-width':2+3*Math.log1p(e.sum_kzt)/maxLog,opacity:.62,'marker-end':'url(#arrow)',class:'graph-edge','data-src':e.src,'data-dst':e.dst});
    line.append(svgEl('title',{},`${e.src} → ${e.dst}\n${fmt(e.sum_kzt)} KZT · ${e.n_tx} переводов`));svg.append(line);
    if(data.edges.length<=8) svg.append(svgEl('text',{x:(x1+x2)/2,y:(y1+y2)/2-7,'text-anchor':'middle',class:'edge-label'},`${fmt(e.sum_kzt)} KZT`));
  });
  data.nodes.forEach(n=>{
    const p=positions.get(n.gid),center=n.gid===data.center_gid;
    const group=svgEl('g',{class:'graph-node'+(n.cluster_id===selectedCluster?' same-cluster':''),tabindex:0,role:'button','aria-label':`Открыть GID ${n.gid}, ${n.role}`});
    if(center) group.append(svgEl('circle',{cx:p.x,cy:p.y,r:34,fill:colors[n.role],opacity:.10}));
    group.append(svgEl('circle',{cx:p.x,cy:p.y,r:center?23:12,fill:colors[n.role],stroke:n.is_seed?'#203c56':'#fff','stroke-width':n.is_seed?2:1.5}));
    if(center||data.nodes.length<=32) group.append(svgEl('text',{x:p.x,y:p.y+(center?53:31),'text-anchor':'middle',class:'node-label'},center?n.gid:'…'+n.gid.slice(-6)));
    if(center) group.append(svgEl('text',{x:p.x,y:p.y+85,'text-anchor':'middle',class:'node-label'},n.role));
    group.append(svgEl('title',{},`${n.gid}\n${n.role} · priority ${fixed(n.priority_score)} · cluster ${n.cluster_id}`));
    group.addEventListener('click',()=>selectNode(n.gid));group.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();selectNode(n.gid);}});svg.append(group);
  });
  if(!data.edges.length) svg.append(svgEl('text',{x:600,y:460,'text-anchor':'middle',class:'node-label'},'Изолированный узел: связей в выгрузке нет'));
  applyZoom();
  $('role-legend').innerHTML=Object.keys(colors).map(role=>`<span>${dot(role)}${role}</span>`).join('');
  $('edge-count').textContent=`· ${data.edges.length}`;
  $('edge-table').innerHTML=data.edges.length?`<table><thead><tr><th>Отправитель → получатель</th><th>KZT</th><th>Переводы</th></tr></thead><tbody>${data.edges.map(e=>`<tr><td><button data-gid="${esc(e.src)}">${esc(e.src)}</button> → <button data-gid="${esc(e.dst)}">${esc(e.dst)}</button></td><td>${fmt(e.sum_kzt)}</td><td>${e.n_tx}</td></tr>`).join('')}</tbody></table>`:'<p class="graph-help">Наблюдаемых переводов нет.</p>';
  attachNodeLinks($('edge-table'));
}
function applyZoom(){ $('network').style.width=`${state.zoom*100}%`; $('network').style.height=`${state.zoom*100}%`; }
function renderCluster(c){$('cluster-panel').innerHTML=`<h3>Кластер ${c.cluster_id} <span class="chip">${c.n_nodes} узлов · ${c.n_seed} seed</span></h3><p>${esc(c.hypothesis)}<br>Наблюдаемый внутренний оборот: ${fmt(c.sum_kzt_internal)} KZT</p><p class="label">Приоритетные узлы кластера</p>${c.top_gids.map(gid=>`<button data-gid="${esc(gid)}">${esc(gid)}</button>`).join('')}`;attachNodeLinks($('cluster-panel'));}
$('search-form').addEventListener('submit',async event=>{event.preventDefault();const request=++state.searchSeq;const q=$('gid-search').value.trim();clearError();$('search-results').hidden=false;$('search-results').textContent='Поиск…';try{const data=await api(`/api/search?q=${encodeURIComponent(q)}`);if(request!==state.searchSeq)return;if(data.exact){await selectNode(data.items[0].gid);return;}$('search-results').innerHTML=data.items.length?`<p class="small">Совпадений: ${data.total}. Показано ${data.items.length}.</p>${data.items.map(n=>`<button data-gid="${esc(n.gid)}">${esc(n.gid)} · ${esc(n.role)}</button>`).join('')}`:'<p>Узел не найден. Введите полный GID или его начало.</p>';attachNodeLinks($('search-results'));}catch(error){$('search-results').textContent='Поиск недоступен';showError(error);}});
document.querySelectorAll('[data-queue]').forEach(button=>button.addEventListener('click',()=>{state.queue=button.dataset.queue;state.offset=0;loadQueue();}));
$('prev-page').addEventListener('click',()=>{state.offset=Math.max(0,state.offset-state.limit);loadQueue();});
$('next-page').addEventListener('click',()=>{state.offset+=state.limit;loadQueue();});
$('cluster-toggle').addEventListener('click',()=>{state.clusterHighlight=!state.clusterHighlight; $('cluster-toggle').setAttribute('aria-pressed',String(state.clusterHighlight)); $('network').classList.toggle('cluster-highlight',state.clusterHighlight);});
$('zoom-in').addEventListener('click',()=>{state.zoom=Math.min(3,state.zoom+.25);applyZoom();});
$('zoom-out').addEventListener('click',()=>{state.zoom=Math.max(.5,state.zoom-.25);applyZoom();});
$('zoom-fit').addEventListener('click',()=>{state.zoom=1;applyZoom();$('graph-viewport').scrollTo(0,0);});
async function boot(){try{const s=await api('/api/summary');const cards=[['Узлы',s.total_nodes,`${s.total_transactions} транзакций`,''],['Направленные связи',s.total_edges,`${fmt(s.total_observed_turnover)} KZT`,''],['Кластеры',s.n_clusters,'Все узлы, включая изоляты',''],['Проверить сейчас',s.queue_counts.INVESTIGATE_NOW,'INVESTIGATE NOW','teal'],['Запросить данные',s.queue_counts.REQUEST_MORE_DATA,'REQUEST MORE DATA','amber']];$('kpis').innerHTML=cards.map(([title,value,sub,color])=>`<div class="kpi ${color}"><label>${title}</label><strong>${fmt(value)}</strong><small>${esc(sub)}</small></div>`).join('');$('count-now').textContent=s.queue_counts.INVESTIGATE_NOW;$('count-data').textContent=s.queue_counts.REQUEST_MORE_DATA;$('count-monitor').textContent=s.queue_counts.MONITOR;const linked=new URLSearchParams(location.search).get('gid');if(linked){state.gid=linked;await selectNode(linked);}await loadQueue();}catch(error){showError(error);$('kpis').innerHTML='<p>Не удалось загрузить данные. Проверьте локальный сервер и обновите страницу.</p>';}}
boot();


let aiSequence=0, aiController=null, aiAvailable=false;
function resetAnalystNode(gid) {
  aiSequence++; if(aiController) aiController.abort(); aiController=null;
  $('ai-archive-link').href='/ai-archive?gid='+encodeURIComponent(gid);
  $('ai-gid').textContent=gid; $('ai-answer').replaceChildren(); $('ai-activity').textContent='';
  $('ai-submit').disabled=!aiAvailable; $('ai-downstream').disabled=!aiAvailable;
}
function renderAnalystEvent(event) {
  if(event.type==='activity') {
    const line=document.createElement('p'); line.textContent=(event.source?'✓ ':'… ')+String(event.message||'');
    $('ai-activity').append(line); return;
  }
  if(event.type==='error') throw new Error(String(event.message||'AI недоступен'));
  if(event.type!=='result') throw new Error('Неизвестный формат AI');
  const a=event.answer;
  if(!a || !Array.isArray(a.why) || !a.why.every(x=>typeof x==='string') ||
      !['conclusion','alternative','evidence_against','limitation','next_step'].every(k=>typeof a[k]==='string') || !Array.isArray(event.trace)) throw new Error('Некорректный ответ AI');
  const labels={conclusion:'Вывод',why:'Наблюдаемые основания',alternative:'Альтернатива',evidence_against:'Что ослабляет гипотезу',limitation:'Ограничение',next_step:'Следующий шаг'};
  $('ai-answer').replaceChildren();
  for(const [key,label] of Object.entries(labels)) {
    const block=document.createElement('section'), heading=document.createElement('h4'), text=document.createElement('p');
    heading.textContent=label; text.textContent=key==='why'?a.why.join('\n'):a[key]; block.append(heading,text); $('ai-answer').append(block);
  }
  const meta=document.createElement('p'); meta.className='explanation';
  meta.textContent=`${event.model} · ${event.latency_seconds} с · ${event.notice}`; $('ai-answer').append(meta);
  const sources=document.createElement('details'), title=document.createElement('summary'), list=document.createElement('p');title.textContent='Проверенные источники: инструменты';
  list.textContent=event.trace.map(t=>`${t.source_id}: ${t.tool} (${Object.values(t.arguments).join(', ')})`).join('\n');sources.append(title,list);$('ai-answer').append(sources);
}
async function askAnalyst(question,sourceGids=null) {
  if(!state.gid || !aiAvailable) return;
  if(aiController) aiController.abort(); aiController=new AbortController();
  const seq=++aiSequence, gid=state.gid, controller=aiController;
  $('ai-answer').replaceChildren();$('ai-activity').textContent='';$('ai-submit').disabled=true; $('ai-downstream').disabled=true;
  const timer=setTimeout(()=>controller.abort(),150000);
  try {
    const response=await fetch('/api/analyst/ask',{method:'POST',headers:{'Content-Type':'application/json'},signal:controller.signal,
      body:JSON.stringify({gid,question,compare_gid:sourceGids?null:($('ai-other').value.trim()||null),source_gids:sourceGids})});
    if(!response.ok) throw new Error(`Запрос отклонён (${response.status}). Проверьте GID.`);
    const reader=response.body.getReader(), decoder=new TextDecoder(); let buffer='',completed=false;
    while(true) {
      const {done,value}=await reader.read(); if(seq!==aiSequence) {await reader.cancel();return;}
      buffer+=decoder.decode(value||new Uint8Array(),{stream:!done});
      let boundary;
      while((boundary=buffer.indexOf('\n'))>=0) {
        const line=buffer.slice(0,boundary);buffer=buffer.slice(boundary+1);if(!line.trim())continue;
        const event=JSON.parse(line);renderAnalystEvent(event); if(event.type==='result')completed=true;
      }
      if(done)break;
    }
    if(!completed)throw new Error('AI не завершил ответ. Повторите запрос.');
  } catch(error) {
    if(seq===aiSequence) { $('ai-answer').textContent=error.name==='AbortError'?'Запрос остановлен или истекло время ожидания.':(error.message||'AI недоступен'); }
  } finally { clearTimeout(timer);if(seq===aiSequence){$('ai-submit').disabled=!aiAvailable; $('ai-downstream').disabled=!aiAvailable;aiController=null;} }
}
$('ai-form').addEventListener('submit',e=>{e.preventDefault();askAnalyst($('ai-question').value.trim());});
document.querySelectorAll('[data-ai-prompt]').forEach(b=>b.addEventListener('click',()=>{$('ai-question').value=b.dataset.aiPrompt;askAnalyst(b.dataset.aiPrompt);}));
$('ai-compare').addEventListener('click',()=>{$('ai-question').value='Почему выбранный узел выше или ниже другого? Назови также преимущество второго узла, если оно есть.';$('ai-other').focus();});
api('/api/analyst/status').then(s=>{aiAvailable=s.available;$('ai-status').textContent=s.message;$('ai-submit').disabled=!aiAvailable; $('ai-downstream').disabled=!aiAvailable;document.querySelectorAll('[data-ai-prompt]').forEach(b=>b.disabled=!aiAvailable);}).catch(()=>{$('ai-status').textContent='AI analyst unavailable';$('ai-submit').disabled=true; $('ai-downstream').disabled=true;});


let resilienceSeq=0;
async function loadResilience(n) {
  const seq=++resilienceSeq;
  $('resilience-result').textContent='Загружаем рассчитанный сценарий…';
  try {
    const data=await api('/api/resilience?n='+n);if(seq!==resilienceSeq)return;
    document.querySelectorAll('[data-removal]').forEach(b=>b.setAttribute('aria-pressed',String(Number(b.dataset.removal)===n)));
    const rows=[['Узлы','nodes'],['Слабосвязные компоненты','weak_components'],['Крупнейшая компонента','largest_component'],['Изолированные узлы','isolated_nodes'],['Достижимы от seed','seed_reachable_nodes'],['Оставшиеся seed','remaining_seeds'],['Компоненты с несколькими seed','multi_seed_components']];
    const loss=data.reachability_loss;
    const percent=value=>value===null?'N/A':fmt(value*100)+'%';
    $('resilience-result').innerHTML=`<p><strong>${n?'Гипотетически удалено узлов: '+data.removed_count:'Исходный граф · удаление не применяется'}</strong></p><div class="resilience-table"><table><thead><tr><th>Показатель</th><th>До</th><th>После</th></tr></thead><tbody>${rows.map(([label,key])=>`<tr><td>${label}</td><td>${data.before[key]}</td><td>${data.after[key]}</td></tr>`).join('')}</tbody></table></div><p>Общая потеря достижимости: <strong>${percent(loss.total_fraction)}</strong> (${loss.total_nodes} узлов).</p><p class="explanation">Из ранее достижимых удалено узлов: ${loss.removed_previously_reachable}; ещё ${loss.lost_surviving_nodes} оставшихся потеряли путь от seed (${percent(loss.surviving_fraction)} от ранее достижимых оставшихся). Seed включает себя в достижимость.</p><p>Дополнительных фрагментов при распаде: <strong>${data.new_fragments}</strong>. Изменение числа компонент: ${data.component_count_delta>=0?'+':''}${data.component_count_delta}. Полностью исчезнувших компонент: ${data.fully_removed_components}.</p>${data.removed_nodes.length?`<details><summary>Удалённые GID · seed среди них: ${data.removed_seed_gids.length}</summary><ul>${data.removed_nodes.map(node=>`<li>${esc(node.gid)} ${node.is_seed?'· SEED':''} · priority ${fixed(node.priority_score)}</li>`).join('')}</ul></details>`:''}<p class="explanation">Расчёт сценария: ${fmt(data.runtime_seconds*1000)} мс. Компоненты связности и рассчитанные кластеры — разные понятия.</p>`;
  }catch(error){if(seq===resilienceSeq)$('resilience-result').textContent='Симуляция недоступна: '+error.message;}
}
document.querySelectorAll('[data-removal]').forEach(b=>b.addEventListener('click',()=>loadResilience(Number(b.dataset.removal))));
loadResilience(0);

$('ai-downstream').addEventListener('click',()=>{
  const gids=[...new Set($('ai-sources').value.trim().split(/[\s,;]+/).filter(Boolean))];
  if(gids.length<1||gids.length>5||!gids.every(g=>/^[0-9]{1,20}$/.test(g))){$('ai-answer').textContent='Введите от 1 до 5 точных GID через пробел или запятую.';return;}
  const question='Кто может собирать деньги с этих узлов? Найди общих кандидатов по наблюдаемым направленным путям; отдельно укажи частичное покрытие. Это не доказательство движения тех же денег.';
  $('ai-question').value=question;askAnalyst(question,gids);
});
