"""Additive observed-graph evidence. No changes to roles, priority or queues."""
import networkx as nx


def dominator_evidence(graph, seeds, clusters):
    # Object sentinel cannot collide with a real gid. Edges are unweighted reachability.
    source = object()
    augmented = graph.copy()
    augmented.add_node(source)
    for seed in sorted(seeds):
        if seed not in graph:
            raise ValueError('Seed missing from graph')
        augmented.add_edge(source, seed)
    immediate = nx.immediate_dominators(augmented, source)
    tree = nx.DiGraph()
    tree.add_node(source)
    for node, parent in immediate.items():
        if node is not source:
            tree.add_edge(parent, node)
    sizes, cluster_sets, samples = {}, {}, {}
    for node in nx.dfs_postorder_nodes(tree, source):
        children = list(tree.successors(node))
        sizes[node] = 1 + sum(sizes[child] for child in children)
        cluster_sets[node] = {clusters[node]} if node is not source else set()
        sample = []
        for child in children:
            cluster_sets[node].update(cluster_sets[child])
            sample.extend([child] + samples[child])
        samples[node] = sorted(sample)[:12]
    result = {}
    for node in sorted(graph):
        if node not in immediate:
            result[str(node)] = {'status': 'NOT_EVALUABLE', 'dominated_nodes': None, 'dominated_clusters': None,
                'sample_dominated_gids': [], 'explanation': 'Узел недостижим от заданных seed: зависимость от seed-путей не оценивается.'}
            continue
        # Proper descendants exclude the node itself. No second subtraction of 1.
        descendants_count = sizes[node] - 1
        descendant_clusters = set()
        for child in tree.successors(node):
            descendant_clusters.update(cluster_sets[child])
        result[str(node)] = {'status': 'AVAILABLE', 'dominated_nodes': descendants_count,
            'dominated_clusters': len(descendant_clusters), 'sample_dominated_gids': [str(gid) for gid in samples[node]],
            'sample_is_truncated': descendants_count > len(samples[node]),
            'explanation': f'В наблюдаемом графе каждый путь от любого seed к {descendants_count} другим узлам проходит через этот узел. Сам узел не включён.',
            'limitation': 'Это зависимость наблюдаемой достижимости, не контроль денег или доказательство роли. Невидимые маршруты и граница обхода могут изменить результат.'}
    return result


def availability(r, dependency):
    rows = {}
    def put(key, status, value, reason):
        rows[key] = {'status': status, 'value': value, 'reason': reason}
    put('fan_in', 'PARTIAL' if r.is_seed or r.in_tx == 0 else 'AVAILABLE', int(r.in_degree),
        'Число наблюдаемых отправителей. Входящие вне выборки неизвестны; у seed upstream особенно неполон.')
    put('fan_out', 'CENSORED' if r.depth == 4 else ('PARTIAL' if r.out_tx == 0 else 'AVAILABLE'),
        None if r.depth == 4 else int(r.out_degree),
        'Depth=4: поведение на выходе нельзя оценить по обрезанному обходу.' if r.depth == 4 else
        'Число наблюдаемых получателей в пределах банка, периода и порога; отсутствие наблюдения не доказывает отсутствие операций.')
    put('transit', 'CENSORED' if r.depth == 4 else ('NOT_EVALUABLE' if r.is_seed or r.isolated else 'PARTIAL'),
        None if r.depth == 4 or r.is_seed or r.isolated or not r.in_tx or not r.out_tx else float(r.strength_transit),
        'Обрезанный выход.' if r.depth == 4 else 'Seed/изолят: правило transit не применяется.' if r.is_seed or r.isolated else
        'Сила месячных признаков transit, не трассировка денег. Временная согласованность не рассчитана; внешние входы неизвестны.')
    terminal_na = r.depth == 4 or r.is_seed or r.isolated
    put('terminal', 'NOT_EVALUABLE' if terminal_na else 'PARTIAL', None if terminal_na else float(r.strength_terminal),
        'Граница, seed или изолят исключены правилом terminal; N/A не равно нулевой вероятности.' if terminal_na else
        'Сила признаков повторного наблюдаемого приёма; без полной истории и остатков удержание не доказано.')
    put('seed_reach', 'AVAILABLE', int(r.reachable_seed_count),
        'Направленная достижимость в наблюдаемом графе, включая себя для seed. Не число независимых ветвей.')
    put('community', 'AVAILABLE', int(r.cluster_id),
        'ID вычисленного структурного кластера, не установленной группы. Изолят имеет одиночный кластер.')
    put('dominator', dependency['status'], dependency['dominated_nodes'],
        'Число других узлов, для которых этот узел обязателен на всех наблюдаемых путях от seed; невидимые маршруты не учитываются.')
    return rows


def build(graph, frame):
    dependency = dominator_evidence(graph, list(frame.index[frame.is_seed]), frame.cluster_id.to_dict())
    nodes = []
    for r in frame.sort_index().itertuples():
        detail = dependency[str(r.Index)]
        available = availability(r, detail)
        nodes.append({'gid': str(r.Index), 'structural_dependency': detail,
                      'evidence_availability': {name: info['status'] for name, info in available.items()},
                      'evidence_details': available})
    return {'schema_version': 1, 'scope': 'Additive evidence only; existing roles, scores, observability and queues unchanged.',
            'nodes': nodes}
