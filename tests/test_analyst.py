import copy
import json
import pytest
from fastapi.testclient import TestClient
from moneygraph.analyst import Analyst, ToolLayer, POLICY, Answer
from moneygraph.server import create_app

A='100000003115284100'
B='100000003684369100'
BOUNDARY='100000003037476100'

@pytest.fixture(scope='module')
def app(): return create_app()

@pytest.fixture
def layer(app): return ToolLayer(app.state.store,[A,B,BOUNDARY])


def test_tools_exact_store_data_and_string_ids(layer):
    p=layer.call('get_node_profile',{'gid':A});n=layer.store.nodes[A]
    assert p['gid']==A and isinstance(p['gid'],str)
    assert p['primary_strength']==n['primary_strength']
    assert p['metrics']==n['metrics']
    assert p['seed_convergence']['effective_last_hop_branches']==n['seed_convergence']['effective_last_hop_branches']
    assert 'branches' not in p['seed_convergence']
    assert sum(p['priority_contributions'].values())==pytest.approx(n['priority_score'],abs=1e-9)
    assert layer.call('get_cluster_context',{'gid':A})['n_nodes']==layer.store.clusters[n['cluster_id']]['n_nodes']
    neighbors=layer.call('get_neighbors',{'gid':B})
    assert len(neighbors['links'])<=30 and neighbors['truncated']
    assert all(isinstance(e['src'],str) and isinstance(e['dst'],str) for e in neighbors['links'])
    p['metrics']['in_degree']=-99
    assert n['metrics']['in_degree']>=0


def test_invalid_gid_scope_and_arguments(layer):
    for args in [{'gid':'999999999999999999'},{'gid':int(A)},{'gid':A,'extra':1},{'gid':'100000003016635100'}]:
        with pytest.raises(ValueError):layer.call('get_node_profile',args)
    with pytest.raises(ValueError):layer.call('run_shell',{'gid':A})


def test_boundary_seed_and_dominator_limitations(layer):
    gaps=layer.call('get_data_gaps',{'gid':BOUNDARY})
    assert gaps['censored_or_na']['fan_out']['status']=='CENSORED'
    assert gaps['censored_or_na']['terminal']['status']=='NOT_EVALUABLE'
    assert layer.call('get_data_gaps',{'gid':B})['observability_reasons']
    s=layer.call('get_structural_evidence',{'gid':A})
    assert 'не контроль' in s['structural_dependency']['limitation']
    assert 'NOT independent routes' in POLICY and 'NOT control of money' in POLICY


def test_comparison_decomposition_and_nonmutation(layer):
    before=copy.deepcopy(layer.store.nodes[A])
    c=layer.call('compare_nodes',{'gid_a':A,'gid_b':B})
    assert [n['profile']['gid'] for n in c['nodes']]==[A,B]
    for k,d in c['priority_contribution_delta_a_minus_b'].items():
        assert d==c['nodes'][0]['profile']['priority_contributions'][k]-c['nodes'][1]['profile']['priority_contributions'][k]
    assert layer.store.nodes[A]==before


def call(name,gid,i):
    return {'type':'function_call','name':name,'arguments':json.dumps({'gid':gid}),'call_id':str(i)}


def valid_answer():
    return dict(conclusion='Гипотеза требует проверки.',why=['Наблюдаемые связи.','Рассчитанный приоритет.'],alternative='Нужна проверка альтернативы.',evidence_against='Полнота неизвестна.',limitation='Только наблюдаемая выборка.',next_step='Запросить историю для проверки источников.',sources=['T1','T2','T3'])


