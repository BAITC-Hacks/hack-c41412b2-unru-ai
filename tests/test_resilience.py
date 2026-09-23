import copy
import hashlib
import json
from types import SimpleNamespace
import networkx as nx
import pytest
from fastapi.testclient import TestClient
from moneygraph.resilience import simulate,build,metrics
from moneygraph.server import create_app
from moneygraph.pipeline import ROOT


def test_chain_removal_separates_removed_and_lost_survivors():
    graph=nx.DiGraph([('1','2'),('2','3'),('3','4')]);before=graph.copy()
    r=simulate(graph,{'1'},['2','1','3','4'],1)
    assert nx.utils.graphs_equal(graph,before)
    assert r['before']['seed_reachable_nodes']==4
    assert r['after']['seed_reachable_nodes']==1
    assert r['after']['weak_components']==2 and r['new_fragments']==1
    assert r['reachability_loss']=={'total_nodes':3,'total_fraction':.75,'removed_previously_reachable':1,'lost_surviving_nodes':2,'surviving_baseline_reachable':3,'surviving_fraction':2/3}


def test_star_seed_removal_and_empty_graph():
    graph=nx.DiGraph([('1','2'),('1','3'),('1','4')])
    r=simulate(graph,{'1'},['1','2','3','4'],1)
    assert r['removed_seed_gids']==['1']
    assert r['after']['remaining_seeds']==0 and r['after']['seed_reachable_nodes']==0
    assert r['after']['weak_components']==3 and r['after']['isolated_nodes']==3
    assert r['new_fragments']==2 and r['reachability_loss']['surviving_fraction']==1
    empty=simulate(graph,{'1'},['1','2','3','4'],5)
    assert empty['removed_count']==4 and empty['after']['largest_component']==0
    assert empty['fully_removed_components']==1 and empty['new_fragments']==0
    assert empty['reachability_loss']['surviving_fraction'] is None


def test_disconnected_components_and_remaining_seed_paths():
    graph=nx.DiGraph([('1','2'),('2','3'),('4','3')]);graph.add_node('5')
    r=simulate(graph,{'1','4','5'},['1','5','2','3','4'],3)
    assert r['before']['weak_components']==2 and r['after']['weak_components']==1
    assert r['fully_removed_components']==1 and r['component_count_delta']==-1
    assert r['after']['seed_reachable_nodes']==2
    assert r['reachability_loss']['lost_surviving_nodes']==0
    assert r['new_fragments']==0


def test_unreachable_baseline_and_reset():
    graph=nx.DiGraph([('1','2')])
    result=simulate(graph,set(),['1','2'],1)
    assert result['reachability_loss']['total_fraction'] is None
    reset=simulate(graph,set(),['1','2'],0)
    assert reset['before']==reset['after'] and reset['removed_gids']==[]
    assert reset['reachability_loss']['total_nodes']==0
    with pytest.raises(ValueError):simulate(graph,set(),['1','2'],2)
    with pytest.raises(ValueError):simulate(graph,set(),['1','1'],1)


def test_exact_string_gid_tie_order():
    ids=['100000003115284101','100000003115284100']
    store=SimpleNamespace(nodes={g:{'priority_score':.5,'is_seed':False} for g in ids},edges=[])
    r,_=build(store)
    assert r[1]['removed_gids']==[ids[1]]
    store.nodes=dict(reversed(list(store.nodes.items())))
    again,_=build(store)
    for key in r:
        r[key].pop('runtime_seconds');again[key].pop('runtime_seconds')
    assert r==again


@pytest.fixture(scope='module')
def app():return create_app()


def test_real_top_selection_and_immutable_store(app):
    before=copy.deepcopy(app.state.store.nodes);edges=copy.deepcopy(app.state.store.edges)
    baseline=json.loads((ROOT/'outputs/node_context.json').read_text())['nodes']
    expected=sorted(baseline,key=lambda n:(-n['priority_score'],int(n['gid'])))
    scenarios,_=build(app.state.store)
    for n,r in scenarios.items():
        assert r['removed_gids']==[x['gid'] for x in expected[:n]]
        assert all(isinstance(g,str) for g in r['removed_gids'])
        assert r['component_count_delta']==r['new_fragments']-r['fully_removed_components']
        loss=r['reachability_loss']
        assert loss['total_nodes']==loss['removed_previously_reachable']+loss['lost_surviving_nodes']
        assert r['after']['seed_reachable_nodes']<=r['before']['seed_reachable_nodes']-loss['removed_previously_reachable']
    assert app.state.store.nodes==before and app.state.store.edges==edges


def test_api_reset_and_frozen_artifacts(app):
    paths=list((ROOT/'outputs').glob('*.csv'))+[ROOT/'outputs'/f for f in ['node_context.json','structural_evidence.json','seed_convergence.json','stability.json']]+[ROOT/'audit/phase5_live_verification.json',ROOT/'moneygraph/analyst.py']
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    client=TestClient(app)
    initial=client.get('/api/resilience?n=0').json()
    for n in [1,3,5,10]:
        result=client.get('/api/resilience',params={'n':n}).json()
        assert result['removed_count']==n
    assert client.get('/api/resilience?n=0').json()==initial
    assert client.get('/api/resilience?n=999').status_code==422
    assert client.get('/api/resilience?n=oops').status_code==422
    assert client.get('/api/summary').json()['total_nodes']==2248
    assert {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}==before
