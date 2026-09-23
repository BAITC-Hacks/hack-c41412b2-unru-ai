"""Six transparent role hypotheses; scores are evidence strength, not probabilities."""
import pandas as pd

ROLE_ORDER = ['coordinator', 'distributor', 'consolidator', 'transit', 'terminal']


def classify_row(r):
    strengths = {role: 0.0 for role in ROLE_ORDER}
    if r.in_degree >= 3 and r.out_degree >= 3 and r.reachable_seed_count >= 2:
        strengths['coordinator'] = .4 * min(min(r.in_degree, r.out_degree) / 8, 1) + .35 * min(r.reachable_seed_count / 5, 1) + .25 * r.pagerank_percentile
    if r.out_degree >= 5:
        strengths['distributor'] = .55 * min(r.out_degree / 20, 1) + .25 * (1 - r.out_max_share) + .20 * r.out_percentile
    if r.in_degree >= 3 and r.out_degree <= max(2, r.in_degree / 2):
        strengths['consolidator'] = .50 * min(r.in_degree / 8, 1) + .30 * (1 - r.in_max_share) + .20 * r.in_percentile
    # Ratio is descriptive even for non-seed nodes: incomplete incoming flows remain possible.
    if not r.is_seed and r.in_tiyn > 0 and r.out_tiyn > 0 and .8 <= r.observed_out_in_ratio <= 1.2:
        agreement = max(0, 1 - abs(r.observed_out_in_ratio - 1) / .2)
        strengths['transit'] = .50 * agreement + .25 * min(min(r.in_tx, r.out_tx) / 5, 1) + .25 * min(min(r.in_degree, r.out_degree) / 3, 1)
    # A repeated observed endpoint, not proof of retention. Boundary and seeds are excluded.
    if not r.is_seed and r.depth < 4 and r.out_degree == 0 and 1 <= r.in_degree <= 2 and r.in_tx >= 3 and r.in_days >= 2:
        strengths['terminal'] = .40 * min(r.in_tx / 10, 1) + .35 * min(r.in_days / 5, 1) + .25 * r.in_percentile
    role = max(ROLE_ORDER, key=lambda name: strengths[name])
    score = strengths[role]
    if score == 0:
        role = 'peripheral'
    prefix = {
        'coordinator': f'Гипотеза связующего узла: вход {r.in_degree}, выход {r.out_degree}, достижим от {r.reachable_seed_count} seed.',
        'distributor': f'Веер: {r.out_degree} получателей, {r.out_tx} переводов, исходящие {r.out_kzt:.2f} KZT.',
        'consolidator': f'Консолидация: {r.in_degree} отправителей, {r.in_tx} переводов, вход {r.in_kzt:.2f} KZT; выход к {r.out_degree}.',
        'transit': f'Сходные наблюдаемые потоки: out/in={r.observed_out_in_ratio:.3f}; вход {r.in_kzt:.2f}, выход {r.out_kzt:.2f} KZT.',
        'terminal': f'Повторный приём: {r.in_tx} переводов за {r.in_days} дней, {r.in_degree} отправителей; выход 0. Удержание не доказано.',
        'peripheral': f'Пороги ролей не достигнуты: входящих связей {r.in_degree}, исходящих {r.out_degree}; переводов {r.in_tx + r.out_tx}.',
    }[role]
    if r.boundary:
        prefix += ' Граница depth=4: продолжение неизвестно.'
    elif r.is_seed:
        prefix += ' Seed: внешние входящие не видны.'
    return role, float(score), prefix, strengths


def assign(features):
    f = features.copy()
    records = [classify_row(row) for row in f.itertuples()]
    f['role'] = [r[0] for r in records]
    f['role_score'] = [r[1] for r in records]
    f['evidence'] = [r[2] for r in records]
    strengths = pd.DataFrame([r[3] for r in records], index=f.index).add_prefix('strength_')
    f = pd.concat([f, strengths], axis=1)
    f['priority_score'] = (.30 * f.volume_percentile + .25 * f.neighbors_percentile +
        .20 * (f.reachable_seed_count / 5).clip(upper=1) + .15 * f.role_score + .10 * f.pagerank_percentile)
    # A seed with no observed links is a data gap, not fabricated transaction evidence.
    f.loc[f.isolated, 'priority_score'] = 0.0
    f['priority_why'] = [
        f'Оборот вход+выход {r.in_kzt + r.out_kzt:.2f} KZT; соседей {r.neighbor_count}; достижим от {r.reachable_seed_count} seed; сила роли {r.role_score:.3f}. '
        + ('Граница обхода: запросить продолжение.' if r.boundary else 'Приоритет проверки, не вероятность нарушения.')
        for r in f.itertuples()
    ]
    return f
