"""Validate raw files and output contracts. Monetary comparisons use integer tiyn."""
from pathlib import Path
import numpy as np
import pandas as pd

ROLES = {'consolidator', 'transit', 'distributor', 'terminal', 'coordinator', 'peripheral'}
NODE_COLUMNS = ['gid', 'role', 'role_score', 'cluster_id', 'priority_score', 'evidence']
CLUSTER_COLUMNS = ['cluster_id', 'n_nodes', 'n_seed', 'sum_kzt_internal', 'top_gids', 'hypothesis']
TOP_COLUMNS = ['rank', 'gid', 'role', 'priority_score', 'why']


def require(condition, message):
    if not bool(condition):
        raise ValueError(message)


def cents(series):
    values = pd.to_numeric(series, errors='raise').to_numpy(dtype=float)
    require(np.isfinite(values).all(), 'Money must be finite')
    require((values > 0).all(), 'Money must be positive')
    require((values < 9e15).all(), 'Money exceeds supported int64 tiyn range')
    scaled = values * 100
    require(np.isclose(scaled, np.rint(scaled), rtol=0, atol=1e-4).all(), 'Money has fractions below one tiyn')
    return np.rint(scaled).astype('int64')


def integer_column(frame, column, label):
    require(pd.api.types.is_integer_dtype(frame[column]), f'{label}.{column} must be integer')


def load_data(folder):
    folder = Path(folder)
    frames = {name: pd.read_parquet(folder / f'{name}.parquet') for name in ['nodes', 'edges', 'transactions']}
    schemas = {'nodes': ['gid', 'depth', 'is_seed'], 'edges': ['src', 'dst', 'sum_kzt', 'n_tx', 'depth'],
               'transactions': ['src', 'dst', 'date', 'sum_kzt']}
    for name, frame in frames.items():
        require(set(schemas[name]) <= set(frame.columns), f'Missing columns in {name}')
        require(not frame[schemas[name]].isna().any().any(), f'Null values in {name}')
    n, e, t = (frames[k].copy() for k in ['nodes', 'edges', 'transactions'])
    for col in ['gid', 'depth']:
        integer_column(n, col, 'nodes')
    require(pd.api.types.is_bool_dtype(n.is_seed), 'nodes.is_seed must be boolean')
    require(len(n) > 0 and n.gid.is_unique, 'nodes.gid must be nonempty and unique')
    require(n.depth.between(0, 4).all(), 'Node depth must be in 0..4 for this sampling protocol')
    require((n.is_seed == (n.depth == 0)).all(), 'Seed flag must match depth 0')
    ids = set(n.gid)
    for label, frame in [('edges', e), ('transactions', t)]:
        for col in ['src', 'dst']:
            integer_column(frame, col, label)
            require(set(frame[col]) <= ids, f'Unknown endpoint in {label}')
        require((frame.src != frame.dst).all(), f'Self-loop in {label}')
        frame['sum_tiyn'] = cents(frame.sum_kzt)
    for col in ['n_tx', 'depth']:
        integer_column(e, col, 'edges')
    require(e.n_tx.gt(0).all(), 'n_tx must be positive')
    require(e.depth.between(1, 4).all(), 'Edge depth must be in 1..4')
    require(not e.duplicated(['src', 'dst']).any(), 'Duplicate edge pair')
    t['date'] = pd.to_datetime(t.date, errors='raise')
    require(not t.date.isna().any(), 'Invalid dates')
    aggregated = t.groupby(['src', 'dst']).agg(sum_tiyn=('sum_tiyn', 'sum'), n_tx=('sum_tiyn', 'size')).sort_index()
    supplied = e.set_index(['src', 'dst'])[['sum_tiyn', 'n_tx']].sort_index()
    require(aggregated.index.equals(supplied.index), 'Transaction/edge pairs disagree')
    require((aggregated.to_numpy() == supplied.to_numpy()).all(), 'Transaction/edge sums or counts disagree')
    # Identical transaction rows intentionally survive: there is no transaction identifier.
    return n.sort_values('gid').reset_index(drop=True), e.sort_values(['src', 'dst']).reset_index(drop=True), t


def validate_outputs(nodes, clusters, top, input_gids):
    for label, frame, columns in [('nodes_roles', nodes, NODE_COLUMNS), ('clusters', clusters, CLUSTER_COLUMNS), ('top_nodes', top, TOP_COLUMNS)]:
        require(set(columns) <= set(frame.columns), f'Missing output columns: {label}')
        require(not frame[columns].isna().any().any(), f'Empty required output: {label}')
    require(nodes.gid.is_unique and set(nodes.gid) == set(input_gids), 'Output must contain every gid exactly once')
    require(set(nodes.role) <= ROLES, 'Unknown role')
    for col in ['role_score', 'priority_score']:
        require(nodes[col].between(0, 1).all(), f'{col} outside 0..1')
    require(nodes.evidence.str.len().between(1, 200).all(), 'Evidence must be 1..200 characters')
    require(clusters.cluster_id.is_unique, 'Duplicate cluster ID')
    require(set(nodes.cluster_id) == set(clusters.cluster_id), 'Cluster coverage mismatch')
    counts = nodes.groupby('cluster_id').size().sort_index()
    require(counts.equals(clusters.set_index('cluster_id').n_nodes.sort_index()), 'Cluster sizes mismatch')
    require(len(top) >= min(20, len(nodes)), 'Top requires at least 20 rows (or all nodes in smaller inputs)')
    require(top.gid.is_unique and set(top.gid) <= set(nodes.gid), 'Invalid top gids')
    require(top['rank'].tolist() == list(range(1, len(top) + 1)), 'Top ranks must be consecutive')
    expected = nodes.sort_values(['priority_score', 'gid'], ascending=[False, True]).head(len(top))
    require(top.gid.tolist() == expected.gid.tolist(), 'Top order does not match node priorities')
    require(np.array_equal(top.priority_score.to_numpy(), expected.priority_score.to_numpy()), 'Top scores disagree')
    require(top.role.tolist() == expected.role.tolist(), 'Top roles disagree')
    require(top.why.str.len().gt(0).all(), 'Empty top explanation')