def test_agent_real_protocol_with_fake_transport(app):
    payloads=[]
    def transport(payload,key):
        payloads.append(copy.deepcopy(payload));assert key=='test-key'
        if len(payloads)==1:
            return {'status':'completed','output':[call(n,A,i) for i,n in enumerate(['get_node_profile','get_structural_evidence','get_data_gaps'])]}
        return {'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(valid_answer())}]}]}
    a=Analyst(app.state.store,transport,lambda:('test-key','test-model'))
    events=list(a.events(A,'Почему?'));assert events[-1]['type']=='result'
    assert len(events[-1]['trace'])==3
    assert payloads[0]['store'] is False and payloads[0]['tool_choice']=='required'
    assert payloads[1]['tool_choice']=='auto'
    assert 'test-key' not in json.dumps(payloads)
    assert not any('parquet' in str(v) for v in payloads[0]['input'])


@pytest.mark.parametrize('response',[
    {'output':[{'type':'message','content':[{'type':'output_text','text':'{}'}]}]},
    {'status':'incomplete','output':[]},
    {'output':'invalid'},
])
def test_bad_early_ai_output_safe(app,response):
    a=Analyst(app.state.store,lambda *_:response,lambda:('test','test'))
    assert list(a.events(A,'Почему?'))[-1]['type']=='error'
    assert not a.lock.locked()


def test_malformed_final_answer_safe(app):
    count=0
    def transport(*_):
        nonlocal count
        count+=1
        if count==1:return {'output':[call(n,A,i) for i,n in enumerate(['get_node_profile','get_structural_evidence','get_data_gaps'])]}
        return {'output':[{'type':'message','content':[{'type':'output_text','text':'not JSON <script>alert(1)</script>'}]}]}
    a=Analyst(app.state.store,transport,lambda:('test','test'))
    assert list(a.events(A,'Почему?'))[-1]['type']=='error'


def test_missing_key_core_survives_and_key_not_exposed(app):
    app.state.analyst=Analyst(app.state.store,settings=lambda:('','test'))
    client=TestClient(app)
    assert client.get('/api/analyst/status').json()['available'] is False
    response=client.post('/api/analyst/ask',json={'gid':A,'question':'Почему?'})
    assert json.loads(response.text)['type']=='error'
    assert client.get('/api/nodes/'+A).status_code==200
    assert client.get('/api/download/nodes_roles.csv').status_code==200
    app.state.analyst=Analyst(app.state.store,settings=lambda:('secret-test-key','test'))
    for path in ['/api/analyst/status','/assets/app.js','/','/api/nodes/'+A]:
        assert 'secret-test-key' not in client.get(path).text
    assert client.get('/.env').status_code==404


def test_endpoint_validation_and_cross_origin(app):
    client=TestClient(app)
    assert client.post('/api/analyst/ask',json={'gid':int(A),'question':'Почему?'}).status_code==422
    assert client.post('/api/analyst/ask',json={'gid':'999999','question':'Почему?'}).status_code==404
    assert client.post('/api/analyst/ask',headers={'Origin':'https://evil.example'},json={'gid':A,'question':'Почему?'}).status_code==403
    assert client.post('/api/analyst/ask',json={'gid':A,'question':'x'*1501}).status_code==422


def test_no_tools_no_answer_and_unknown_nodes_not_sent(app):
    sent=[]
    a=Analyst(app.state.store,lambda *args:sent.append(args),lambda:('key','test'))
    assert list(a.events(A,'Проверь 999999999999999999'))[-1]['type']=='error'
    assert not sent
    a.lock.acquire()
    assert list(a.events(A,'Почему?'))[-1]['type']=='error'
    a.lock.release()


def test_comparison_requires_both_nodes_and_compare_tool(app):
    count=0
    def transport(*_):
        nonlocal count
        count+=1
        if count==1:
            return {'output':[{'type':'function_call','name':'compare_nodes','call_id':'c','arguments':json.dumps({'gid_a':A,'gid_b':B})}]}
        answer=valid_answer();answer['sources']=['T1'];answer['alternative']='Для второго узла distributor'
        return {'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(answer)}]}]}
    a=Analyst(app.state.store,transport,lambda:('key','test'))
    result=list(a.events(A,'Сравни',B))[-1]
    assert result['type']=='result' and result['trace'][0]['tool']=='compare_nodes'


def test_convergence_rename_preserves_phase4b_values():
    import hashlib
    from moneygraph.pipeline import ROOT
    digest=json.loads((ROOT/'tests/phase4b_convergence_sha256.json').read_text())['canonical_sha256']
    current=json.loads((ROOT/'outputs/seed_convergence.json').read_text())
    for row in current['nodes']:
        c=row['seed_convergence'];c['last_hop_effective_branches']=c.pop('effective_last_hop_branches')
    assert hashlib.sha256(json.dumps(current,sort_keys=True).encode()).hexdigest()==digest


def test_semantic_guard_checks_existing_alternative_and_boundary(app):
    a=Analyst(app.state.store)
    answer=Answer(**valid_answer())
    assert a.answer_issues(answer,[B],'Оспорь гипотезу')
    answer.alternative='distributor'
    assert not a.answer_issues(answer,[B],'Оспорь гипотезу')
    answer.conclusion='Скорее нет, нельзя подтвердить.'
    assert a.answer_issues(answer,[BOUNDARY],'Это конечный получатель?')
    answer.conclusion='Определить невозможно по границе выгрузки.'
    assert not a.answer_issues(answer,[BOUNDARY],'Это конечный получатель?')
