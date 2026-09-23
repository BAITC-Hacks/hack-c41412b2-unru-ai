'use strict';
// Presentation only: edge facts come from the existing ego response.
function edgeFactsHTML(edge,nodes,center,links=false) {
  const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const role=gid=>MoneyGraphUI.localize(nodes.get(gid)?.role||'Роль не определена');
  const id=gid=>links?`<button type="button" data-edge-gid="${escape(gid)}">${escape(gid)}</button>`:`<span>${escape(gid)}</span>`;
  return `<div class="edge-direction">${edge.dst===center?'Входящий перевод в выбранный узел':'Исходящий перевод из выбранного узла'}</div><div class="edge-endpoint"><b>Отправитель</b> ${id(edge.src)}<small>${escape(role(edge.src))}</small></div><div class="edge-endpoint"><b>Получатель</b> ${id(edge.dst)}<small>${escape(role(edge.dst))}</small></div><div class="edge-totals"><strong>${new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2}).format(edge.sum_kzt)} ₸</strong><span>Переводов: ${escape(edge.n_tx)}</span></div>`;
}
function createEdgeInspector(openNode) {
  const tip=document.getElementById('edge-tooltip'),panel=document.getElementById('edge-inspection');
  let timer=null,hovered=null,pinned=null;
  function hideTip(){clearTimeout(timer);timer=null;tip.hidden=true;if(hovered&&hovered!==pinned)hovered.classList.remove('edge-active');hovered=null;}
  function reset(){hideTip();if(pinned){pinned.classList.remove('edge-active');pinned=null;}panel.hidden=true;panel.replaceChildren();}
  function position(x,y){
    const rect=tip.getBoundingClientRect(),margin=12;
    let left=x+18,top=y+18;
    if(left+rect.width>window.innerWidth-margin)left=x-rect.width-18;
    if(top+rect.height>window.innerHeight-margin)top=y-rect.height-18;
    tip.style.left=Math.max(margin,Math.min(left,window.innerWidth-rect.width-margin))+'px';
    tip.style.top=Math.max(margin,Math.min(top,window.innerHeight-rect.height-margin))+'px';
  }
  function bind(target,line,edge,nodes,center){
    function show(event,delay){
      hideTip();hovered=line;line.classList.add('edge-active');
      const rect=target.getBoundingClientRect(),x=event.clientX??(rect.left+rect.width/2),y=event.clientY??(rect.top+rect.height/2);
      timer=setTimeout(()=>{tip.innerHTML=edgeFactsHTML(edge,nodes,center)+'<p>Нажмите, чтобы закрепить детали. Роли — гипотезы.</p>';tip.hidden=false;const current=target.getBoundingClientRect();position(event.type==='focus'?current.left+current.width/2:x,event.type==='focus'?current.top+current.height/2:y);},delay);
    }
    target.addEventListener('pointerenter',e=>{if(e.pointerType!=='touch')show(e,120);});
    target.addEventListener('pointerleave',hideTip);
    target.addEventListener('focus',e=>show(e,0));
    target.addEventListener('blur',hideTip);
    function pin(){
      hideTip();if(pinned)pinned.classList.remove('edge-active');pinned=line;line.classList.add('edge-active');
      panel.innerHTML='<div class="edge-detail-head"><h3>Выбранная связь</h3><button type="button" class="edge-close" aria-label="Закрыть детали связи">×</button></div>'+edgeFactsHTML(edge,nodes,center,true)+'<p class="explanation">Сумма всех наблюдаемых переводов по этому направлению за июль 2026. Роли узлов — гипотезы. Точные даты операций в этом представлении не передаются.</p>';
      panel.hidden=false;panel.querySelector('.edge-close').addEventListener('click',()=>{reset();target.focus();hideTip();});
      panel.querySelectorAll('[data-edge-gid]').forEach(b=>b.addEventListener('click',()=>openNode(b.dataset.edgeGid)));
      panel.scrollIntoView({block:'nearest',behavior:'smooth'});
    }
    target.addEventListener('click',pin);
    target.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();pin();}});
  }
  document.addEventListener('keydown',e=>{if(e.key==='Escape')reset();});
  window.addEventListener('resize',hideTip);
  document.addEventListener('scroll',()=>{if(!document.activeElement?.classList.contains('edge-hit'))hideTip();},true);
  return {bind,reset};
}
