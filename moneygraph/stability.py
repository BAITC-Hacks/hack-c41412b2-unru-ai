"""Fixed sensitivity scenarios, separate from the production engine and its outputs."""
import argparse
import hashlib
import json
import math
import random
import time
from pathlib import Path
import pandas as pd
from . import features, roles
from .io import load_data
from .pipeline import ROOT, DEFAULT_DATA

PRIORITY = {'volume':.30,'neighbors':.25,'seed_reach':.20,'role_strength':.15,'pagerank':.10}
PARAMETERS = [
    {'id':'volume_plus10','priority_factor':{'volume':1.1}},
    {'id':'volume_minus10','priority_factor':{'volume':.9}},
    {'id':'neighbors_plus10','priority_factor':{'neighbors':1.1}},
    {'id':'neighbors_minus10','priority_factor':{'neighbors':.9}},
    {'id':'seed_reach_plus10','priority_factor':{'seed_reach':1.1}},
    {'id':'without_pagerank','priority_factor':{'pagerank':0}},
    {'id':'role_first_component_plus10','role_first_factor':1.1},
    {'id':'role_first_component_minus10','role_first_factor':.9},
    {'id':'thresholds_stricter','threshold_shift':1},
    {'id':'thresholds_looser','threshold_shift':-1},
]
DROPOUT_SEEDS = [42,43,44]
FROZEN = ['nodes_roles.csv','clusters.csv','top_nodes.csv','node_context.json','structural_evidence.json','seed_convergence.json']


def adjusted_role(r, first_factor=1.0, shift=0):
    # Diagnostic copy of PHASE 1 rules. Production roles.py is intentionally frozen.
    strengths = dict.fromkeys(roles.ROLE_ORDER,0.0)
    def weighted(weights, values):
        changed=[weights[0]*first_factor,*weights[1:]]
        return sum(w*x for w,x in zip(changed,values))/sum(changed)
    if r.in_degree>=3+shift and r.out_degree>=3+shift and r.reachable_seed_count>=2+shift:
        strengths['coordinator']=weighted([.4,.35,.25],[min(min(r.in_degree,r.out_degree)/8,1),min(r.reachable_seed_count/5,1),r.pagerank_percentile])
    if r.out_degree>=5+shift:
        strengths['distributor']=weighted([.55,.25,.20],[min(r.out_degree/20,1),1-r.out_max_share,r.out_percentile])
    if r.in_degree>=3+shift and r.out_degree<=max(2,r.in_degree/2):
        strengths['consolidator']=weighted([.50,.30,.20],[min(r.in_degree/8,1),1-r.in_max_share,r.in_percentile])
    width=.2-.05*shift
    if not r.is_seed and r.in_tiyn>0 and r.out_tiyn>0 and 1-width<=r.observed_out_in_ratio<=1+width:
        strengths['transit']=weighted([.50,.25,.25],[max(0,1-abs(r.observed_out_in_ratio-1)/.2),min(min(r.in_tx,r.out_tx)/5,1),min(min(r.in_degree,r.out_degree)/3,1)])
    if not r.is_seed and r.depth<4 and r.out_degree==0 and 1<=r.in_degree<=2 and r.in_tx>=3+shift and r.in_days>=2+shift:
        strengths['terminal']=weighted([.40,.35,.25],[min(r.in_tx/10,1),min(r.in_days/5,1),r.in_percentile])
    role=max(roles.ROLE_ORDER,key=lambda name:strengths[name]);score=strengths[role]
    return (role if score>0 else 'peripheral'),score


def parameter_run(frame, scenario):
    result=roles.assign(frame)
    if 'role_first_factor' in scenario or 'threshold_shift' in scenario:
        records=[adjusted_role(row,scenario.get('role_first_factor',1),scenario.get('threshold_shift',0)) for row in frame.itertuples()]
        result['role']=[r[0] for r in records];result['role_score']=[r[1] for r in records]
    weights={k:w*scenario.get('priority_factor',{}).get(k,1) for k,w in PRIORITY.items()}
    total=sum(weights.values());weights={k:w/total for k,w in weights.items()}
    result['priority_score']=(weights['volume']*result.volume_percentile +weights['neighbors']*result.neighbors_percentile+
        weights['seed_reach']*(result.reachable_seed_count/5).clip(upper=1)+weights['role_strength']*result.role_score+
        weights['pagerank']*result.pagerank_percentile)
    result.loc[result.isolated,'priority_score']=0.0
    return result


def drop_edges(edges, tx, seed, fraction=.05):
    ordered=edges.sort_values(['src','dst']).reset_index(drop=True)
    count=math.ceil(len(ordered)*fraction)
    removed=set(random.Random(seed).sample(range(len(ordered)),count))
    kept=ordered.loc[[i not in removed for i in range(len(ordered))]].copy()
    pairs=set(zip(kept.src,kept.dst))
    kept_tx=tx.loc[[(s,d) in pairs for s,d in zip(tx.src,tx.dst)]].copy()
    return kept,kept_tx,count


