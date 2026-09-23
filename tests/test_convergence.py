import hashlib
import json
import math
from pathlib import Path
import networkx as nx
import pandas as pd
import pytest
from moneygraph.convergence import calculate, build
from moneygraph.pipeline import run, ROOT


def value(edges, seeds, target, extra=()):
    g = nx.DiGraph(edges); g.add_nodes_from(seeds); g.add_nodes_from(extra)
    return calculate(g, seeds)[str(target)]


def test_single_seed_split_conserves_one_credit():
    v = value([(1,2),(1,3),(2,4),(3,4)], [1], 4)
    assert v['external_seed_count'] == 1
    assert v['effective_last_hop_branches'] == pytest.approx(2)
    assert sum(b['seed_credit_mass'] for b in v['branches']) == pytest.approx(1)


def test_upstream_merge_has_one_final_branch():
    v = value([(1,3),(2,3),(3,4)], [1,2], 4)
    assert v['external_seed_count'] == 2
    assert v['effective_last_hop_branches'] == 1


def test_balanced_branches_and_uneven_mass():
    balanced = value([(1,4),(2,4),(3,4)], [1,2,3], 4)
    assert balanced['effective_last_hop_branches'] == pytest.approx(3)
    edges = [(s,10) for s in range(1,10)] + [(10,20),(11,20)]
    uneven = value(edges, list(range(1,10))+[11], 20)
    assert uneven['effective_last_hop_branches'] == pytest.approx(math.exp(-.9*math.log(.9)-.1*math.log(.1)))


def test_cycles_do_not_create_return_branches_or_self_seed_credit():
    edges = [(1,2),(2,3),(3,2),(2,2)]
    v = value(edges, [1], 2)
    assert v['supported_predecessor_count'] == 1
    assert v['branches'][0]['predecessor_gid'] == '1'
    assert v['external_seed_count'] == 1
    assert value(edges, [2], 2)['effective_last_hop_branches'] == 0
    assert value(edges, [1,2], 2)['external_seed_count'] == 1


def test_cycle_before_target_retains_genuine_arrivals():
    v = value([(1,2),(2,3),(3,2),(2,4),(3,4)], [1], 4)
    assert v['external_seed_count'] == 1
    assert v['effective_last_hop_branches'] == pytest.approx(2)


def test_empty_unreachable_and_no_predecessors():
    for target in [1,7,9]:
        v = value([(8,9)], [1], target, extra=[7])
        assert v['effective_last_hop_branches'] == 0
        assert v['external_seed_count'] == 0 and v['branches'] == []


def test_exact_gid_order_determinism_nonmutation_and_depth_four():
    ids = [100000003115284100+i for i in range(4)]
    edges = [(ids[0],ids[2]),(ids[1],ids[2]),(ids[2],ids[3])]
    g = nx.DiGraph(edges)
    f = pd.DataFrame({'is_seed':[True,True,False,False], 'reachable_seed_count':[1,1,2,2], 'depth':[0,0,3,4]}, index=ids)
    original_edges = list(g.edges())
    before = f.copy(deep=True)
    a = build(g,f); b = build(nx.DiGraph(list(reversed(edges))),f.iloc[::-1])
    assert a == b
    pd.testing.assert_frame_equal(f,before)
    assert list(g.edges()) == original_edges
    assert a['nodes'][-1]['seed_convergence']['effective_last_hop_branches'] == 1
    assert a['nodes'][-1]['gid'] == str(ids[-1])
    assert a['nodes'][0]['seed_convergence']['reachable_seed_count'] == 1
    assert a['nodes'][0]['seed_convergence']['external_seed_count'] == 0
    assert isinstance(a['nodes'][-1]['seed_convergence']['branches'][0]['predecessor_gid'],str)


def test_phase4a_and_core_artifacts_frozen(tmp_path):
    frozen = json.loads((Path(__file__).parent/'phase4b_frozen_sha256.json').read_text())
    run(out=tmp_path)
    for name, digest in frozen.items():
        assert hashlib.sha256((tmp_path/name).read_bytes()).hexdigest() == digest
    rows = json.loads((tmp_path/'seed_convergence.json').read_text())['nodes']
    assert len(rows) == 2248
    for row in rows:
        v = row['seed_convergence']
        assert v['external_seed_count'] == v['reachable_seed_count'] - int(v['self_seed_excluded'])
        assert sum(b['seed_credit_mass'] for b in v['branches']) == pytest.approx(v['external_seed_count'])
        assert 0 <= v['effective_last_hop_branches'] <= v['supported_predecessor_count'] + 1e-10
