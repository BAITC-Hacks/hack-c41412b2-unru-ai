'use strict';
// Display-only glossary. Never changes API payloads, input values, enums or files.
const MoneyGraphUI = (() => {
  const terms = {
    'AI analyst unavailable: OPENAI_API_KEY отсутствует':'ИИ-помощник недоступен: ключ сервиса не настроен',
    'Схождение seed':'Схождение путей от исходных узлов',
    'Внешних seed в расчёте':'Внешних исходных узлов в расчёте',
    'пересекаться upstream':'пересекаться на предыдущих участках',
    'больше числа seed':'больше числа исходных узлов',
    'от внешнего seed':'от внешнего исходного узла',
    'от любого seed':'от любого исходного узла',
    'начат с seed':'начат с исходных узлов',
    'видимость upstream':'видимость предшествующей истории',
    'Отклонения от depth=':'Отклонения среди узлов колена ',
    'Граница depth=4':'Граница 4-го колена',
    'Исходящие CENSORED: depth=4':'Исходящие обрезаны выборкой: 4-е колено',
    'strongest alternative':'наиболее сильная альтернатива',
    'primary':'основная гипотеза','alternative':'альтернативная гипотеза',
    'in_degree':'число отправителей','out_degree':'число получателей','neighbor_count':'число соседей',
    'observability':'достаточность данных','pagerank':'структурная значимость',
    'structural_dependency':'зависимость наблюдаемых путей','Dominator':'Зависимость наблюдаемых путей',
    'fan-out':'число получателей','gid':'ID узла','null':'отсутствует',
    'AI analyst unavailable':'ИИ-помощник недоступен',
    'FINANCIAL NETWORK INTELLIGENCE':'АНАЛИЗ ФИНАНСОВОЙ СЕТИ',
    'AI INVESTIGATION ANALYST':'ИИ-ПОМОЩНИК АНАЛИТИКА',
    'AI Investigation Analyst':'ИИ-помощник аналитика',
    'NETWORK RESILIENCE':'УСТОЙЧИВОСТЬ СЕТИ',
    'Network Resilience':'Устойчивость сети',
    'INVESTIGATE_NOW':'Проверить сейчас','INVESTIGATE NOW':'Проверить сейчас',
    'REQUEST MORE DATA':'Запросить данные','REQUEST_MORE_DATA':'Запросить данные','MONITOR':'Наблюдать',
    'OBSERVABILITY':'ДОСТАТОЧНОСТЬ ДАННЫХ','ORDER UNKNOWN':'ПОРЯДОК НЕИЗВЕСТЕН',
    'NOT_EVALUABLE':'Нельзя оценить','SMALL_COHORT':'Малая группа сравнения',
    'STABLE':'Устойчиво','SENSITIVE':'Чувствительно',
    'CENSORED':'Обрезано выборкой','AVAILABLE':'Доступно','PARTIAL':'Частично',
    'HIGH':'Высокая','MEDIUM':'Средняя','LOW':'Низкая','N/A':'Нельзя оценить',
    'consolidator':'точка консолидации','coordinator':'координирующий узел',
    'distributor':'распределитель','transit':'транзитный узел',
    'terminal':'предполагаемый конечный получатель','peripheral':'периферийный узел',
    'Transit evidence':'Признаки транзита','Terminal evidence':'Признаки конечного получателя',
    'primary_role':'основная гипотеза','primary_strength':'сила основной гипотезы',
    'alternative_role':'альтернативная гипотеза','alternative_strength':'сила альтернативы',
    'role_score':'сила признаков роли','role_strength':'сила признаков роли',
    'priority_score':'приоритет проверки','queue_reason':'основание очереди',
    'baseline_role':'исходная гипотеза','observability_score':'достаточность данных',
    'observed_out_in_ratio':'отношение наблюдаемого выхода ко входу',
    'fan_out':'число получателей','fan_in':'число отправителей',
    'effective_last_hop_branches':'разнообразие входящих ветвей',
    'reachable_seed_count':'достижимость от исходных узлов',
    'min_hops':'минимум переходов','max_hops':'максимум переходов',
    'hop_limit':'предел переходов','returned_candidates':'показано кандидатов',
    'total_candidates':'всего кандидатов','truncated':'выдача сокращена',
    'get_node_profile':'Профиль узла','get_structural_evidence':'Структурные основания',
    'get_data_gaps':'Недостающие данные','compare_nodes':'Сравнение узлов',
    'get_neighbors':'Связи узла','get_cluster_context':'Контекст кластера',
    'find_common_downstream':'Общие получатели по направленным путям',
    'gather→scatter':'сбор → распределение','Gather→scatter':'Сбор → распределение',
    'last-hop diversity':'разнообразие входящих ветвей','downstream':'дальше по направлению переводов',
    'upstream':'предшествующая история','follow-up':'период последующего наблюдения',
    'Same-day':'В один день','same-day':'в один день',
    'Stability':'Устойчивость','depth-peer':'группа того же колена','peer':'сопоставимый узел',
    'TOP':'ТОП','GID':'ID узла','DEPTH':'КОЛЕНО','SEED':'ИСХОДНЫЙ УЗЕЛ',
    'depth':'колено','Seed':'Исходный узел','seed':'исходный узел','KZT':'₸',
    'accuracy':'точность классификации','dominator':'зависимость наблюдаемых путей',
    'directed':'направленный','raw':'исходный','flags':'сигналы',
    'HOP':'ПЕРЕХОД','hop':'переход','baseline':'исходный расчёт',
    'strength':'сила признаков','queue':'очередь','priority':'приоритет','role':'гипотеза роли','AI':'ИИ',
    'data gaps':'недостающие данные','true':'да','false':'нет'
  };
  const escapeRegex=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
  const keys=Object.keys(terms).sort((a,b)=>b.length-a.length);
  const pattern=new RegExp('(?<![A-Za-z0-9_])('+keys.map(escapeRegex).join('|')+')(?![A-Za-z0-9_])','g');
  function localize(value) {
    return String(value).replace(pattern,m=>terms[m])
      .replace(/Наблюдаемость/g,'Достаточность данных').replace(/наблюдаемость/g,'достаточность данных')
      .replace(/наблюдаемости/g,'достаточности данных').replace(/Пригодность наблюдений/g,'Достаточность данных')
      .replace(/пригодность/g,'достаточность данных').replace(/OBSERVABILITY/g,'ДОСТАТОЧНОСТЬ ДАННЫХ')
      .replace(/(\d+) исходный узел/g,'$1 исходных узлов').replace(/от исходный узел/g,'от исходных узлов')
      .replace(/для исходный узел/g,'для исходных узлов').replace(/У исходный узел/g,'У исходных узлов')
      .replace(/у исходный узел/g,'у исходных узлов').replace(/исходный узел=/g,'исходных узлов: ')
      .replace(/внешних исходный узел/g,'внешних исходных узлов').replace(/исходный узел-клиентов/g,'исходных клиентов')
      .replace(/Оставшиеся исходный узел/g,'Оставшиеся исходные узлы').replace(/несколькими исходный узел/g,'несколькими исходными узлами')
      .replace(/Исходные ID узла/g,'ID исходных узлов').replace(/исходному приоритет проверки/g,'исходному приоритету проверки');
  }
  function excluded(element){return !element||element.closest('script,style,textarea,input,code,pre,[data-original],[data-brand]');}
  function translateNode(node) {
    if(node.nodeType===3) {
      if(!excluded(node.parentElement)){const translated=localize(node.nodeValue);if(translated!==node.nodeValue)node.nodeValue=translated;}
      return;
    }
    if(node.nodeType!==1 || (excluded(node) && !['INPUT','TEXTAREA'].includes(node.tagName)))return;
    for(const key of ['aria-label','title','placeholder']) {
      const current=node.getAttribute(key);if(current){const translated=localize(current);if(current!==translated)node.setAttribute(key,translated);}
    }
    if(['INPUT','TEXTAREA'].includes(node.tagName))return;
    // Input labels may be translated; form values and submitted questions never are.
    for(const child of node.childNodes)translateNode(child);
  }
  function start(){
    translateNode(document.body);
    const observer=new MutationObserver(records=>{
      for(const record of records){
        if(record.type==='childList')for(const node of record.addedNodes)translateNode(node);
        else if(record.type==='characterData')translateNode(record.target);
        else if(record.type==='attributes')translateNode(record.target);
      }
    });
    observer.observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['aria-label','title','placeholder']});
  }
  return {localize,start};
})();
if(typeof document!=='undefined')MoneyGraphUI.start();
