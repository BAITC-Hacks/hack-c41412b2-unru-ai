"""Directed graph metrics. Observed flows are never account balances."""
import networkx as nx
import pandas as pd


def positive_percentile(series):
    result = pd.Series(0.0, index=series.index)
    positive = series > 0
    result.loc[positive] = series.loc[positive].rank(method='average', pct=True)
    return result


def calculate(nodes, edges, transactions):
    graph = nx.DiGraph()
    graph.add_nodes_from(int(gid) for gid in nodes.gid)
    for e in edges.itertuples(index=False):
        graph.add_edge(int(e.src), int(e.dst), sum_tiyn=int(e.sum_tiyn), n_tx=int(e.n_tx))
    f = nodes.set_index('gid').copy()
    f['in_degree'] = pd.Series(dict(graph.in_degree())).reindex(f.index)
    f['out_degree'] = pd.Series(dict(graph.out_degree())).reindex(f.index)
    for direction, endpoint in [('in', 'dst'), ('out', 'src')]:
        groups = edges.groupby(endpoint)
        f[f'{direction}_tiyn'] = groups.sum_tiyn.sum().reindex(f.index, fill_value=0).astype('int64')
        f[f'{direction}_kzt'] = f[f'{direction}_tiyn'] / 100
        f[f'{direction}_tx'] = groups.n_tx.sum().reindex(f.index, fill_value=0).astype('int64')
        max_edge = groups.sum_tiyn.max().reindex(f.index, fill_value=0)
        f[f'{direction}_max_share'] = (max_edge / f[f'{direction}_tiyn'].replace(0, float('nan'))).fillna(0)
        tx = transactions.assign(day=transactions.date.dt.normalize())
        f[f'{direction}_days'] = tx.groupby(endpoint).day.nunique().reindex(f.index, fill_value=0).astype('int64')
    f['neighbor_count'] = [len(set(graph.predecessors(gid)) | set(graph.successors(gid))) for gid in f.index]
    f['pagerank'] = pd.Series(nx.pagerank(graph, weight='sum_tiyn', tol=1e-10, max_iter=1000)).reindex(f.index)
    f['reachable_seed_count'] = 0
    for seed in f.index[f.is_seed]:
        reached = nx.descendants(graph, int(seed)) | {int(seed)}
        f.loc[sorted(reached), 'reachable_seed_count'] += 1
    f['boundary'] = f.depth.eq(4) & f.out_degree.eq(0)
    f['isolated'] = f.neighbor_count.eq(0)
    f['observed_out_gt_in'] = f.out_tiyn > f.in_tiyn
    f['observed_out_in_ratio'] = f.out_tiyn / f.in_tiyn.replace(0, float('nan'))
    f['volume_percentile'] = positive_percentile(f.in_tiyn + f.out_tiyn)
    f['in_percentile'] = positive_percentile(f.in_tiyn)
    f['out_percentile'] = positive_percentile(f.out_tiyn)
    f['neighbors_percentile'] = positive_percentile(f.neighbor_count)
    # Isolated nodes have PageRank through teleportation, not transaction evidence.
    f['pagerank_percentile'] = positive_percentile(f.pagerank.where(~f.isolated, 0))
    return graph, f
