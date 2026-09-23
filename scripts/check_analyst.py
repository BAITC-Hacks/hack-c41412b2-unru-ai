"""Explicit opt-in live API evaluation. Sends bounded tool results; never logs keys."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from moneygraph.analyst import Analyst, ToolLayer
from moneygraph.server import Store
from moneygraph.pipeline import ROOT, DEFAULT_DATA

QUESTIONS = [
 ('100000003115284100','Почему этот узел находится в INVESTIGATE NOW?',None),
 ('100000003684369100','Оспорь основную гипотезу по этому узлу. Какие факты против неё?',None),
 ('100000005523088100','Каких данных здесь не хватает и зачем их запрашивать?',None),
 ('100000003115284100','Почему этот узел выше или ниже другого? Укажи преимущество второго, если оно есть.','100000003684369100'),
 ('100000003016635100','Почему этот узел структурно важен?',None),
 ('100000003037476100','Это конечный получатель?',None),
]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true',help='Send questions and tool results to OpenAI using server-side key')
    parser.add_argument('--limit',type=int,default=6,choices=range(1,7))
    args=parser.parse_args();store=Store(DEFAULT_DATA,ROOT/'outputs')
    if not args.live:
        preview=[]
        for gid,q,other in QUESTIONS[:args.limit]:
            layer=ToolLayer(store,[gid]+([other] if other else []))
            preview.append({'gid':gid,'question':q,'compare_gid':other,
                'required_tool_data':layer.call('compare_nodes',{'gid_a':gid,'gid_b':other}) if other else
                {n:layer.call(n,{'gid':gid}) for n in ['get_node_profile','get_structural_evidence','get_data_gaps']}})
        print(json.dumps(preview,ensure_ascii=False,indent=2));return
    agent=Analyst(store);results=[]
    for gid,q,other in QUESTIONS[:args.limit]:
        events=list(agent.events(gid,q,other));results.append({'gid':gid,'question':q,'compare_gid':other,'events':events})
        (ROOT/'audit/phase5_live_verification.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
        final=events[-1];print(json.dumps({'gid':gid,'result':final},ensure_ascii=False),flush=True)
        if final['type']!='result':raise SystemExit(1)

if __name__=='__main__':main()
