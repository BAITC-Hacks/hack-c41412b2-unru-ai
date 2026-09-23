"""Separate interpretation limits and triage; never mutate analytical scores."""
from collections import Counter
from .roles import ROLE_ORDER

PRIORITY_THRESHOLD = 0.75
EVIDENCE_THRESHOLD = 0.50
ACCEPTABLE_OBSERVABILITY = 0.60
LEVELS = ('HIGH', 'MEDIUM', 'LOW')
QUEUES = ('INVESTIGATE_NOW', 'REQUEST_MORE_DATA', 'MONITOR')


def node_context(r):
    score = 0.90
    reasons, gaps, requests, caps = [], [], [], []

    def limit(code, ceiling, reason, gap, request):
        nonlocal score
        score = min(score, ceiling)
        reasons.append(reason)
        gaps.append({'code': code, 'description': gap})
        requests.append(request)
        caps.append({'code': code, 'ceiling': ceiling})

    # Order also defines which useful request is displayed first; not a learned utility.
    if r.depth == 4:
        limit('BOUNDARY_DEPTH_4', .15,
              'Depth=4: исходящий обход заканчивается на этом колене.',
              'Продолжение переводов за границей обхода не представлено.',
              'Продолжить исходящий обход от этого gid за depth=4 за тот же период и с тем же порогом; указать полноту новой выгрузки.')
    if r.isolated:
        limit('ISOLATED', .05,
              'В узле нет наблюдаемых рёбер; роль по транзакциям интерпретировать нельзя.',
              'В выборке нет ни входящих, ни исходящих переводов этого узла.',
              'Запросить входящие и исходящие переводы этого gid за июль и проверить причину отсутствия рёбер в исходной выгрузке.')
    if r.is_seed:
        limit('SEED_UPSTREAM', .55,
              'Seed: обход начат с узла, входящие вне выборки не представлены.',
              'Upstream-потоки вне текущего обхода неизвестны; баланс не восстановлен.',
              'Запросить входящие переводы этого seed из-за пределов текущего обхода; для анализа баланса отдельно нужны остатки и полный охват операций.')
    if r.in_tx == 0:
        limit('NO_OBSERVED_INCOMING', .35,
              'Наблюдаемых входящих переводов нет: входящая сторона потока не представлена.',
              'Отсутствие входящих в выборке не означает отсутствие входящих у клиента.',
              'Запросить входящие переводы этого gid за тот же период с указанием охвата, включая отправителей вне текущего графа.')
    if r.out_tx == 0:
        ceiling = .55 if r.role == 'terminal' else .35
        limit('NO_OBSERVED_OUTGOING', ceiling,
              'Исходящие не наблюдаются; удержание денег не подтверждено.' if r.role == 'terminal'
              else 'Наблюдаемых исходящих переводов нет: продолжение потока неизвестно.',
              'Нельзя отличить фактическое отсутствие выхода от ограничений выгрузки.',
              'Проверить полноту исходящих операций этого gid за тот же период; для гипотезы удержания запросить остатки на начало и конец периода.')
    if r.depth == 3:
        limit('NEAR_BOUNDARY', .65,
              'Depth=3: следующее колено является границей наблюдения.',
              'Дальнейшая судьба потоков за следующим коленом неизвестна.',
              'Расширить исходящий обход получателей этого gid за четвёртое колено для проверки дальнейшего маршрута.')
    if r.in_tx + r.out_tx < 3:
        limit('FEW_TRANSACTIONS', .35,
              f'Всего {r.in_tx + r.out_tx} наблюдаемых переводов: мало повторений для интерпретации роли.',
              'Недостаточно повторных наблюдений в текущем месяце.',
              'Запросить переводы за соседний период с теми же условиями отбора, чтобы проверить повторяемость структуры.')
    # Require days on the side relevant to the role, not the sum of possibly overlapping day counts.
    if r.role in ('transit', 'coordinator'):
        supported_days = min(r.in_days, r.out_days)
    elif r.role in ('consolidator', 'terminal'):
        supported_days = r.in_days
    elif r.role == 'distributor':
        supported_days = r.out_days
    else:
        supported_days = max(r.in_days, r.out_days)
    if supported_days < 2:
        limit('FEW_ROLE_DAYS', .55,
              f'Поддержка гипотезы по дням: {supported_days}; требуется хотя бы 2 дня для повторяемости.',
              'Признаки соответствующей стороны потока наблюдаются менее чем в двух днях.',
              'Запросить соседний период и проверить, повторяется ли наблюдаемая структура связей.')
    if not r.is_seed and r.out_tiyn - r.in_tiyn > 1:
        limit('OUT_EXCEEDS_OBSERVED_IN', .55,
              'Исходящая сумма больше наблюдаемой входящей более чем на 1 тиын; источник разницы не установлен.',
              'Разница может зависеть от начального остатка или входящих вне выборки; причина по графу не устанавливается.',
              'Запросить входящие за пределами обхода и начальный остаток за период, чтобы проверить источник наблюдаемой разницы.')
    if r.role == 'transit':
        limit('TRANSIT_NO_TRACING', .65,
              'Transit основан на сходстве месячных сумм; временная связь входа и выхода не проверена.',
              'Даты без внутридневного времени не доказывают сквозной перенос конкретных денег.',
              'Запросить точное время операций для проверки последовательности входа и выхода; совпадение сумм само по себе недостаточно.')
    if not reasons:
        reasons.append('Внутренний не-seed узел: видны обе стороны потока, ≥3 перевода и ≥2 дня на нужной для роли стороне.')
    gaps.append({'code': 'GLOBAL_SAMPLING', 'description':
        'Общий охват ограничен одним банком, июлем 2026, платежами от 5000 KZT и исходящим обходом. Полнота истории клиента неизвестна.'})
    level = 'HIGH' if score >= .75 else 'MEDIUM' if score >= .45 else 'LOW'
    if r.priority_score < PRIORITY_THRESHOLD:
        queue = 'MONITOR'
        queue_reason = f'Приоритет {r.priority_score:.3f} ниже порога {PRIORITY_THRESHOLD:.2f}; это не отсутствие риска.'
    elif score >= ACCEPTABLE_OBSERVABILITY and r.role_score >= EVIDENCE_THRESHOLD:
        queue = 'INVESTIGATE_NOW'
        queue_reason = 'Приоритет ≥0.75, сила роли ≥0.50, пригодность наблюдений ≥0.60: можно начать проверку имеющихся фактов.'
    else:
        queue = 'REQUEST_MORE_DATA'
        blockers = []
        if score < ACCEPTABLE_OBSERVABILITY:
            blockers.append(f'пригодность {score:.2f} <0.60')
        if r.role_score < EVIDENCE_THRESHOLD:
            blockers.append(f'сила роли {r.role_score:.3f} <0.50')
        queue_reason = 'Приоритет ≥0.75, но ' + '; '.join(blockers) + '; приоритет сохранён.'
    alternatives = [(name, float(getattr(r, f'strength_{name}'))) for name in ROLE_ORDER
                    if name != r.role and getattr(r, f'strength_{name}') > 0]
    alternatives.sort(key=lambda pair: (-pair[1], ROLE_ORDER.index(pair[0])))
    return {
        'gid': str(r.Index),  # Never serialize these ~10^17 identifiers as JavaScript numbers.
        'priority_score': float(r.priority_score),
        'primary_role': r.role, 'primary_strength': float(r.role_score),
        'alternative_role': alternatives[0][0] if alternatives else None,
        'alternative_strength': alternatives[0][1] if alternatives else 0.0,
        'role_alternatives': [{'role': name, 'strength': strength} for name, strength in alternatives],
        'observability_score': score, 'observability_level': level,
        'observability_reasons': reasons, 'observability_caps': caps,
        'investigation_queue': queue, 'queue_reason': queue_reason,
        'data_gaps': gaps,
        'next_data_request': requests[0] if requests else
            'Для проверки устойчивости гипотезы запросить соседний период с теми же условиями отбора; текущий месяц не описывает всю историю клиента.',
        'possible_data_requests': list(dict.fromkeys(requests)),
        'evidence': r.evidence,
        'metrics': {name: int(getattr(r, name)) for name in
                    ('depth', 'in_degree', 'out_degree', 'in_tx', 'out_tx', 'in_days', 'out_days', 'reachable_seed_count', 'cluster_id')},
        'is_seed': bool(r.is_seed), 'isolated': bool(r.isolated),
    }


def build_context(frame):
    nodes = [node_context(row) for row in frame.sort_index().itertuples()]
    observations = Counter(n['observability_level'] for n in nodes)
    queues = Counter(n['investigation_queue'] for n in nodes)
    return {
        'schema_version': 1,
        'interpretation': 'Relative suitability for interpreting the current role hypothesis, not percent of bank data or a probability. Priority is unchanged.',
        'thresholds': {'high_priority': PRIORITY_THRESHOLD, 'sufficient_role_strength': EVIDENCE_THRESHOLD,
                       'acceptable_observability': ACCEPTABLE_OBSERVABILITY},
        'summary': {'observability': {level: observations[level] for level in LEVELS},
                    'queues': {queue: queues[queue] for queue in QUEUES}},
        'nodes': nodes,
    }
