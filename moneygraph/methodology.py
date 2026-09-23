"""Read-only documentation rendered from trusted Python rules and saved results."""
import ast
import inspect
from html import escape as e
from types import SimpleNamespace
from . import roles, observability, communities
from .analyst import TOOLS

NAMES = {'coordinator':'Координирующий узел','distributor':'Распределитель','consolidator':'Точка консолидации','transit':'Транзитный узел','terminal':'Предполагаемый конечный получатель','peripheral':'Периферийный узел'}
FIELDS = {'in_degree':'I','out_degree':'O','in_tx':'Ti','out_tx':'To','in_days':'Di','reachable_seed_count':'S','observed_out_in_ratio':'R','in_percentile':'Pi','out_percentile':'Po','pagerank_percentile':'Ppr','in_max_share':'Mi','out_max_share':'Mo'}
DESCRIPTIONS = {'coordinator':'Сочетание входящих, исходящих связей и достижимости от нескольких исходных узлов. Не доказательство управления другими клиентами.', 'distributor':'Распределение нескольким получателям; учитываются ширина веера, распределённость сумм и исходящий оборот.', 'consolidator':'Несколько отправителей при относительно ограниченном исходящем распределении. Не доказательство сбора денег для общей цели.', 'transit':'Сходство наблюдаемых месячных входящих и исходящих сумм. Не отслеживание конкретных денег.', 'terminal':'Повторный приём без наблюдаемого выхода внутри границы обхода. Удержание денег не доказано; исходные узлы и четвёртое колено исключены.', 'peripheral':'Ни одна из пяти гипотез не получила положительной силы признаков. Не означает безопасность.'}


def rule_specs():
    """Extract exact predicates, helper expressions and additive terms; no copied weights."""
    result = {}
    tree = ast.parse(inspect.getsource(roles.classify_row))
    for block in tree.body[0].body:
        if not isinstance(block, ast.If):
            continue
        helpers = {}
        for item in block.body:
            if not isinstance(item, ast.Assign):
                continue
            target = item.targets[0]
            if isinstance(target, ast.Name):
                helpers[target.id] = item.value
            elif isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) and target.value.id == 'strengths':
                result[target.slice.value] = {'condition':block.test,'expression':item.value,'helpers':helpers.copy()}
    return result


def expression(node):
    text = ast.unparse(node)
    for field, label in FIELDS.items():
        text = text.replace('r.' + field, label)
    return text.replace('r.', '').replace(' * ', ' × ').replace(' and ', ' И ').replace('not ', 'НЕ ')


def evaluate(node, context):
    # Only AST extracted from our installed rules, never expressions from requests.
    return eval(compile(ast.Expression(node), '<installed-role-rule>', 'eval'), {'__builtins__':{},'min':min,'max':max,'abs':abs}, context)


def terms(node):
    return terms(node.left) + terms(node.right) if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add) else [node]


def breakdown(record, name):
    if name == 'peripheral':
        eligible = all(breakdown(record, role)['score'] == 0 for role in roles.ROLE_ORDER)
        return {'eligible':eligible,'terms':[],'score':0.0,'inputs':{}}
    spec = rule_specs()[name]
    r = SimpleNamespace(**record)
    context = {'r':r}
    eligible = bool(evaluate(spec['condition'], context))
    if eligible:
        for key, value in spec['helpers'].items():
            context[key] = evaluate(value, context)
    fields = sorted({n.attr for tree in [spec['condition'],spec['expression'],*spec['helpers'].values()] for n in ast.walk(tree) if isinstance(n,ast.Attribute) and isinstance(n.value,ast.Name) and n.value.id=='r'})
    values = [float(evaluate(t,context)) for t in terms(spec['expression'])] if eligible else []
    return {'eligible':eligible,'terms':values,'score':sum(values),'inputs':{FIELDS.get(f,f):record[f] for f in fields}}


def code(value):
    return '<pre><code>' + e(str(value)) + '</code></pre>'


