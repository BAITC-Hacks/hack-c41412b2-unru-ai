import hashlib
import json
from pathlib import Path
import random
import pytest
from fastapi.testclient import TestClient
from moneygraph.server import create_app, DOWNLOADS
from moneygraph.pipeline import ROOT


@pytest.fixture(scope='module')
def app():
    return create_app()


@pytest.fixture(scope='module')
def client(app):
    return TestClient(app)


def test_summary_and_queue_pagination(client, app):
    s=client.get('/api/summary').json()
    assert s['total_nodes']==2248 and s['total_edges']==3119 and s['n_clusters']==91
    for queue,nodes in app.state.store.queue_lists.items():
        a=client.get(f'/api/queues/{queue}?limit=10').json()
        b=client.get(f'/api/queues/{queue}?limit=10&offset=10').json()
        assert a['total']==len(nodes)==s['queue_counts'][queue]
        assert [r['gid'] for r in a['items']]==[r['gid'] for r in nodes[:10]]
        assert [r['gid'] for r in b['items']]==[r['gid'] for r in nodes[10:20]]
        assert all(r['investigation_queue']==queue for r in a['items'])
    assert client.get('/api/queues/UNKNOWN').status_code==404
    assert client.get('/api/queues/MONITOR?limit=100000').status_code==422
    assert client.get('/api/queues/MONITOR?offset=-1').status_code==422


def test_every_gid_exact_search_and_string_roundtrip(client, app):
    for gid in app.state.store.nodes:
        result=client.get('/api/search',params={'q':gid}).json()
        assert result['exact'] and result['total']==1
        assert json.loads(json.dumps(result))['items'][0]['gid']==gid
        assert isinstance(result['items'][0]['gid'],str)


def test_node_card_precision_gaps_and_alternatives(client, app):
    ids=random.Random(42).sample(list(app.state.store.nodes),5)
    ids+=['100000003115284100','100000003684369100','100000003037476100']
    for gid in ids:
        result=client.get('/api/nodes/'+gid).json()
        assert result['gid']==gid
        assert result['role']==app.state.store.nodes[gid]['primary_role']
        assert result['data_gaps'] and result['next_data_request']
        assert all(isinstance(g,str) for g in result['cluster']['top_gids'])
        alt=result['alternative_role']
        if alt is None: assert result['alternative_strength']==0
        else: assert result['alternative_strength']==pytest.approx(result['strength_'+alt],abs=1e-9)
    example=client.get('/api/nodes/100000003684369100').json()
    assert example['alternative_role']=='distributor'
    assert example['investigation_queue']=='REQUEST_MORE_DATA'


def test_missing_invalid_and_prefix_search(client):
    assert client.get('/api/nodes/999999999999999999').status_code==404
    assert client.get('/api/nodes/999999999999999999/ego').status_code==404
    assert client.get('/api/search?q=999999999999999999').json()['items']==[]
    assert client.get('/api/search?q=abc').json()['items']==[]
    assert client.get('/api/search?q=').json()['items']==[]
    prefix=client.get('/api/search?q=100000003&limit=7').json()
    assert not prefix['exact'] and len(prefix['items'])==7
    assert all(r['gid'].startswith('100000003') for r in prefix['items'])
    assert client.get('/api/clusters/99999').status_code==404


def test_ego_directions_isolated_and_bounds(client, app):
    isolated=next(gid for gid,n in app.state.store.nodes.items() if n['isolated'])
    edge_lookup={(e['src'],e['dst']):e for e in app.state.store.edges}
    for gid in [isolated,'100000003684369100','100000003115284100','100000003037476100']:
        ego=client.get(f'/api/nodes/{gid}/ego').json()
        assert ego['center_gid']==gid and gid in {n['gid'] for n in ego['nodes']}
        assert all(isinstance(n['gid'],str) for n in ego['nodes'])
        for edge in ego['edges']:
            assert isinstance(edge['src'],str) and isinstance(edge['dst'],str)
            assert edge==edge_lookup[(edge['src'],edge['dst'])]
        if gid==isolated: assert len(ego['nodes'])==1 and not ego['edges']
    limited=client.get('/api/nodes/100000003684369100/ego?max_nodes=3').json()
    assert len(limited['nodes'])==3 and limited['truncated']
    assert limited['omitted_neighbors']==limited['total_neighbors']-2
    assert client.get('/api/nodes/100000003684369100/ego?max_nodes=99999').status_code==422


def test_read_only_download_whitelist_and_static_ui(client):
    before={name:hashlib.sha256((ROOT/'outputs'/name).read_bytes()).hexdigest() for name in DOWNLOADS}
    for name in DOWNLOADS:
        response=client.get('/api/download/'+name)
        assert response.status_code==200
        assert hashlib.sha256(response.content).hexdigest()==before[name]
    assert client.get('/api/download/.env').status_code==404
    assert client.get('/api/download/node_context.json').status_code==404
    assert client.post('/api/nodes/100000003115284100').status_code==405
    assert client.get('/').status_code==200
    assert client.get('/assets/app.js').status_code==200
    assert client.get('/assets/style.css').status_code==200
    assert before=={name:hashlib.sha256((ROOT/'outputs'/name).read_bytes()).hexdigest() for name in DOWNLOADS}


def test_structural_evidence_api_keeps_na_distinct_from_observed_zero(client):
    n=client.get('/api/nodes/100000003037476100').json()
    assert n['out_degree']==0  # actual observed record count remains unchanged
    assert n['evidence_availability']['fan_out']=='CENSORED'
    assert n['evidence_details']['fan_out']['value'] is None
    assert n['evidence_details']['terminal']['value'] is None
    assert n['evidence_details']['fan_in']['value']==3
    d=client.get('/api/nodes/100000003016635100').json()['structural_dependency']
    assert d['dominated_nodes']==102 and d['dominated_clusters']==10


def test_seed_convergence_api_exact_ids_and_unmodified_reach(client, app):
    for gid in ['100000003115284100','100000003016635100','100000003037476100']:
        node = client.get('/api/nodes/'+gid).json()
        c = node['seed_convergence']
        assert c['reachable_seed_count'] == node['reachable_seed_count']
        assert c['external_seed_count'] == c['reachable_seed_count'] - int(node['is_seed'])
        assert all(isinstance(b['predecessor_gid'],str) for b in c['branches'])
        assert c['last_hop_effective_branches'] >= 0