def rank(frame):
    order=frame.reset_index().sort_values(['priority_score','gid'],ascending=[False,True]).gid.tolist()
    return {gid:i+1 for i,gid in enumerate(order)},set(order[:20])


def build(nodes, edges, tx):
    # Sorted inputs avoid order-sensitive tie handling and RNG sampling.
    nodes=nodes.sort_values('gid');edges=edges.sort_values(['src','dst'])
    _,frame=features.calculate(nodes,edges,tx)
    baseline=roles.assign(frame);base_ranks,base_top=rank(baseline)
    families={};definitions={}
    for family in ['parameter','edge_dropout']:
        runs=[]
        if family=='parameter':
            definitions[family]=PARAMETERS
            runs=[(s['id'],parameter_run(frame,s)) for s in PARAMETERS]
        else:
            definitions[family]=[]
            for seed in DROPOUT_SEEDS:
                e,t,count=drop_edges(edges,tx,seed)
                _,f=features.calculate(nodes,e,t)
                runs.append((f'drop5_seed{seed}',roles.assign(f)))
                definitions[family].append({'id':runs[-1][0],'random_seed':seed,'removed_edges':count,'fraction_requested':.05})
        families[family]=[]
        for name,run in runs:
            ranks,top=rank(run)
            families[family].append({'id':name,'roles':run.role.to_dict(),'ranks':ranks,'top':top,
                                    'top20_jaccard':len(base_top&top)/len(base_top|top)})
    records=[]
    for r in baseline.sort_index().itertuples():
        gid=r.Index
        meaningful=base_ranks[gid]<=100 or any(gid in run['top'] for runs in families.values() for run in runs)
        result={'gid':str(gid),'baseline_role':r.role,'baseline_rank':None if r.isolated else base_ranks[gid],
                'baseline_top20':gid in base_top,'status':'NOT_EVALUABLE' if r.isolated else 'AVAILABLE'}
        for family,runs in families.items():
            if r.isolated:
                result[family]={'runs':len(runs),'role_matches':None,'role_stability':None,'top20_count':None,'top20_inclusion':None,'rank_range':None,'role_status':'NOT_EVALUABLE','competing_roles':[]}
                continue
            matches=sum(run['roles'][gid]==r.role for run in runs)
            inclusion=sum(gid in run['top'] for run in runs)
            ranks=[run['ranks'][gid] for run in runs]
            result[family]={'runs':len(runs),'role_matches':matches,'role_stability':matches/len(runs),
                'top20_count':inclusion,'top20_inclusion':inclusion/len(runs),
                'rank_range':[min(ranks),max(ranks)] if meaningful else None,
                'role_status':'STABLE' if matches/len(runs)>=.9 else 'SENSITIVE',
                'competing_roles':sorted({run['roles'][gid] for run in runs}-{r.role})}
        records.append(result)
    summary={family:{'runs':len(runs),'mean_top20_jaccard':sum(r['top20_jaccard'] for r in runs)/len(runs),
                     'scenarios':[{'id':r['id'],'top20_jaccard':r['top20_jaccard']} for r in runs],
                     'role_status_counts':pd.Series([n[family]['role_status'] for n in records]).value_counts().to_dict()}
             for family,runs in families.items()}
    return {'schema_version':1,'definitions':definitions,'summary':summary,'nodes':records,
            'scope':'Diagnostic sensitivity, not accuracy, probability or confidence interval. Fixed edge dropout is a stress test, not a model of real missingness. Production outputs unchanged.',
            'stable_rule':'STABLE means role matches baseline in at least 90% of the selected scenario family. This threshold is a display convention, not validation.'}


def run(data=DEFAULT_DATA,out=ROOT/'outputs'):
    start=time.perf_counter();n,e,t=load_data(data);result=build(n,e,t)
    result['input_sha256']={name:hashlib.sha256((Path(data)/name).read_bytes()).hexdigest() for name in ['nodes.parquet','edges.parquet','transactions.parquet']}
    result['calculation_sha256']={name:hashlib.sha256((Path(out)/name).read_bytes()).hexdigest() for name in FROZEN}
    result['elapsed_seconds']=round(time.perf_counter()-start,4)
    target=Path(out)/'stability.json';temporary=target.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n');temporary.replace(target)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--data',type=Path,default=DEFAULT_DATA);parser.add_argument('--out',type=Path,default=ROOT/'outputs')
    args=parser.parse_args();result=run(args.data,args.out)
    print(json.dumps({'elapsed_seconds':result['elapsed_seconds'],'summary':result['summary']},indent=2))

if __name__=='__main__':main()
