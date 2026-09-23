"""Bounded directed reachability of up to five explicit source IDs, not money tracing."""
from collections import deque


def find_candidates(nodes, edges, gids, max_hops=4, limit=20):
    if not isinstance(gids,list) or not 1<=len(gids)<=5 or any(not isinstance(g,str) or g not in nodes for g in gids):
        raise ValueError('Нужно от 1 до 5 существующих строковых GID')
    if type(max_hops) is not int or not 1<=max_hops<=4:raise ValueError('Глубина должна быть от 1 до 4')
    gids=list(dict.fromkeys(gids));sources=set(gids)
    adjacency={g:set() for g in nodes}
    for e in edges:adjacency[e['src']].add(e['dst'])
    paths={}
    for source in gids:
        found={source:[source]};pending=deque([source])
        while pending:
            node=pending.popleft()
            if len(found[node])-1>=max_hops:continue
            for neighbor in sorted(adjacency[node],key=int):
                if neighbor not in found:
                    found[neighbor]=found[node]+[neighbor];pending.append(neighbor)
        for target,path in found.items():
            if target not in sources:
                paths.setdefault(target,[]).append({'source_gid':source,'hops':len(path)-1,'one_observed_path':path})
    candidates=[]
    minimum=min(2,len(gids))
    for gid,reached in paths.items():
        if len(reached)<minimum:continue
        n=nodes[gid];distances=[p['hops'] for p in reached]
        candidates.append({'gid':gid,'source_count':len(reached),'source_total':len(gids),'reaches_all_sources':len(reached)==len(gids),
            'min_hops':min(distances),'max_hops':max(distances),'paths':reached,
            'baseline_role':n['primary_role'],'role_strength':n['primary_strength'],
            'alternative_role':n['alternative_role'],'alternative_strength':n['alternative_strength'],
            'priority_score':n['priority_score'],'depth':n['depth'],
            'observability_level':n['observability_level']})
    candidates.sort(key=lambda r:(-r['source_count'],r['max_hops'],-r['priority_score'],int(r['gid'])))
    return {'source_gids':gids,'source_total':len(gids),'hop_limit':max_hops,
        'common_to_all_count':sum(r['reaches_all_sources'] for r in candidates),
        'partial_candidate_count':sum(not r['reaches_all_sources'] for r in candidates),
        'total_candidates':len(candidates),'returned_candidates':len(candidates[:limit]),
        'truncated':len(candidates)>limit,'candidates':candidates[:limit],
        'selection':'At least two sources (one for a single-source query); input GIDs excluded as candidates. Sort: source coverage desc, max distance asc, existing priority desc, exact gid asc.',
        'limitation':'Наблюдаемая направленная достижимость за 1–4 перехода внутри выданной выборки. Не доказательство перечисления тех же денег, не временная трассировка и не доказательство роли сборщика. Часть 4/5 не является общим получателем всех 5. Граница depth=4, один банк/месяц и порог скрывают другие пути.'}