def table(headers, rows):
    return '<div class="table-scroll"><table><thead><tr>'+''.join('<th>'+e(str(h))+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+e(('Да' if v else 'Нет') if isinstance(v,bool) else ('Не определено' if v is None else str(v)))+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table></div>'


def render(store, resilience, gid=None):
    selected = store.node(gid) if gid else None
    report = store.report
    sections = []
    def add(anchor, title, body, badge='ОСНОВНОЙ РАСЧЁТ'):
        sections.append((anchor,title,f'<details class="method-section panel" id="{anchor}"><summary>{len(sections)+1}. {title}</summary><div class="method-body"><span class="chip">{badge}</span>{body}</div></details>'))
    add('data','Исходные данные', table(['Показатель','Значение'],[(label,report[key]) for key,label in [('nodes','Узлы'),('edges','Направленные связи'),('transactions','Транзакции'),('seed','Исходные узлы')]])+'<p>Июль 2026 · один банк · операции от 5 000 ₸ · исходящий обход до четвёртого колена. Внешние входящие операции не представлены. Одинаковые строки не удаляем автоматически: это могут быть разные операции. Проверки сумм используют целые тиыны.</p>'+code(f"{report['seed']} исходных узлов → колено 1 → 2 → 3 → 4 → дальше данных нет"))
    add('graph','Как строится граф',f'<p>Вершина — обезличенный клиент (GID), направленное ребро A → B — наблюдаемые переводы. Вес: сумма в тиынах <code>sum_tiyn</code>, эквивалентная <code>sum_kzt × 100</code>; число операций — <code>n_tx</code>. Все узлы из nodes.parquet сохраняются.</p>'+code(f"{report['weak_components_edge_graph']} компонент по рёбрам + {report['isolated']} изолированных узлов = {report['weak_components_all_nodes']} компонент полного графа"))
    metrics=[('I / O','Уникальные отправители / получатели','Только видимые связи'),('Ti / To','Входящие / исходящие операции','Повторные строки сохранены'),('Di','Дни с входящими операциями','Дата без времени суток'),('S','Число достигающих исходных узлов','Включает самого исходного; не независимые потоки'),('R','Исходящая сумма / входящая','Не полный баланс; при нулевом входе не определено'),('Pi / Po','Процентили входящего / исходящего оборота','Средний ранг среди положительных значений'),('Ppr','Процентиль PageRank','Изоляты исключены; не вероятность нарушения'),('Mi / Mo','Доля крупнейшего отправителя / получателя','Максимальная сумма ребра / сумма стороны; ноль без потока'),('Pvolume','Процентиль входа + выхода','Оборот, не остаток средств'),('Pneighbors','Процентиль числа соседей','Объединение отправителей и получателей')]
    add('metrics','Базовые признаки узла',table(['Обозначение','Смысл','Ограничение'],metrics)+'<p>Неположительные значения получают нулевой процентиль. PageRank использует веса сумм, коэффициент затухания 0,85; он дополняет структурную картину. Эти признаки используются в ролях и приоритете.</p>')
    cards=[]
    for name in [*roles.ROLE_ORDER,'peripheral']:
        spec=rule_specs().get(name)
        formula=code(expression(spec['expression'])) if spec else code('role_score = 0')
        condition=code(expression(spec['condition'])) if spec else '<p>Все силы пяти ролей равны нулю.</p>'
        helper=''.join(code(k+' = '+expression(v)) for k,v in spec['helpers'].items()) if spec else ''
        example=selected or next(n for n in store.nodes.values() if n['role']==name)
        b=breakdown(example,name)
        calc=' + '.join(f'{v:.6f}' for v in b['terms'])+' = '+f"{b['score']:.6f}" if b['eligible'] else 'Условие допуска не выполнено → сила этой гипотезы 0'
        cards.append(f'<article class="method-role" id="{name}"><h3>{NAMES[name]}</h3><small>Техническое имя: <code>{name}</code></small><p>{DESCRIPTIONS[name]}</p><h4>Условие допуска</h4>{condition}<h4>Формула из текущего кода</h4>{helper}{formula}<h4>{"Выбранный узел" if selected else "Пример из выгрузки"}: <a href="/?gid={e(example["gid"])}">{e(example["gid"])}</a></h4>'+table(['Входной признак','Значение'],[( {'is_seed':'Исходный узел','depth':'Колено','in_tiyn':'Вход, тиыны','out_tiyn':'Выход, тиыны'}.get(k,k),v) for k,v in b['inputs'].items()])+code(calc if b['terms'] or not b['eligible'] else 'Сила роли = 0')+'<p>Используется для гипотезы роли; сила признаков не является вероятностью действительной роли или виновности. Числа в примере округлены до 6 знаков.</p></article>')
    add('roles','Определение ролей','<p>Выбирается максимальная сила. При равенстве порядок: '+', '.join(NAMES[n] for n in roles.ROLE_ORDER)+'. Пороги и веса — интерпретируемые эвристики, не обучены на размеченных ролях. <code>min(x, 1)</code> ограничивает вклад единицей. В условиях <code>is_seed</code> — исходный узел, <code>depth</code> — колено.</p>'+''.join(cards))
    priority=next(n.value for n in ast.walk(ast.parse(inspect.getsource(roles.assign))) if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Subscript) and isinstance(n.targets[0].slice,ast.Constant) and n.targets[0].slice.value=='priority_score')
    add('priority','Приоритет проверки',code(ast.unparse(priority))+'<p>Имена <code>f.*</code> соответствуют признакам таблицы выше; <code>clip(upper=1)</code> ограничивает вклад единицей. Приоритет отвечает: кого полезнее проверить первым. У изолированных узлов он принудительно равен нулю. Достаточность данных не умножается на приоритет. Это порядок проверки, не вероятность нарушения.</p>')
    louvain=next(n for n in ast.walk(ast.parse(inspect.getsource(communities.assign))) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='louvain_communities')
    params=', '.join(k.arg+'='+ast.unparse(k.value) for k in louvain.keywords)
    multi=sum(c['n_seed']>1 for c in store.clusters.values())
    add('clusters','Кластеризация',f'<p>Louvain ищет структурные сообщества с относительно плотными внутренними связями. Неориентированная проекция складывает суммы встречных рёбер. Кластеров: {len(store.clusters)}; с несколькими исходными узлами: {multi}.</p>'+code(params)+'<p>Кластер — структурное разбиение, не доказательство общей преступной деятельности. Номера упорядочены по минимальному GID.</p>')
    obs_tree=ast.parse(inspect.getsource(observability.node_context))
    caps=[]
    for block in obs_tree.body[0].body:
        if not isinstance(block,ast.If): continue
        local={n.targets[0].id:n.value for n in block.body if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name)}
        for n in ast.walk(block):
            if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='limit':
                ceiling=n.args[1]
                if isinstance(ceiling,ast.Name): ceiling=local[ceiling.id]
                caps.append((expression(block.test),expression(ceiling)))

    level=next(n.value for n in ast.walk(obs_tree) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='level' for t in n.targets))
    add('observability','Достаточность данных','<p>Начальное значение 0,90 ограничивается минимумом применимых потолков, а не суммой штрафов. Это пригодность выгрузки для интерпретации гипотезы, не доля банковской истории. <code>isolated</code> — нет связей; <code>supported_days</code> — минимум входящих и исходящих дней для транзитной и координирующей роли, входящие дни для консолидации и конечного получателя, исходящие для распределителя, максимум двух сторон для периферии. В формуле <code>score</code> — полученная достаточность.</p>'+table(['Условие из кода','Потолок'],caps)+code(ast.unparse(level))+'<p>Доступно — измеримо в графе; частично — ограниченная интерпретация; обрезано выборкой — продолжение не видно; нельзя оценить — не ноль. На четвёртом колене вход и достижимость доступны, исходящее поведение обрезано, конечный получатель не определяется.</p>')
    add('queues','Очереди действий',f'<p>Сначала приоритет &lt; {observability.PRIORITY_THRESHOLD} → наблюдать. Иначе достаточность ≥ {observability.ACCEPTABLE_OBSERVABILITY} и сила роли ≥ {observability.EVIDENCE_THRESHOLD} → проверить сейчас. В остальных случаях → запросить данные.</p><p>«Наблюдать» не означает безопасен. «Запросить данные» не означает виновен. Разрывы данных определяют полезный следующий запрос.</p>')
    add('dependency','Зависимость наблюдаемых путей','<p>Если все направленные пути от исходных клиентов к другим узлам проходят через выбранный узел, эти узлы структурно зависят от него в текущем графе. Считаем зависимые узлы и число их кластеров; сам выбранный узел не входит в счёт.</p>'+code('super-source → все seed → NetworkX immediate_dominators')+'<p>Невидимый маршрут вне выгрузки может устранить зависимость. Это не доказательство контроля клиентов или денег.</p>','ДОПОЛНИТЕЛЬНЫЙ ПРИЗНАК')
    add('convergence','Схождение исходных узлов',code('effective_last_hop_branches = exp(−Σ qᵢ ln(qᵢ))')+'<p>Для каждого внешнего исходного узла единица веса делится поровну между достигаемыми последними входящими ветвями. Массы ветвей нормируются в qᵢ. Маршруты через сам целевой узел исключены, сам исходный узел не считается внешним. Без ветвей результат 0.</p><p>15 исходных узлов, сходящихся через одну последнюю ветвь, дают разнообразие 1. Достижимость и разнообразие ветвей — не число независимых путей. Используется как дополнительная диагностика схождения.</p>','ДОПОЛНИТЕЛЬНЫЙ ПРИЗНАК')
    stability=store.stability_summary
    summary=stability.get('summary',{})
    add('stability','Устойчивость результатов','<p>Проверяем совпадение роли, попадание в первые 20 и диапазон ранга. 10 изменений параметров включают сильную проверку без PageRank; это не только малые изменения. Три стресс-теста удаляют по 5% рёбер с фиксированными случайными последовательностями. Узлы сохраняются. Совпадение ≥90% означает устойчивость внутри выбранной группы сценариев; изоляты не оцениваем. Диапазон ранга показывается для исходного топ-100 или попадания в топ-20 любого сценария.</p>'+table(['Сценарии','Устойчивые','Чувствительные','Нельзя оценить','Среднее пересечение топ-20'],[(('Параметры' if k=='parameter' else 'Удаление связей'),v['role_status_counts'].get('STABLE',0),v['role_status_counts'].get('SENSITIVE',0),v['role_status_counts'].get('NOT_EVALUABLE',0),round(v['mean_top20_jaccard'],6)) for k,v in summary.items()])+'<p>Нет размеченных истинных ролей: это не точность, не доверительный интервал и не вероятность правильности. Диагностика не меняет основной рейтинг.</p>','ДИАГНОСТИКА')
    rows=[]
    for n in (1,3,5,10):
        r=resilience[n]; rows.append((n,r['after']['weak_components'],r['after']['largest_component'],r['after']['seed_reachable_nodes'],r['reachability_loss']['lost_surviving_nodes']))
    add('resilience','Устойчивость сети при изъятии узлов',table(['Удалить первых','Компоненты','Крупнейшая','Достижимые','Оставшиеся, потерявшие путь'],rows)+'<p>Удаляем первые N узлов исходного рейтинга в копии графа. Слабая компонента игнорирует направление; крупнейшая — её число узлов. Достижимость считается от оставшихся исходных узлов, включая их самих. Потерявшие путь оставшиеся учитываются отдельно от удалённых.</p><p>Контрфактическое изменение наблюдаемого графа, не прогноз реакции реальной сети.</p>','ДИАГНОСТИКА')
    add('temporal','Временные признаки','<p>Дневные входы и выходы сопоставляются максимальным потоком с лагом +1/+2 дня без повторного использования суммы. Делитель — входы с полностью наблюдаемыми двумя следующими днями; входы 30–31 июля исключены. Совместимость — допустимая верхняя граница, не отслеживание конкретных денег.</p><p>В тот же день порядок неизвестен: сумма минимумов входа и выхода показывается отдельно, не прибавляется к лаговому потоку. Сбор → распределение: ≥3 отправителей за день и ≥3 получателей за следующие два дня. Всплеск: ≥5 операций и ≥50% операций узла в один день. Для границы обхода исходящие интерпретации недоступны.</p>','ДИАГНОСТИКА')
    add('routes','Маршруты и возвратные потоки','<p>Повторная цепочка A → B → C требует трёх разных узлов и минимум двух согласованных пар дней с лагом +1/+2; дни одной стороны одной цепочки не переиспользуются. Взаимная пара — рёбра обоих направлений за месяц. Короткие циклы содержат 3–4 узла; повороты объединяются, обратное направление считается отдельно.</p>'+table(['Текущая сводка паттернов','Значение'],[({'nodes':'Узлы','repeated_chains':'Повторяющиеся цепочки','reciprocal_pairs':'Взаимные пары','short_cycles':'Короткие циклы','cycles_truncated':'Поиск циклов ограничен лимитом','cycle_expansions':'Проверенные расширения','nodes_with_gather_scatter':'Узлы со сбором и распределением','nodes_with_peer_flags':'Узлы с отклонениями','nodes_with_equal_amount_distribution':'Узлы с одинаковыми суммами'}.get(k,k),('Да' if v else 'Нет') if isinstance(v,bool) else str(v)) for k,v in store.patterns_summary.get('summary',{}).items()])+'<p>Поиск ограничен 10 000 циклами / 200 000 расширениями; при достижении лимита числа — нижние границы. В карточке до 10 примеров каждого типа, полные счётчики отдельно. Это структурные паттерны, не доказательство незаконной деятельности.</p>','ДИАГНОСТИКА')
    add('anomalies','Аномальные отклонения','<p>Сравниваем узлы одного колена: входящие и исходящие связи, входящий и общий оборот, число операций, максимальное дневное число отправителей и получателей. Средний процентиль включает все узлы группы; сигнал — положительное значение ≥99-го процентиля при группе ≥20 узлов. На границе обхода исходящие и зависящие от них показатели не оцениваем.</p><p>Распределение одинаковых сумм: точное совпадение суммы в тиынах в один день минимум трём разным получателям. Необычное относительно сопоставимых узлов не означает мошенничество.</p>','ДИАГНОСТИКА')
    add('ai','Роль ИИ',code('Вопрос → выбор инструмента → факты Python → гипотеза → альтернатива → ограничения → следующий шаг')+'<p>ИИ-помощник аналитика объясняет детерминированный расчёт, не рассчитывает роли, рейтинг и графовые метрики. Модель по умолчанию gpt-5.4-mini, может быть изменена OPENAI_MODEL. Инструменты:</p>'+code('\n'.join(t['name'] for t in TOOLS))+'<p>В OpenAI уходят вопрос, выбранные идентификаторы, инструкции и ограниченные результаты инструментов: профиль, признаки, до 30 соседей, сводка кластера; групповой поиск — до 5 исходных узлов и 20 кандидатов с путями. Весь parquet не передаётся. Паттерны не включены в инструменты ИИ. Без ключа вся основная аналитика и локальный архив реальных предыдущих ответов работают. Архив не является новым ответом для произвольного узла. Интерпретацию ИИ нужно сверять с источниками.</p>','ДОПОЛНИТЕЛЬНЫЙ ПРИЗНАК')
    add('limitations','Ограничения метода','<p>Один банк, один месяц, только операции от 5 000 ₸, только исходящий обход до четырёх колен. Нет полного входящего потока, внешних клиентских атрибутов и размеченных истинных ролей. Дата без времени суток. Пороги — экспертные эвристики. ИИ может ошибаться.</p><p><strong>Сообщество ≠ преступная группа. Роль ≠ виновность. Сила признаков ≠ вероятность.</strong></p>','ОГРАНИЧЕНИЕ')
    nav='<nav class="method-nav" aria-label="Разделы"><a href="/">Граф</a><a href="/methodology">Методика расчёта</a><a href="/ai-archive">Архив ИИ</a></nav>'
    return '<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Методика расчёта · MoneyGraph Investigator</title><link rel="stylesheet" href="/assets/style.css"><link rel="stylesheet" href="/assets/methodology.css"><script defer src="/assets/methodology.js"></script></head><body>'+nav+'<main class="methodology"><p class="eyebrow">МЕТОДИКА MONEYGRAPH INVESTIGATOR</p><h1>Методика расчёта</h1><p>Все роли и приоритеты являются объяснимыми гипотезами, рассчитанными по наблюдаемому графу. Сила признаков не является вероятностью виновности.</p>'+('<p class="notice">Выбранный узел: '+e(gid)+'</p>' if gid else '')+'<ol class="method-toc">'+''.join(f'<li><a href="#{a}">{t}</a></li>' for a,t,_ in sections)+'</ol>'+''.join(s for _,_,s in sections)+'</main></body></html>'
