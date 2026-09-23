from pathlib import Path
import json
import pandas as pd
import pytest
from moneygraph.io import load_data, validate_outputs
from moneygraph.pipeline import DEFAULT_DATA, run
from moneygraph import features, roles, communities


def dataset(folder, node_rows, payments):
    """Small explicit transaction fixtures; no copied computed role outputs."""
    folder.mkdir(parents=True, exist_ok=True)
    n = pd.DataFrame(node_rows, columns=['gid', 'depth', 'is_seed'])
    t = pd.DataFrame(payments, columns=['src', 'dst', 'date', 'sum_kzt'])
    t['src'] = t.src.astype('int64'); t['dst'] = t.dst.astype('int64')
    t['sum_kzt'] = t.sum_kzt.astype(float); t['date'] = pd.to_datetime(t.date)
    e = t.groupby(['src', 'dst']).agg(sum_kzt=('sum_kzt', 'sum'), n_tx=('sum_kzt', 'size')).reset_index()
    e['depth'] = 1
    for name, frame in [('nodes', n), ('edges', e), ('transactions', t)]:
        frame.to_parquet(folder / f'{name}.parquet', index=False)
    return folder


def calculate(folder):
    n, e, t = load_data(folder)
    g, f = features.calculate(n, e, t)
    return g, roles.assign(f)


def test_real_data_contract_and_boundary(tmp_path):
    report = run(out=tmp_path)
    n = pd.read_csv(tmp_path / 'nodes_roles.csv')
    c = pd.read_csv(tmp_path / 'clusters.csv')
    top = pd.read_csv(tmp_path / 'top_nodes.csv')
    validate_outputs(n, c, top, pd.read_parquet(DEFAULT_DATA / 'nodes.parquet').gid)
    assert len(n) == 2248 and len(top) == 50
    assert report['isolated'] == 19
    assert report['weak_components_edge_graph'] == 16
    assert report['weak_components_all_nodes'] == 35
    assert not (n.boundary & n.role.eq('terminal')).any()
    assert n.loc[n.isolated, 'priority_score'].eq(0).all()
    assert n.loc[n.isolated, 'role'].eq('peripheral').all()
    assert report['duplicate_transaction_rows_retained'] == 97
    assert report['out_gt_in_audit']['all']['out_gt_in'] == 377
    assert report['out_gt_in_audit']['positive_in']['out_gt_in'] == 354
    assert report['out_gt_in_audit']['zero_in']['out_gt_in'] == 23
    assert report['sum_kzt'] == 365890012.01
    assert report['elapsed_seconds'] < 300


def test_reproducible_csvs_and_input_order(tmp_path):
    source = tmp_path / 'shuffled'; source.mkdir()
    for name in ['nodes', 'edges', 'transactions']:
        pd.read_parquet(DEFAULT_DATA / f'{name}.parquet').sample(frac=1, random_state=17).to_parquet(source / f'{name}.parquet', index=False)
    run(out=tmp_path / 'a'); run(data=source, out=tmp_path / 'b')
    for name in ['nodes_roles.csv', 'clusters.csv', 'top_nodes.csv']:
        assert (tmp_path / 'a' / name).read_bytes() == (tmp_path / 'b' / name).read_bytes()


def test_no_automatic_terminal_and_isolated_retained(tmp_path):
    data = dataset(tmp_path / 'data', [(0, 0, True), (1, 1, False), (2, 4, False), (3, 0, True)],
        [(0, 1, '2026-07-01', 5000), (0, 2, '2026-07-01', 5000),
         (0, 2, '2026-07-02', 5000), (0, 2, '2026-07-03', 5000)])
    g, f = calculate(data)
    assert 3 in g and f.loc[3, 'isolated']
    assert f.loc[1, 'role'] == 'peripheral'  # one receipt alone is not retention
    assert f.loc[2, 'role'] != 'terminal'  # repeated receipts cannot override depth=4


def test_repeated_internal_endpoint_is_terminal_hypothesis(tmp_path):
    data = dataset(tmp_path / 'data', [(0, 0, True), (1, 1, False)],
        [(0, 1, '2026-07-01', 5000), (0, 1, '2026-07-01', 5000), (0, 1, '2026-07-02', 5000)])
    _, f = calculate(data)
    assert f.loc[1, 'role'] == 'terminal'
    assert 'не доказано' in f.loc[1, 'evidence']
    assert f.loc[1, 'in_tx'] == 3  # identical rows are real observations, not auto-deduplicated


