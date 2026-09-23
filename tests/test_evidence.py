import json
from pathlib import Path
import networkx as nx
import pandas as pd
import pytest
from moneygraph.evidence import dominator_evidence, build
from moneygraph import communities, features, roles
from moneygraph.io import load_data
from moneygraph.pipeline import DEFAULT_DATA, run, ROOT


def calculate(edges, seeds, extra=()):
    g=nx.DiGraph(edges);g.add_nodes_from(seeds);g.add_nodes_from(extra)
    return dominator_evidence(g,seeds,{n:n%2 for n in g})


def test_chain_excludes_self_without_double_subtraction():
    d=calculate([(1,2),(2,3),(3,4)],[1])
    assert [d[str(i)]['dominated_nodes'] for i in range(1,5)]==[3,2,1,0]
    assert d['2']['dominated_clusters']==2
    assert d['4']['sample_dominated_gids']==[]


def test_diamond_bypass_and_second_seed():
    d=calculate([(1,2),(1,3),(2,4),(3,4),(4,5)],[1])
    assert d['2']['dominated_nodes']==0 and d['3']['dominated_nodes']==0
    assert d['4']['dominated_nodes']==1
    d=calculate([(1,2),(2,3),(3,4)],[1,3])
    assert d['1']['dominated_nodes']==1
    assert d['2']['dominated_nodes']==0
    assert d['3']['dominated_nodes']==1


def test_cycles_unreachable_and_isolated_seed():
    d=calculate([(1,2),(2,3),(3,2),(3,4),(8,9)],[1,7],extra=[10])
    assert d['2']['dominated_nodes']==2
    assert d['7']['dominated_nodes']==0
    for gid in ['8','9','10']:
        assert d[gid]['status']=='NOT_EVALUABLE' and d[gid]['dominated_nodes'] is None


def test_no_seed_does_not_invent_zero():
    d=calculate([(1,2)],[])
    assert all(r['dominated_nodes'] is None for r in d.values())


def test_cluster_count_excludes_subject_only_cluster():
    g=nx.DiGraph([(1,2),(2,3)])
    d=dominator_evidence(g,[1],{1:100,2:200,3:200})
    assert d['1']['dominated_clusters']==1


@pytest.fixture(scope='module')
def actual():
    n,e,t=load_data(DEFAULT_DATA);g,f=features.calculate(n,e,t);f=roles.assign(f);f,_=communities.assign(g,f)
    return g,f,build(g,f)


def test_real_counts_against_node_removal(actual):
    g,f,result=actual
    seeds=set(f.index[f.is_seed]);root=object();baseline=g.copy();baseline.add_node(root)
    baseline.add_edges_from((root,s) for s in seeds)
    reached=nx.descendants(baseline,root)
    candidates=sorted(result['nodes'],key=lambda n:-(n['structural_dependency']['dominated_nodes'] or 0))[:5]
    for n in candidates:
        gid=int(n['gid']); modified=baseline.copy();modified.remove_node(gid)
        lost=reached-nx.descendants(modified,root)-{gid}
        assert len(lost)==n['structural_dependency']['dominated_nodes']
        assert len({f.loc[v,'cluster_id'] for v in lost})==n['structural_dependency']['dominated_clusters']
        assert set(map(int,n['structural_dependency']['sample_dominated_gids']))<=lost


def test_boundary_mask_keeps_incoming_and_seed_reach(actual):
    g,f,result=actual
    for n in result['nodes']:
        r=f.loc[int(n['gid'])]
        if r.depth!=4: continue
        assert n['evidence_availability']['fan_out']=='CENSORED'
        assert n['evidence_availability']['terminal']=='NOT_EVALUABLE'
        assert n['evidence_details']['fan_out']['value'] is None
        assert n['evidence_details']['terminal']['value'] is None
        assert n['evidence_details']['seed_reach']['value']==r.reachable_seed_count
        assert n['evidence_details']['fan_in']['value']==r.in_degree


def test_stable_nonmutating_and_string_ids(actual):
    g,f,result=actual;previous=f.copy(deep=True)
    assert build(g,f.sample(frac=1,random_state=4))==result
    pd.testing.assert_frame_equal(f,previous)
    assert len(result['nodes'])==2248
    assert all(isinstance(n['gid'],str) for n in result['nodes'])
    json.dumps(result,allow_nan=False)


def test_additive_output_preserves_phase2_context(tmp_path):
    run(out=tmp_path)
    assert (tmp_path/'node_context.json').read_bytes()==(ROOT/'outputs/node_context.json').read_bytes()
    assert (tmp_path/'structural_evidence.json').is_file()
