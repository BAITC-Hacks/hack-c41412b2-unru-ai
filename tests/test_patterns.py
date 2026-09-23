import hashlib
import json
import shutil
from pathlib import Path
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from moneygraph.patterns import compatible_flow, repeated_episodes, short_cycles, build, run
from moneygraph.pipeline import ROOT, DEFAULT_DATA
from moneygraph.server import create_app


def d(day):return pd.Timestamp(f'2026-07-{day:02d}')


def frames(rows,depths=None,count=25):
    ids=list(range(1,count+1))
    n=pd.DataFrame({'gid':ids,'depth':[(depths or {}).get(g,1) for g in ids],'is_seed':[False]*count})
    t=pd.DataFrame(rows,columns=['src','dst','date','sum_tiyn']);t['date']=pd.to_datetime(t.date)
    t['sum_kzt']=t.sum_tiyn/100
    e=t.groupby(['src','dst']).agg(sum_tiyn=('sum_tiyn','sum'),n_tx=('sum_tiyn','size')).reset_index()
    e['sum_kzt']=e.sum_tiyn/100;e['depth']=1
    return n,e,t


def test_flow_capacities_no_double_count_same_day_and_month_end():
    result=compatible_flow({d(1):10000,d(2):10000,d(30):90000,d(31):90000},{d(1):999999,d(3):15000,d(31):999999},d(31))
    assert result=={'eligible_in_kzt':200,'compatible_out_kzt':150,'compatibility_fraction':.75,'right_censored_in_kzt':1800}
    assert compatible_flow({d(1):100},{d(1):100},d(31))['compatible_out_kzt']==0
    assert compatible_flow({d(1):100},{d(4):100},d(31))['compatible_out_kzt']==0
    assert compatible_flow({d(30):100},{d(31):100},d(31))['compatibility_fraction'] is None
    assert compatible_flow({d(1):100,d(2):100},{d(2):100,d(3):100},d(31))['compatible_out_kzt']==2


def test_matching_repeated_distinct_day_pairs():
    result=repeated_episodes({d(1),d(2),d(7)},{d(3),d(8)})
    assert result==[{'in_date':'2026-07-01','out_date':'2026-07-03'},{'in_date':'2026-07-07','out_date':'2026-07-08'}]
    assert repeated_episodes({d(1)},{d(1),d(4)})==[]


def test_cycles_unique_directed_simple_and_bounded():
    adj={1:{2},2:{1,3},3:{1,4},4:{1}}
    cycles,truncated,_=short_cycles(adj)
    assert cycles==[[1,2,3,1],[1,2,3,4,1]] and not truncated
    assert short_cycles(adj,max_cycles=1)[1]
    assert short_cycles(adj,max_expansions=1)[1]
    assert short_cycles(dict(reversed(list(adj.items()))))[0]==cycles


def toy_patterns():
    return frames([(1,5,d(5),10000),(2,5,d(5),10000),(3,5,d(5),10000),
        (5,6,d(6),10000),(5,7,d(6),10000),(5,8,d(6),10000),
        (1,5,d(12),10000),(5,6,d(13),10000),(6,1,d(14),10000),
        (5,1,d(15),5000),(1,25,d(30),10000)],{25:4})


def test_gather_repeated_reciprocal_peers_censoring_and_equal_amounts():
    r=build(*toy_patterns(),'2026-07-01','2026-07-31');ns={n['gid']:n for n in r['nodes']}
    x=ns['5']
    assert x['temporal']['gather_scatter_count']==1
    assert x['temporal']['gather_scatter_samples'][0]['senders']==3
    assert any(c['gids']==['1','5','6'] and c['support_episodes']==2 for c in x['routes']['repeated_chain_samples'])
    assert x['routes']['reciprocal_count']==1 and x['routes']['short_cycle_count']>=1
    assert x['anomalies']['equal_amount_distribution_count']==1
    assert x['anomalies']['equal_amount_samples'][0]['recipient_count']==3
    boundary=ns['25']
    assert boundary['temporal']['compatible_out_kzt'] is None
    assert boundary['temporal']['gather_scatter_count'] is None
    assert boundary['anomalies']['peers']['out_counterparties']['status']=='CENSORED'
    assert boundary['anomalies']['peers']['incoming_volume_kzt']['status']=='SMALL_COHORT'
    assert all(not p['flag'] for p in ns['24']['anomalies']['peers'].values())
    assert x['anomalies']['peers']['max_daily_fan_out']['flag']


def test_order_determinism_duplicate_rows_and_window_validation():
    n,e,t=toy_patterns();a=build(n,e,t,'2026-07-01','2026-07-31')
    assert build(n.iloc[::-1],e.iloc[::-1],t.iloc[::-1],'2026-07-01','2026-07-31')==a
    n,e,t=frames([(1,2,d(1),100),(1,2,d(1),100),(2,3,d(2),200)])
    ns={r['gid']:r for r in build(n,e,t,'2026-07-01','2026-07-31')['nodes']}
    assert ns['2']['temporal']['eligible_in_kzt']==2
    assert ns['2']['temporal']['compatible_out_kzt']==2
    with pytest.raises(ValueError):build(n,e,t,'2026-07-02','2026-07-31')


def test_real_data_coverage_invariants_and_frozen_baseline(tmp_path):
    names=['nodes_roles.csv','clusters.csv','top_nodes.csv','node_context.json','structural_evidence.json','seed_convergence.json']
    before={name:hashlib.sha256((ROOT/'outputs'/name).read_bytes()).hexdigest() for name in names}
    result=run(DEFAULT_DATA,tmp_path)
    assert result['summary']['nodes']==2248 and not result['summary']['cycles_truncated']
    assert len({r['gid'] for r in result['nodes']})==2248
    assert before=={name:hashlib.sha256((ROOT/'outputs'/name).read_bytes()).hexdigest() for name in names}
    n,e,t=toy_patterns()
    for r in result['nodes']:
        temporal=r['temporal'];v=temporal['compatibility_fraction']
        assert v is None or 0<=v<=1
        if r['depth']==4:assert v is None
        else:assert temporal['compatible_out_kzt']<=temporal['eligible_in_kzt']+1e-8
        for group in ['repeated_chain_samples','reciprocal_samples','short_cycle_samples']:
            assert len(r['routes'][group])<=10
            assert all(isinstance(g,str) for p in r['routes'][group] for g in p['gids'])


def test_api_optional_missing_stale_corrupt_and_fresh(tmp_path):
    for p in (ROOT/'outputs').glob('*'):
        if p.is_file() and p.name!='patterns.json':shutil.copy(p,tmp_path/p.name)
    app=create_app(out=tmp_path)
    with TestClient(app) as client:assert not client.get('/api/patterns/summary').json()['available']
    data=run(DEFAULT_DATA,tmp_path)
    app=create_app(out=tmp_path)
    with TestClient(app) as client:
        assert client.get('/api/patterns/summary').json()['available']
        assert client.get('/api/nodes/100000003115284100').json()['patterns']['gid']=='100000003115284100'
    data['input_sha256']['nodes.parquet']='invalid'
    (tmp_path/'patterns.json').write_text(json.dumps(data))
    assert not create_app(out=tmp_path).state.store.patterns_summary['available']
    (tmp_path/'patterns.json').write_text('broken')
    assert not create_app(out=tmp_path).state.store.patterns_summary['available']
