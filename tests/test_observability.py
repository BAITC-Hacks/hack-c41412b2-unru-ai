import hashlib
import json
from pathlib import Path
import pandas as pd
import pytest
from moneygraph import features, roles, communities, observability
from moneygraph.io import load_data
from moneygraph.pipeline import DEFAULT_DATA, run


@pytest.fixture(scope='module')
def frame():
    n, e, t = load_data(DEFAULT_DATA)
    graph, f = features.calculate(n, e, t)
    f = roles.assign(f)
    f, _ = communities.assign(graph, f)
    return f


@pytest.fixture(scope='module')
def context(frame):
    return observability.build_context(frame)


def test_all_nodes_and_exact_string_identifiers(frame, context):
    assert len(context['nodes']) == len(frame)
    assert {n['gid'] for n in context['nodes']} == {str(gid) for gid in frame.index}
    assert all(isinstance(n['gid'], str) for n in context['nodes'])
    json.dumps(context, allow_nan=False)
    assert sum(context['summary']['queues'].values()) == len(frame)
    assert sum(context['summary']['observability'].values()) == len(frame)


def test_boundary_never_high_and_important_boundary_requests_data(frame, context):
    boundary = [n for n in context['nodes'] if n['metrics']['depth'] == 4]
    assert boundary and all(n['observability_level'] == 'LOW' for n in boundary)
    important = [n for n in boundary if n['priority_score'] >= .75]
    assert important, 'Real data must exercise this critical triage distinction'
    assert all(n['investigation_queue'] == 'REQUEST_MORE_DATA' for n in important)
    assert all('depth=4' in n['next_data_request'] for n in important)
    for n in important:
        assert n['priority_score'] == frame.loc[int(n['gid']), 'priority_score']


def test_observability_does_not_mutate_engine(frame):
    before = frame.copy(deep=True)
    c = observability.build_context(frame)
    pd.testing.assert_frame_equal(frame, before)
    for n in c['nodes']:
        row = frame.loc[int(n['gid'])]
        assert n['priority_score'] == row.priority_score
        assert n['primary_role'] == row.role
        assert n['primary_strength'] == row.role_score


def test_isolated_seed_explicit_data_gap(context):
    isolated = [n for n in context['nodes'] if n['isolated'] and n['is_seed']]
    assert len(isolated) == 19
    for n in isolated:
        assert n['observability_level'] == 'LOW'
        assert n['observability_score'] == .05
        assert 'ISOLATED' in {gap['code'] for gap in n['data_gaps']}
        assert n['next_data_request']
        assert n['investigation_queue'] == 'MONITOR'  # frozen priority=0, explicitly documented


def test_stable_under_row_permutation(frame, context):
    shuffled = observability.build_context(frame.sample(frac=1, random_state=12))
    assert shuffled == context


def test_alternatives_are_eligible_calculated_strengths(frame, context):
    count = 0
    for n in context['nodes']:
        row = frame.loc[int(n['gid'])]
        if n['alternative_role'] is None:
            assert n['alternative_strength'] == 0 and not n['role_alternatives']
            continue
        count += 1
        assert n['alternative_role'] != n['primary_role']
        assert n['alternative_strength'] > 0
        assert n['alternative_strength'] == row['strength_' + n['alternative_role']]
        assert n['primary_strength'] >= n['alternative_strength']
    assert count > 0


def test_queue_thresholds_and_evidence_gate(frame):
    base = next(frame.itertuples())._replace(depth=1, is_seed=False, isolated=False,
        in_tx=5, out_tx=5, in_days=3, out_days=3, in_tiyn=10000, out_tiyn=10000,
        role='coordinator', role_score=.8, priority_score=.75)
    assert observability.node_context(base)['investigation_queue'] == 'INVESTIGATE_NOW'
    assert observability.node_context(base._replace(priority_score=.7499))['investigation_queue'] == 'MONITOR'
    weak = observability.node_context(base._replace(role_score=.4999))
    assert weak['investigation_queue'] == 'REQUEST_MORE_DATA'
    assert 'пригодность 0.90 <0.60' not in weak['queue_reason']
    assert 'сила роли' in weak['queue_reason']
    assert observability.node_context(base._replace(depth=4))['investigation_queue'] == 'REQUEST_MORE_DATA'
    assert observability.node_context(base._replace(is_seed=True))['observability_level'] == 'MEDIUM'


def test_role_specific_days_and_missing_flows(frame):
    base = next(frame.itertuples())._replace(depth=1, is_seed=False, isolated=False,
        in_tx=5, out_tx=5, in_days=1, out_days=4, in_tiyn=10000, out_tiyn=10000,
        role='distributor', role_score=.8, priority_score=.8)
    assert observability.node_context(base)['observability_level'] == 'HIGH'
    assert observability.node_context(base._replace(role='coordinator'))['observability_level'] == 'MEDIUM'
    terminal = base._replace(role='terminal', out_tx=0, in_days=3, out_days=0, out_tiyn=0)
    assert observability.node_context(terminal)['observability_level'] == 'MEDIUM'
    assert observability.node_context(base._replace(in_tx=0, in_days=0, in_tiyn=0))['observability_level'] == 'LOW'


def test_three_csvs_frozen_and_json_matches_shuffled_raw_input(tmp_path):
    expected = json.loads(Path(__file__).with_name('phase1_csv_sha256.json').read_text())
    original = tmp_path / 'original'
    run(out=original)
    for name, sha in expected.items():
        assert hashlib.sha256((original / name).read_bytes()).hexdigest() == sha
    data = tmp_path / 'data'; data.mkdir()
    for name in ['nodes', 'edges', 'transactions']:
        pd.read_parquet(DEFAULT_DATA / f'{name}.parquet').sample(frac=1, random_state=3).to_parquet(data / f'{name}.parquet', index=False)
    run(data, tmp_path / 'shuffled')
    assert (original / 'node_context.json').read_bytes() == (tmp_path / 'shuffled/node_context.json').read_bytes()