def test_ratio_cannot_assign_seed_transit(tmp_path):
    data = dataset(tmp_path / 'data', [(0, 0, True), (1, 1, False), (2, 2, False)],
        [(0, 1, '2026-07-01', 5000), (1, 2, '2026-07-02', 5000), (2, 0, '2026-07-03', 5000)])
    _, f = calculate(data)
    assert f.loc[0, 'observed_out_in_ratio'] == 1
    assert f.loc[0, 'role'] != 'transit'
    assert f.loc[1, 'role'] == 'transit'
    assert f.reachable_seed_count.eq(1).all()  # cycle does not create additional seed evidence


def test_distributor_and_data_changes_affect_rank(tmp_path):
    nodes = [(0, 0, True)] + [(i, 1, False) for i in range(1, 8)]
    first = dataset(tmp_path / 'first', nodes, [(0, 1, '2026-07-01', 5000)])
    second = dataset(tmp_path / 'second', nodes, [(0, i, '2026-07-01', 5000) for i in range(1, 8)])
    _, a = calculate(first); _, b = calculate(second)
    assert a.loc[0, 'role'] == 'peripheral' and b.loc[0, 'role'] == 'distributor'
    assert b.loc[0, 'priority_score'] > a.loc[0, 'priority_score']


def test_multiple_seeds_consolidate_without_independence_claim(tmp_path):
    nodes = [(i, 0, True) for i in range(4)] + [(10, 1, False)]
    data = dataset(tmp_path / 'data', nodes, [(i, 10, '2026-07-01', 5000) for i in range(4)])
    _, f = calculate(data)
    assert f.loc[10, 'role'] == 'consolidator'
    assert f.loc[10, 'reachable_seed_count'] == 4


def test_empty_edge_graph(tmp_path):
    data = dataset(tmp_path / 'data', [(0, 0, True), (1, 0, True)], [])
    report = run(data, tmp_path / 'output')
    assert report['nodes'] == 2 and report['clusters'] == 2
    assert report['weak_components_edge_graph'] == 0


@pytest.mark.parametrize('column,value', [('sum_kzt', 12345.67), ('n_tx', 4)])
def test_edge_aggregate_corruption_rejected(tmp_path, column, value):
    data = dataset(tmp_path / 'data', [(0, 0, True), (1, 1, False)], [(0, 1, '2026-07-01', 5000)])
    e = pd.read_parquet(data / 'edges.parquet'); e.loc[0, column] = value; e.to_parquet(data / 'edges.parquet')
    with pytest.raises(ValueError, match='sums or counts'):
        load_data(data)


def test_unknown_endpoint_rejected(tmp_path):
    data = dataset(tmp_path / 'data', [(0, 0, True)], [(0, 999, '2026-07-01', 5000)])
    with pytest.raises(ValueError, match='Unknown endpoint'):
        load_data(data)


def test_money_precision_rejected(tmp_path):
    data = dataset(tmp_path / 'data', [(0, 0, True), (1, 1, False)], [(0, 1, '2026-07-01', 5000.001)])
    with pytest.raises(ValueError, match='tiyn'):
        load_data(data)


def test_projection_sums_reciprocal_edges(tmp_path, monkeypatch):
    data = dataset(tmp_path / 'data', [(0, 0, True), (1, 1, False)],
        [(0, 1, '2026-07-01', 5000), (1, 0, '2026-07-02', 10000)])
    g, f = calculate(data)
    import networkx as nx
    original = nx.community.louvain_communities
    def capture(projection, **kwargs):
        assert projection[0][1]['weight'] == 1500000
        return original(projection, **kwargs)
    monkeypatch.setattr(nx.community, 'louvain_communities', capture)
    _, c = communities.assign(g, f)
    assert c.sum_kzt_internal.sum() == 15000


def test_coordinator_requires_observed_in_out_and_multiple_seeds(tmp_path):
    nodes = [(i, 0, True) for i in range(8)] + [(10, 1, False)] + [(i, 2, False) for i in range(20, 28)]
    payments = [(i, 10, '2026-07-01', 5000) for i in range(8)] + [(10, i, '2026-07-02', 10000) for i in range(20, 28)]
    data = dataset(tmp_path / 'data', nodes, payments)
    _, f = calculate(data)
    assert f.loc[10, 'role'] == 'coordinator'
    assert f.loc[10, 'reachable_seed_count'] == 8
    assert f.loc[10, 'in_degree'] == 8 and f.loc[10, 'out_degree'] == 8
