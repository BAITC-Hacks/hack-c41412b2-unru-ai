"""Structural counterfactual on copies of the baseline graph; not network behavior prediction."""
import time
import networkx as nx

SIZES = (0,1,3,5,10)


def observed_reach(graph, seeds):
    seen=set(seeds)&set(graph)
    pending=list(seen)
    while pending:
        node=pending.pop()
        for neighbor in graph.successors(node):
            if neighbor not in seen:
                seen.add(neighbor);pending.append(neighbor)
    return seen


def metrics(graph, seeds):
    remaining_seeds=set(seeds)&set(graph)
    components=list(nx.weakly_connected_components(graph))
    return {'nodes':len(graph),'edges':graph.number_of_edges(),
            'weak_components':len(components),'largest_component':max(map(len,components),default=0),
            'isolated_nodes':sum(graph.degree(n)==0 for n in graph),
            'seed_reachable_nodes':len(observed_reach(graph,remaining_seeds)),
            'remaining_seeds':len(remaining_seeds),
            'multi_seed_components':sum(len(c&remaining_seeds)>1 for c in components)}


def simulate(graph, seeds, ranked_gids, n):
    if n not in SIZES: raise ValueError('Supported N: 0, 1, 3, 5, 10')
    if len(set(ranked_gids))!=len(ranked_gids) or set(ranked_gids)!=set(graph):
        raise ValueError('Ranking must cover each baseline node exactly once')
    if not set(seeds)<=set(graph):raise ValueError('Seed outside graph')
    start=time.perf_counter()
    removed=list(ranked_gids[:n]);removed_set=set(removed)
    after=graph.copy();after.remove_nodes_from(removed)
    before_metrics=metrics(graph,seeds);after_metrics=metrics(after,seeds)
    baseline_reach=observed_reach(graph,seeds);after_reach=observed_reach(after,set(seeds)-removed_set)
    surviving_baseline=baseline_reach-removed_set
    lost_surviving=surviving_baseline-after_reach
    new_fragments=0;vanished_components=0
    # Removing an entire original component is not counted as negative fragmentation.
    for component in nx.weakly_connected_components(graph):
        survivors=component-removed_set
        pieces=nx.number_weakly_connected_components(after.subgraph(survivors)) if survivors else 0
        new_fragments+=max(pieces-1,0)
        vanished_components+=int(not pieces)
    total_loss=len(baseline_reach)-len(after_reach)
    return {'n_requested':n,'removed_count':len(removed),'removed_gids':[str(g) for g in removed],
            'removed_seed_gids':[str(g) for g in removed if g in seeds],
            'before':before_metrics,'after':after_metrics,
            'component_count_delta':after_metrics['weak_components']-before_metrics['weak_components'],
            'new_fragments':new_fragments,'fully_removed_components':vanished_components,
            'reachability_loss':{'total_nodes':total_loss,
                'total_fraction':total_loss/len(baseline_reach) if baseline_reach else None,
                'removed_previously_reachable':len(baseline_reach&removed_set),
                'lost_surviving_nodes':len(lost_surviving),
                'surviving_baseline_reachable':len(surviving_baseline),
                'surviving_fraction':len(lost_surviving)/len(surviving_baseline) if surviving_baseline else None},
            'runtime_seconds':round(time.perf_counter()-start,6),
            'scope':'Структура наблюдаемого графа после гипотетического удаления узлов. Не прогноз реальной реакции сети.',
            'reach_definition':'Направленная достижимость от любого оставшегося seed, включая сам seed. Общая потеря включает удалённые узлы; потеря среди оставшихся показана отдельно.'}


def build(store):
    start=time.perf_counter()
    graph=nx.DiGraph();graph.add_nodes_from(store.nodes)
    graph.add_edges_from((e['src'],e['dst']) for e in store.edges)
    seeds={gid for gid,node in store.nodes.items() if node['is_seed']}
    ranking=sorted(store.nodes,key=lambda gid:(-store.nodes[gid]['priority_score'],int(gid)))
    results={n:simulate(graph,seeds,ranking,n) for n in SIZES}
    for result in results.values():
        result['removed_nodes']=[{'gid':gid,'is_seed':gid in seeds,'priority_score':store.nodes[gid]['priority_score']} for gid in result['removed_gids']]
    return results,round(time.perf_counter()-start,6)
