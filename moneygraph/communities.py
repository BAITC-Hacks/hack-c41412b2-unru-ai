"""Louvain on reciprocal-summed projection; IDs ordered by smallest member gid."""
import networkx as nx
import pandas as pd
from .io import CLUSTER_COLUMNS


def assign(graph, features):
    projection = nx.Graph()
    projection.add_nodes_from(sorted(graph.nodes))
    for a, b, attrs in sorted(graph.edges(data=True)):
        existing = projection.get_edge_data(a, b, {}).get('weight', 0)
        projection.add_edge(a, b, weight=existing + attrs['sum_tiyn'])
    groups = nx.community.louvain_communities(projection, weight='weight', resolution=1, seed=42) if projection.number_of_edges() else [{gid} for gid in projection]
    groups = sorted(groups, key=lambda group: min(group))
    membership = {gid: i for i, group in enumerate(groups) for gid in group}
    f = features.copy()
    f['cluster_id'] = pd.Series(membership).reindex(f.index).astype('int64')
    internal = {i: 0 for i in range(len(groups))}
    for a, b, attrs in graph.edges(data=True):
        if membership[a] == membership[b]:
            internal[membership[a]] += attrs['sum_tiyn']
    rows = []
    for i, group in enumerate(groups):
        members = f.loc[sorted(group)]
        top = members.sort_values(['priority_score', 'gid'], ascending=[False, True]).head(5)
        seeds = int(members.is_seed.sum())
        leading = members.role.value_counts().sort_index().sort_values(ascending=False, kind='stable').index[0]
        hypothesis = (f'Изолированный узел: связей в выгрузке нет; seed={seeds}.' if len(group) == 1 and members.isolated.all()
            else f'Структурное сообщество: {len(group)} узлов, seed={seeds}; чаще {leading}. Связанность не доказывает общую деятельность.')
        rows.append([i, len(group), seeds, internal[i] / 100, ';'.join(map(str, top.index)), hypothesis])
    return f, pd.DataFrame(rows, columns=CLUSTER_COLUMNS)
