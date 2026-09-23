import hashlib
import json
from pathlib import Path
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from moneygraph.stability import build,drop_edges,parameter_run,adjusted_role,run,FROZEN
from moneygraph import features,roles
from moneygraph.io import load_data
from moneygraph.pipeline import ROOT,DEFAULT_DATA
from moneygraph.server import create_app,Store

@pytest.fixture(scope='module')
def actual():
    n,e,t=load_data(DEFAULT_DATA)
    return n,e,t,build(n,e,t)


def test_deterministic_row_order_and_ids(actual):
    n,e,t,result=actual
    assert build(n.sample(frac=1,random_state=3),e.sample(frac=1,random_state=4),t.sample(frac=1,random_state=5))==result
    assert len(result['nodes'])==2248
    assert all(isinstance(r['gid'],str) for r in result['nodes'])


def test_baseline_rule_copy_matches_production(actual):
    n,e,t,_=actual;_,f=features.calculate(n,e,t)
    baseline=roles.assign(f);diagnostic=parameter_run(f,{})
    assert baseline.role.tolist()==diagnostic.role.tolist()
    assert diagnostic.priority_score.tolist()==pytest.approx(baseline.priority_score.tolist(),abs=1e-14)
    for row in f.itertuples():
        role,score=adjusted_role(row)
        assert role==baseline.loc[row.Index,'role']
        assert score==pytest.approx(baseline.loc[row.Index,'role_score'],abs=1e-14)


def test_dropout_is_fixed_nonmutating_and_transaction_consistent(actual):
    n,e,t,_=actual;e_before=e.copy(deep=True);t_before=t.copy(deep=True)
    kept,tx,count=drop_edges(e,t,42)
    again,again_tx,again_count=drop_edges(e,t,42)
    assert count==156==again_count and len(kept)==len(e)-count
    pd.testing.assert_frame_equal(kept,again);pd.testing.assert_frame_equal(tx,again_tx)
    pd.testing.assert_frame_equal(e,e_before);pd.testing.assert_frame_equal(t,t_before)
    aggregate=tx.groupby(['src','dst']).agg(sum_tiyn=('sum_tiyn','sum'),n_tx=('sum_tiyn','size')).sort_index()
    pd.testing.assert_frame_equal(aggregate,kept.set_index(['src','dst'])[['sum_tiyn','n_tx']].sort_index())
    g,_=features.calculate(n,kept,tx);assert len(g)==len(n)


def test_ranges_isolates_and_top20(actual):
    n,e,t,result=actual
    original=pd.read_csv(ROOT/'outputs/top_nodes.csv',dtype={'gid':str})
    assert {r['gid'] for r in result['nodes'] if r['baseline_top20']}==set(original.head(20).gid)
    for row in result['nodes']:
        for family in ['parameter','edge_dropout']:
            v=row[family]
            if row['status']=='NOT_EVALUABLE':
                assert v['role_stability'] is None and v['rank_range'] is None and row['baseline_rank'] is None
            else:
                assert 0<=v['role_stability']<=1 and 0<=v['top20_inclusion']<=1
                assert v['role_stability']==v['role_matches']/v['runs']
                if v['rank_range']:assert 1<=v['rank_range'][0]<=v['rank_range'][1]<=2248
    for family,s in result['summary'].items():
        assert 0<=s['mean_top20_jaccard']<=1
        assert sum(s['role_status_counts'].values())==2248


def test_core_and_ai_artifacts_frozen(tmp_path):
    paths=[ROOT/'outputs'/name for name in FROZEN]+[ROOT/'audit/phase5_live_verification.json',ROOT/'moneygraph/analyst.py']
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    for name in FROZEN:(tmp_path/name).write_bytes((ROOT/'outputs'/name).read_bytes())
    result=run(out=tmp_path)
    assert result['elapsed_seconds']>0
    assert {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}==before
    for name in FROZEN:assert (tmp_path/name).read_bytes()==(ROOT/'outputs'/name).read_bytes()


def test_server_optional_stability_and_stale_guard(tmp_path):
    for name in FROZEN+['run_report.json','stability.json']:(tmp_path/name).write_bytes((ROOT/'outputs'/name).read_bytes())
    app=create_app(out=tmp_path);client=TestClient(app)
    assert client.get('/api/stability/summary').json()['available']
    assert client.get('/api/nodes/100000003115284100').json()['stability']['gid']=='100000003115284100'
    diagnostic=json.loads((tmp_path/'stability.json').read_text());diagnostic['input_sha256']['nodes.parquet']='stale'
    (tmp_path/'stability.json').write_text(json.dumps(diagnostic))
    stale=Store(DEFAULT_DATA,tmp_path)
    assert not stale.stability_summary['available'] and all(n['stability'] is None for n in stale.nodes.values())
    (tmp_path/'stability.json').unlink()
    missing=Store(DEFAULT_DATA,tmp_path)
    assert not missing.stability_summary['available'] and len(missing.nodes)==2248
