'use strict';
const $=id=>document.getElementById(id);
let archive=null;
function text(tag,value,parent){const e=document.createElement(tag);e.textContent=value;parent.append(e);return e;}
function showRecord(record){
 const root=$('archive-result');root.replaceChildren();
 text('p','АРХИВ · РЕАЛЬНЫЙ API-ЗАПРОС ВЫПОЛНЕН РАНЕЕ',root).className='eyebrow';
 text('h3',record.question,root);
 const result=record.result;
 text('p',`${archive.manifest.run_date} · ${result.model} · длительность исходного запроса ${result.latency_seconds} с`,root).className='small';
 const nodes=text('p','Узлы: ',root);
 for(const gid of [record.gid,record.compare_gid].filter(Boolean)){const a=text('a',gid,nodes);a.href='/?gid='+encodeURIComponent(gid);text('span',' ',nodes);}
 const names={conclusion:'Вывод модели',why:'Наблюдаемые основания',alternative:'Альтернатива',evidence_against:'Что ослабляет гипотезу',limitation:'Ограничение',next_step:'Предложенный следующий шаг'};
 for(const [field,label]of Object.entries(names)){const section=text('section','',root);text('h4',label,section);text('p',Array.isArray(result.answer[field])?result.answer[field].join('\n'):result.answer[field],section);}
 const log=text('details','',root);text('summary','Журнал инструментов исходного запроса',log);
 text('p',result.trace.map(t=>`${t.source_id} · ${t.tool} (${Object.values(t.arguments).join(', ')})`).join('\n'),log);
 text('p','Это сохранённый результат. Инструменты сейчас не выполнялись; модель могла допустить ошибки интерпретации.',root).className='explanation';
 document.querySelectorAll('[data-record]').forEach(b=>b.classList.toggle('selected',b.dataset.record===record.id));
}
function filterRecords(gid){
 const records=archive.records.filter(r=>!gid||r.gid===gid||r.compare_gid===gid);
 $('archive-list').replaceChildren();$('archive-result').replaceChildren();
 if(!records.length){text('p','Для этого GID сохранённых AI-ответов нет. Это не означает, что узел отсутствует в графе. Откройте все демо или используйте живой AI с настроенным ключом.',$('archive-result'));return;}
 for(const record of records){const button=text('button',record.question,$('archive-list'));button.type='button';button.dataset.record=record.id;text('small',record.gid+(record.compare_gid?' ↔ '+record.compare_gid:''),button);button.addEventListener('click',()=>showRecord(record));}
 showRecord(records[0]);
}
$('archive-filter').addEventListener('submit',e=>{e.preventDefault();if(archive)filterRecords($('archive-gid').value.trim());});
$('archive-all').addEventListener('click',()=>{if(archive){$('archive-gid').value='';filterRecords('');}});
(async()=>{try{
 const response=await fetch('/api/analyst/archive');if(!response.ok)throw Error('Архив недоступен');
 const data=await response.json();if(!data.available)throw Error(data.message);
 archive=data;
 $('archive-summary').textContent=`${data.records.length} сохранённых вопросов · дата демо ${data.manifest.run_date}`;
 $('archive-warning').textContent=data.current_data_matches?'Данные и расчёты совпадают с версией сохранённого демо.':'Текущие данные или расчёты отличаются от исходного демо. Архивные ответы относятся только к прежней версии.';
 const manifest=data.manifest;
 text('p',manifest.provenance_note,$('archive-provenance'));
 text('p',`${manifest.run_time_note}\nСохранено в архив: ${manifest.archived_at_utc}\nКоммит исходной записи: ${manifest.source_commit}\nФайл: ${manifest.source_path}\nSHA-256: ${manifest.source_sha256}`,$('archive-provenance'));
 const gid=new URLSearchParams(location.search).get('gid')||'';$('archive-gid').value=gid;filterRecords(gid);
}catch(error){$('archive-summary').textContent=error.message||'Не удалось прочитать архив';}})();
