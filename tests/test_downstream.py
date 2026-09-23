from types import SimpleNamespace
import json
import pytest
from moneygraph.downstream import find_candidates
from moneygraph.analyst import Analyst,ToolLayer
from moneygraph.server import create_app


def toy(edges):
    nodes={str(g):{'primary_role':'peripheral','primary_strength':0.0,'alternative_role':None,'alternative_strength':0.0,'priority_score':0.0,'depth':1,'observability_level':'LOW'} for pair in edges for g in pair}
    return nodes,[{'src':str(a),'dst':str(b)} for a,b in edges]


def test_common_partial_cutoff_and_exact_paths():
    nodes,edges=toy([(1,6),(2,6),(3,6),(4,6),(5,6),(1,7),(2,7),(3,7),(4,7),(6,8),(8,9),(9,10),(10,11)])
    r=find_candidates(nodes,edges,['1','2','3','4','5'])
    assert r['common_to_all_count']==4
    assert r['partial_candidate_count']==1
    assert '11' not in {c['gid'] for c in r['candidates']}
    partial=next(c for c in r['candidates'] if c['gid']=='7')
    assert partial['source_count']==4 and not partial['reaches_all_sources']
    assert r['candidates'][0]['gid']=='6' and r['candidates'][0]['min_hops']==1
    pairs={(e['src'],e['dst']) for e in edges}
    for c in r['candidates']:
        for path in c['paths']:
            p=path['one_observed_path'];assert p[0]==path['source_gid'] and p[-1]==c['gid']
            assert len(p)-1==path['hops']<=4
            assert all(pair in pairs for pair in zip(p,p[1:]))


def test_cycles_inputs_excluded_and_no_common():
    nodes,edges=toy([(1,2),(2,1),(2,3),(4,5)])
    r=find_candidates(nodes,edges,['1','2'])
    assert [c['gid'] for c in r['candidates']]==['3']
    assert not find_candidates(nodes,edges,['1','4'])['candidates']
    assert find_candidates(nodes,edges,['1','1'])['source_total']==1
    with pytest.raises(ValueError):find_candidates(nodes,edges,['1']*6)
    with pytest.raises(ValueError):find_candidates(nodes,edges,[1])
    with pytest.raises(ValueError):find_candidates(nodes,edges,['1'],5)


def test_order_determinism_limit_and_read_only():
    ids=['100000003115284100','100000003115284101']
    nodes,edges=toy([(ids[0],str(100000003115285000+i)) for i in range(25)]+[(ids[1],str(100000003115285000+i)) for i in range(25)])
    before=json.dumps([nodes,edges],sort_keys=True)
    r=find_candidates(nodes,edges,ids)
    assert len(r['candidates'])==20 and r['truncated'] and r['common_to_all_count']==25
    assert find_candidates(dict(reversed(list(nodes.items()))),list(reversed(edges)),ids)==r
    assert before==json.dumps([nodes,edges],sort_keys=True)
    assert all(isinstance(c['gid'],str) for c in r['candidates'])


def test_group_tool_and_agent_coverage():
    nodes,edges=toy([(i,6) for i in range(1,6)])
    store=SimpleNamespace(nodes=nodes,edges=edges);gids=[str(i) for i in range(1,6)]
    layer=ToolLayer(store,gids)
    result=layer.call('find_common_downstream',{'gids':gids,'max_hops':4})
    assert result['candidates'][0]['source_count']==5
    seen=[]
    def transport(payload,key):
        seen.append(payload)
        if len(seen)==1:return {'output':[{'type':'function_call','name':'find_common_downstream','call_id':'g','arguments':json.dumps({'gids':gids,'max_hops':4})}]}
        answer={'conclusion':'Найден кандидат 6','why':['Покрытие 5/5','Один переход'],'alternative':'Других кандидатов нет','evidence_against':'Пути не доказывают роль','limitation':'Наблюдаемый граф','next_step':'Проверить входящие','sources':['T1']}
        return {'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(answer)}]}]}
    events=list(Analyst(store,transport,lambda:('test','test')).events('1','Кто собирает деньги?',source_gids=gids))
    assert events[-1]['type']=='result' and events[-1]['trace'][0]['tool']=='find_common_downstream'
    assert len(seen)==2


def test_real_five_sources_and_question_scope():
    app=create_app();store=app.state.store
    sources=sorted({e['src'] for e in store.edges if e['dst']=='100000003115284100'},key=int)[:5]
    r=ToolLayer(store,sources).call('find_common_downstream',{'gids':sources,'max_hops':4})
    target=next(c for c in r['candidates'] if c['gid']=='100000003115284100')
    assert target['source_count']==5 and target['max_hops']==1
    # Existing selected gid must not silently become a sixth source.
    sent=[]
    def transport(payload,key):
        sent.append(json.loads(payload['input'][0]['content']));return {'output':[]}
    a=Analyst(store,transport,lambda:('test','test'))
    list(a.events('100000003684369100','Кто собирает деньги с '+', '.join(sources)+'?'))
    assert sent[0]['requested_gids']==sources


def test_invalid_source_reference_is_repaired_within_existing_budget():
    nodes,edges=toy([(i,6) for i in range(1,6)])
    store=SimpleNamespace(nodes=nodes,edges=edges);gids=[str(i) for i in range(1,6)]
    calls=[]
    def transport(payload,key):
        calls.append(payload)
        if len(calls)==1:
            return {'output':[{'type':'function_call','name':'find_common_downstream','call_id':'g','arguments':json.dumps({'gids':gids,'max_hops':4})}]}
        answer={'conclusion':'Кандидат 6','why':['5/5','1 переход'],'alternative':'Нет другой гипотезы','evidence_against':'Не доказательство','limitation':'Наблюдаемая выборка','next_step':'Проверить данные','sources':['T999' if len(calls)==2 else 'T1']}
        return {'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(answer)}]}]}
    events=list(Analyst(store,transport,lambda:('test','test')).events('1','Общий кандидат',source_gids=gids))
    assert len(calls)==3 and events[-1]['type']=='result'
    assert events[-1]['answer']['sources']==['T1']
    assert any('Проверяются ссылки' in e.get('message','') for e in events)
