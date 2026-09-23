"""Observed temporal, route and depth-peer patterns. No baseline mutation."""
import argparse
from collections import defaultdict, Counter
import hashlib
import json
from pathlib import Path
import time
import networkx as nx
import pandas as pd
from .io import load_data
from .pipeline import ROOT, DEFAULT_DATA

SAMPLE_LIMIT = 10
CYCLE_LIMIT = 10000
EXPANSION_LIMIT = 200000
DAY = pd.Timedelta(days=1)


def compatible_flow(incoming, outgoing, end):
    """Maximum amount compatible with +1/+2 days, capacities used only once."""
    eligible = {d:v for d,v in incoming.items() if d + 2*DAY <= end}
    graph = nx.DiGraph()
    graph.add_nodes_from(['source', 'sink'])
    for d, value in sorted(eligible.items()):
        graph.add_edge('source', ('in',d), capacity=int(value))
        for lag in [1,2]:
            later = d + lag*DAY
            if later in outgoing:
                graph.add_edge(('in',d), ('out',later), capacity=int(value))
    for d,value in sorted(outgoing.items()):
        graph.add_edge(('out',d), 'sink', capacity=int(value))
    amount = int(nx.maximum_flow_value(graph,'source','sink'))
    total = sum(eligible.values())
    return {'eligible_in_kzt':total/100, 'compatible_out_kzt':amount/100,
            'compatibility_fraction':amount/total if total else None,
            'right_censored_in_kzt':(sum(incoming.values())-total)/100}


def repeated_episodes(left_dates, right_dates):
    """Distinct day-bucket pairs within a chain. No bucket reused in that chain."""
    remaining = set(right_dates); result=[]
    for day in sorted(left_dates):
        choices = [day+lag*DAY for lag in [1,2] if day+lag*DAY in remaining]
        if choices:
            later=choices[0];remaining.remove(later)
            result.append({'in_date':day.date().isoformat(),'out_date':later.date().isoformat()})
    return result


def short_cycles(adjacency, max_cycles=CYCLE_LIMIT, max_expansions=EXPANSION_LIMIT):
    """Canonical directed simple cycles of length 3–4, bounded and deterministic."""
    cycles=[];expansions=0;truncated=False
    for start in sorted(adjacency):
        stack=[(start,[start])]
        while stack:
            node,path=stack.pop()
            for neighbor in sorted(adjacency[node],reverse=True):
                expansions+=1
                if expansions>max_expansions:
                    return cycles,True,expansions-1
                if neighbor==start and len(path) in (3,4):
                    if len(cycles)>=max_cycles:return cycles,True,expansions
                    cycles.append(path+[start])
                elif len(path)<4 and neighbor>start and neighbor not in path:
                    stack.append((neighbor,path+[neighbor]))
    return sorted(cycles),truncated,expansions


