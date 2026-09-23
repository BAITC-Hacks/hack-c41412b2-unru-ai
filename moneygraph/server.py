"""Local read-only investigator UI. Run python -m moneygraph.server."""
import argparse
import copy
import hashlib
import json
import time
from pathlib import Path
import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request
from pydantic import BaseModel, Field, ConfigDict
from .analyst import Analyst
from .archive import read_archive, SOURCE as ARCHIVE_SOURCE
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from .pipeline import ROOT, DEFAULT_DATA, run
from .observability import QUEUES

DOWNLOADS = {'nodes_roles.csv', 'clusters.csv', 'top_nodes.csv'}


class AnalystQuestion(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    gid: str = Field(pattern=r'^[0-9]{1,20}$')
    question: str = Field(min_length=1, max_length=1500)
    compare_gid: str | None = Field(default=None, pattern=r'^[0-9]{1,20}$')


class Store:
    def __init__(self, data, out):
        start = time.perf_counter()
        self.out = Path(out)
        self.report = json.loads((self.out / 'run_report.json').read_text())
        for name, sha in self.report['input_sha256'].items():
            if hashlib.sha256((Path(data) / name).read_bytes()).hexdigest() != sha:
                raise ValueError('Input/output mismatch; run pipeline for the selected data directory')
        frame = pd.read_csv(self.out / 'nodes_roles.csv', dtype={'gid': str})
        records = frame.astype(object).where(pd.notna(frame), None).to_dict('records')
        self.nodes = {r['gid']: r for r in records}
        context = json.loads((self.out / 'node_context.json').read_text())
        if set(self.nodes) != {r['gid'] for r in context['nodes']}:
            raise ValueError('CSV/context node coverage mismatch')
        for r in context['nodes']:
            node = self.nodes[r['gid']]
            # Internal JSON retains original precision; CSV carries human exports.
            node.update(r)
            for field in ['in_kzt', 'out_kzt', 'in_degree', 'out_degree', 'in_tx', 'out_tx', 'in_days', 'out_days',
                          'neighbor_count', 'pagerank', 'reachable_seed_count', 'observed_out_in_ratio']:
                node['metrics'][field] = node[field]
        evidence = json.loads((self.out / 'structural_evidence.json').read_text())
        if set(self.nodes) != {n['gid'] for n in evidence['nodes']}:
            raise ValueError('Structural evidence coverage mismatch; rerun pipeline')
        for record in evidence['nodes']:
            self.nodes[record['gid']].update(record)
        convergence = json.loads((self.out / 'seed_convergence.json').read_text())
        if set(self.nodes) != {n['gid'] for n in convergence['nodes']}:
            raise ValueError('Seed convergence coverage mismatch; rerun pipeline')
        for record in convergence['nodes']:
            self.nodes[record['gid']].update(record)
        self.stability_summary = {'available':False,'message':'Диагностика не рассчитана: python -m moneygraph.stability'}
        for node in self.nodes.values(): node['stability'] = None
        diagnostic_path = self.out / 'stability.json'
        if diagnostic_path.is_file():
            try:
                diagnostic = json.loads(diagnostic_path.read_text())
                valid = diagnostic['input_sha256'] == self.report['input_sha256']
                valid = valid and all(hashlib.sha256((self.out/name).read_bytes()).hexdigest()==sha for name,sha in diagnostic['calculation_sha256'].items())
                valid = valid and set(self.nodes)=={r['gid'] for r in diagnostic['nodes']}
                if valid:
                    for record in diagnostic['nodes']: self.nodes[record['gid']]['stability']=record
                    self.stability_summary={'available':True,'summary':diagnostic['summary'],'scope':diagnostic['scope'],'elapsed_seconds':diagnostic['elapsed_seconds']}
                else:
                    self.stability_summary={'available':False,'message':'Stability относится к другой версии данных/расчётов; пересчитайте диагностику.'}
            except (OSError,ValueError,KeyError,TypeError):
                self.stability_summary={'available':False,'message':'Файл Stability повреждён; основная аналитика доступна.'}
        self.edges, self.adj = [], {gid: set() for gid in self.nodes}
        for row in pd.read_parquet(Path(data) / 'edges.parquet').itertuples(index=False):
            edge = {'src': str(row.src), 'dst': str(row.dst), 'sum_kzt': float(row.sum_kzt), 'n_tx': int(row.n_tx)}
            self.edges.append(edge)
            self.adj[edge['src']].add(edge['dst']); self.adj[edge['dst']].add(edge['src'])
        self.clusters = {}
        for row in pd.read_csv(self.out / 'clusters.csv', dtype={'top_gids': str}).to_dict('records'):
            row['top_gids'] = row['top_gids'].split(';')
            row['top_nodes'] = [self.brief(self.nodes[gid]) for gid in row['top_gids']]
            self.clusters[row['cluster_id']] = row
        self.queue_lists = {q: sorted((r for r in self.nodes.values() if r['investigation_queue'] == q),
                                     key=lambda r: (-r['priority_score'], int(r['gid']))) for q in QUEUES}
        self.load_seconds = round(time.perf_counter() - start, 4)

    @staticmethod
    def brief(node):
        return {key: node[key] for key in ['gid', 'role', 'role_score', 'priority_score', 'observability_level',
                                           'investigation_queue', 'cluster_id', 'is_seed', 'depth']}

    def node(self, gid):
        if gid not in self.nodes:
            raise HTTPException(404, 'GID не найден в текущей выгрузке')
        return self.nodes[gid]


def create_app(data=DEFAULT_DATA, out=ROOT / 'outputs'):
    store = Store(data, out)
    app = FastAPI(title='MoneyGraph Investigator', version='0.3.0')
    app.state.store = store
    app.state.analyst = Analyst(store)

    @app.get('/ai-archive')
    def ai_archive_page():
        return FileResponse(ROOT / 'web/ai-archive.html')

    @app.get('/api/analyst/archive')
    def ai_archive():
        return read_archive(store)

    @app.get('/api/analyst/archive/download')
    def ai_archive_download():
        if not read_archive(store)['available']:
            raise HTTPException(404, 'Архив недоступен')
        return FileResponse(ARCHIVE_SOURCE, media_type='application/json', filename='recorded-real-ai-results.json')

    @app.get('/api/analyst/status')
    def analyst_status():
        return app.state.analyst.status()

    @app.post('/api/analyst/ask')
    def analyst_ask(body: AnalystQuestion, request: Request):
        origin = request.headers.get('origin')
        if origin and origin != str(request.base_url).rstrip('/'):
            raise HTTPException(403, 'Cross-origin AI requests are not allowed')
        store.node(body.gid)
        if body.compare_gid: store.node(body.compare_gid)
        def stream():
            for event in app.state.analyst.events(body.gid, body.question, body.compare_gid):
                yield json.dumps(event, ensure_ascii=False, allow_nan=False) + '\n'
        return StreamingResponse(stream(), media_type='application/x-ndjson', headers={'Cache-Control':'no-store'})


    @app.get('/api/stability/summary')
    def stability_summary():
        return store.stability_summary

    @app.get('/api/summary')
    def summary():
        r = store.report
        return {'total_nodes': r['nodes'], 'total_edges': r['edges'], 'total_transactions': r['transactions'],
                'n_clusters': r['clusters'], 'queue_counts': r['triage_summary']['queues'],
                'observability_counts': r['triage_summary']['observability'], 'total_observed_turnover': r['sum_kzt'],
                'pipeline_seconds': r['elapsed_seconds'], 'store_load_seconds': store.load_seconds,
                'period': 'Июль 2026', 'scope': 'Один банк · переводы от 5 000 KZT · исходящий обход до depth=4'}

    @app.get('/api/queues/{queue}')
    def queue(queue: str, offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=200)):
        if queue not in QUEUES:
            raise HTTPException(404, 'Неизвестная очередь')
        nodes = store.queue_lists[queue]
        return {'queue': queue, 'total': len(nodes), 'offset': offset, 'limit': limit,
                'items': [store.brief(n) for n in nodes[offset:offset + limit]]}

    @app.get('/api/search')
    def search(q: str = Query('', max_length=32), limit: int = Query(20, ge=1, le=100)):
        q = q.strip()
        if not q or not q.isascii() or not q.isdigit():
            return {'query': q, 'exact': False, 'total': 0, 'items': []}
        if q in store.nodes:
            return {'query': q, 'exact': True, 'total': 1, 'items': [store.brief(store.nodes[q])]}
        matches = sorted((gid for gid in store.nodes if gid.startswith(q)), key=int)
        return {'query': q, 'exact': False, 'total': len(matches), 'items': [store.brief(store.nodes[gid]) for gid in matches[:limit]]}

    @app.get('/api/nodes/{gid}')
    def node(gid: str):
        result = copy.deepcopy(store.node(gid))
        result['cluster'] = store.clusters[result['cluster_id']]
        return result

    @app.get('/api/nodes/{gid}/ego')
    def ego(gid: str, max_nodes: int = Query(160, ge=1, le=250)):
        store.node(gid)
        neighbors = sorted(store.adj[gid], key=lambda n: (-store.nodes[n]['priority_score'], int(n)))
        selected = [gid] + neighbors[:max_nodes - 1]
        included = set(selected)
        edges = [e for e in store.edges if (e['src'] == gid or e['dst'] == gid) and e['src'] in included and e['dst'] in included]
        return {'center_gid': gid, 'hops': 1, 'edge_scope': 'incident_to_selected_node',
                'nodes': [store.brief(store.nodes[n]) for n in selected], 'edges': edges,
                'total_neighbors': len(neighbors), 'omitted_neighbors': max(0, len(neighbors) - max_nodes + 1),
                'truncated': len(neighbors) + 1 > max_nodes, 'max_nodes': max_nodes}

    @app.get('/api/clusters/{cluster_id}')
    def cluster(cluster_id: int):
        if cluster_id not in store.clusters:
            raise HTTPException(404, 'Кластер не найден')
        return store.clusters[cluster_id]

    @app.get('/api/download/{filename}')
    def download(filename: str):
        if filename not in DOWNLOADS:
            raise HTTPException(404, 'Файл недоступен')
        return FileResponse(store.out / filename, media_type='text/csv', filename=filename)

    @app.get('/')
    def index():
        return FileResponse(ROOT / 'web/index.html')

    app.mount('/assets', StaticFiles(directory=ROOT / 'web'), name='assets')
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=DEFAULT_DATA)
    parser.add_argument('--out', type=Path, default=ROOT / 'outputs')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8010)
    args = parser.parse_args()
    start = time.perf_counter()
    run(args.data, args.out)
    app = create_app(args.data, args.out)
    print(f'Pipeline + UI store ready in {time.perf_counter() - start:.3f}s. http://{args.host}:{args.port}', flush=True)
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == '__main__':
    main()