def build(nodes, edges, tx, period_start, period_end):
    start=pd.Timestamp(period_start).normalize();end=pd.Timestamp(period_end).normalize()
    if start>end:raise ValueError('Invalid observation window')
    tx=tx.copy();tx['day']=tx.date.dt.normalize()
    if not tx.day.between(start,end).all():raise ValueError('Transactions outside declared observation window')
    ids=sorted(int(g) for g in nodes.gid)
    incoming={g:defaultdict(int) for g in ids};outgoing={g:defaultdict(int) for g in ids}
    senders={g:defaultdict(set) for g in ids};receivers={g:defaultdict(set) for g in ids}
    day_counts={g:Counter() for g in ids};in_count=Counter();out_count=Counter()
    edge_days=defaultdict(set);equal=defaultdict(set);edge_amount={}
    adjacency={g:set() for g in ids};predecessors={g:set() for g in ids}
    for r in edges.itertuples():
        a,b=int(r.src),int(r.dst);adjacency[a].add(b);predecessors[b].add(a)
        edge_amount[a,b]=int(r.sum_tiyn)
    for r in tx.itertuples():
        a,b,d,v=int(r.src),int(r.dst),r.day,int(r.sum_tiyn)
        incoming[b][d]+=v;outgoing[a][d]+=v
        senders[b][d].add(a);receivers[a][d].add(b)
        in_count[b]+=1;out_count[a]+=1;day_counts[a][d]+=1;day_counts[b][d]+=1
        edge_days[a,b].add(d);equal[a,d,v].add(b)
    records={}
    for n in nodes.sort_values('gid').itertuples():
        g=int(n.gid);boundary=int(n.depth)==4;inc=incoming[g];out=outgoing[g]
        temporal=compatible_flow(inc,out,end)
        temporal.update({'status':'CENSORED' if boundary else 'PARTIAL',
            'observed_in_kzt':sum(inc.values())/100,
            'same_day_overlap_kzt':sum(min(v,out.get(d,0)) for d,v in inc.items())/100,
            'same_day_order':'UNKNOWN',
            'daily':[{'date':d.date().isoformat(),'in_kzt':inc.get(d,0)/100,'out_kzt':None if boundary else out.get(d,0)/100,
                      'senders':len(senders[g].get(d,set())),'recipients':None if boundary else len(receivers[g].get(d,set()))} for d in sorted(set(inc)|set(out))]})
        if boundary:
            temporal.update(compatible_out_kzt=None,compatibility_fraction=None,same_day_overlap_kzt=None)
        gather=[]
        for d,who in sorted(senders[g].items()):
            following=receivers[g].get(d+DAY,set()) | receivers[g].get(d+2*DAY,set())
            if not boundary and d+2*DAY<=end and len(who)>=3 and len(following)>=3:
                gather.append({'date':d.date().isoformat(),'senders':len(who),'following_1_2_day_recipients':len(following),
                    'in_kzt':inc[d]/100,'following_out_kzt':(out.get(d+DAY,0)+out.get(d+2*DAY,0))/100})
        temporal['gather_scatter_count']=None if boundary else len(gather)
        temporal['gather_scatter_samples']=gather[:SAMPLE_LIMIT]
        peak_day=max(day_counts[g],key=lambda d:(day_counts[g][d],-d.value)) if day_counts[g] else None
        total=in_count[g]+out_count[g]
        temporal['activity_burst']={'status':'CENSORED' if boundary else 'AVAILABLE',
            'flag':None if boundary else bool(peak_day is not None and day_counts[g][peak_day]>=5 and day_counts[g][peak_day]/total>=.5),
            'peak_date':peak_day.date().isoformat() if peak_day is not None else None,
            'peak_tx_count':day_counts[g][peak_day] if peak_day is not None else 0,
            'peak_share':day_counts[g][peak_day]/total if total else None}
        records[g]={'gid':str(g),'depth':int(n.depth),'is_seed':bool(n.is_seed),'temporal':temporal,
            'routes':{'repeated_chain_count':0,'repeated_chain_samples':[],'reciprocal_count':0,'reciprocal_samples':[],
                      'short_cycle_count':0,'short_cycle_samples':[]},
            'anomalies':{'peers':{},'flag_count':0,'equal_amount_distribution_count':None if boundary else 0,'equal_amount_samples':[]}}
    chains=0
    for middle in ids:
        for a in sorted(predecessors[middle]):
            for c in sorted(adjacency[middle]-{a}):
                episodes=repeated_episodes(edge_days[a,middle],edge_days[middle,c])
                if len(episodes)<2:continue
                chains+=1
                record={'gids':[str(a),str(middle),str(c)],'support_episodes':len(episodes),'episodes':episodes[:SAMPLE_LIMIT]}
                for g in (a,middle,c):
                    r=records[g]['routes'];r['repeated_chain_count']+=1
                    if len(r['repeated_chain_samples'])<SAMPLE_LIMIT:r['repeated_chain_samples'].append(record)
    reciprocal=0
    for a in ids:
        for b in sorted(adjacency[a]):
            if a<b and a in adjacency[b]:
                reciprocal+=1
                record={'gids':[str(a),str(b),str(a)],'forward_kzt':edge_amount[a,b]/100,'reverse_kzt':edge_amount[b,a]/100}
                for g in (a,b):
                    r=records[g]['routes'];r['reciprocal_count']+=1
                    if len(r['reciprocal_samples'])<SAMPLE_LIMIT:r['reciprocal_samples'].append(record)
    cycles,truncated,expansions=short_cycles(adjacency)
    for path in cycles:
        record={'gids':list(map(str,path)),'length':len(path)-1}
        for g in path[:-1]:
            r=records[g]['routes'];r['short_cycle_count']+=1
            if len(r['short_cycle_samples'])<SAMPLE_LIMIT:r['short_cycle_samples'].append(record)
    for (g,d,v),recipients in sorted(equal.items()):
        if len(recipients)>=3 and records[g]['depth']<4:
            r=records[g]['anomalies'];r['equal_amount_distribution_count']+=1
            if len(r['equal_amount_samples'])<SAMPLE_LIMIT:r['equal_amount_samples'].append({'date':d.date().isoformat(),'amount_kzt':v/100,'recipient_count':len(recipients),'recipient_gids':list(map(str,sorted(recipients)[:10]))})
    metrics={g:{'in_counterparties':len(predecessors[g]),'out_counterparties':len(adjacency[g]),
        'incoming_volume_kzt':sum(incoming[g].values())/100,'observed_volume_kzt':(sum(incoming[g].values())+sum(outgoing[g].values()))/100,
        'tx_count':in_count[g]+out_count[g],
        'max_daily_fan_in':max(map(len,senders[g].values()),default=0),'max_daily_fan_out':max(map(len,receivers[g].values()),default=0)} for g in ids}
    censored={'out_counterparties','observed_volume_kzt','tx_count','max_daily_fan_out'}
    for depth in range(5):
        group=[g for g in ids if records[g]['depth']==depth];size=len(group)
        if not group:continue
        for key in next(iter(metrics.values())):
            values=pd.Series({g:metrics[g][key] for g in group});percentiles=values.rank(method='average',pct=True)
            for g in group:
                status='CENSORED' if depth==4 and key in censored else 'SMALL_COHORT' if size<20 else 'AVAILABLE'
                percentile=float(percentiles[g]) if status=='AVAILABLE' else None
                flag=bool(metrics[g][key]>0 and percentile>=.99) if percentile is not None else None
                records[g]['anomalies']['peers'][key]={'value':metrics[g][key] if status!='CENSORED' else None,'percentile':percentile,'peer_count':size,'status':status,'flag':flag}
                records[g]['anomalies']['flag_count']+=int(flag is True)
    for g,r in records.items():
        r['routes']['cycles_truncated']=truncated
        r['routes']['interpretation']='Observed relationships; cycles have no verified time order, repeated day-pairs do not trace identical funds. Counts are graph patterns, not independent events.'
        r['temporal']['limitation']='Maximum compatible amount, not proven pass-through. Incoming buckets require complete +2 day follow-up. Same-day overlap is separate and must not be added. Month/bank/threshold/upstream incomplete.'
        r['anomalies']['interpretation']='Depth-peer average-rank percentiles, threshold >=99%, positive values only, cohort >=20. Flags are not probability or guilt. Equal amounts do not prove splitting; sub-5000 transfers are absent.'
    return {'schema_version':1,'period':{'start':start.date().isoformat(),'end':end.date().isoformat()},
        'definitions':{'lag_days':[1,2],'gather_min_senders':3,'scatter_min_recipients':3,'chain_min_disjoint_day_pairs':2,'cycle_lengths':[3,4],'cycle_limit':CYCLE_LIMIT,'cycle_expansion_limit':EXPANSION_LIMIT,'sample_limit':SAMPLE_LIMIT,'peer_min_size':20,'peer_percentile_threshold':.99,'burst_min_tx':5,'burst_min_share':.5},
        'summary':{'nodes':len(records),'repeated_chains':chains,'reciprocal_pairs':reciprocal,'short_cycles':len(cycles),'cycles_truncated':truncated,'cycle_expansions':expansions,
            'nodes_with_gather_scatter':sum(bool(r['temporal']['gather_scatter_count']) for r in records.values()),
            'nodes_with_peer_flags':sum(r['anomalies']['flag_count']>0 for r in records.values()),
            'nodes_with_equal_amount_distribution':sum(bool(r['anomalies']['equal_amount_distribution_count']) for r in records.values())},
        'nodes':list(records.values())}


def run(data=DEFAULT_DATA,out=ROOT/'outputs',period_start='2026-07-01',period_end='2026-07-31'):
    begin=time.perf_counter();n,e,t=load_data(data);result=build(n,e,t,period_start,period_end)
    result['input_sha256']={name:hashlib.sha256((Path(data)/name).read_bytes()).hexdigest() for name in ['nodes.parquet','edges.parquet','transactions.parquet']}
    result['elapsed_seconds']=round(time.perf_counter()-begin,4)
    target=Path(out)/'patterns.json';target.parent.mkdir(parents=True,exist_ok=True)
    temp=target.with_suffix('.json.tmp');temp.write_text(json.dumps(result,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n');temp.replace(target)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',type=Path,default=DEFAULT_DATA);p.add_argument('--out',type=Path,default=ROOT/'outputs');p.add_argument('--period-start',default='2026-07-01');p.add_argument('--period-end',default='2026-07-31')
    a=p.parse_args();r=run(a.data,a.out,a.period_start,a.period_end)
    print(json.dumps({'elapsed_seconds':r['elapsed_seconds'],'summary':r['summary']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
