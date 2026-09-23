"""One command: raw parquet -> validated CSV, metrics and a reproducibility report."""
import argparse
import hashlib
import json
import platform
import tempfile
import time
from pathlib import Path
import networkx as nx
import pandas as pd
from . import communities, features, roles, observability, evidence, convergence
from .io import NODE_COLUMNS, load_data, validate_outputs

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA = ROOT / 'audit/source/data/data'


def run(data=DEFAULT_DATA, out=ROOT / 'outputs', top_n=50):
    start = time.perf_counter()
    nodes, edges, tx = load_data(data)
    graph, f = features.calculate(nodes, edges, tx)
    f = roles.assign(f)
    f, clusters = communities.assign(graph, f)
    node_output = f.reset_index()
    optional = [c for c in node_output.columns if c not in NODE_COLUMNS]
    node_output = node_output[NODE_COLUMNS + optional]
    top = node_output.sort_values(['priority_score', 'gid'], ascending=[False, True]).head(max(20, top_n))
    top = top[['gid', 'role', 'priority_score', 'priority_why']].rename(columns={'priority_why': 'why'}).reset_index(drop=True)
    top.insert(0, 'rank', range(1, len(top) + 1))
    validate_outputs(node_output, clusters, top, nodes.gid)
    context = observability.build_context(f)
    structural_evidence = evidence.build(graph, f)
    seed_convergence = convergence.build(graph, f)
    delta = f.out_tiyn - f.in_tiyn
    comparisons = {}
    for label, mask in [('all', pd.Series(True, index=f.index)), ('seed', f.is_seed), ('non_seed', ~f.is_seed),
                        ('positive_in', f.in_tiyn > 0), ('zero_in', f.in_tiyn == 0)]:
        comparisons[label] = {'out_gt_in': int(((delta > 0) & mask).sum()),
                              'out_gt_in_plus_one_tiyn': int(((delta > 1) & mask).sum())}
    edge_graph = graph.subgraph([gid for gid in graph if graph.degree(gid) > 0])
    report = {
        'nodes': len(nodes), 'edges': len(edges), 'transactions': len(tx), 'seed': int(nodes.is_seed.sum()),
        'sum_kzt': int(edges.sum_tiyn.sum()) / 100, 'duplicate_transaction_rows_retained': int(tx.duplicated(['src', 'dst', 'date', 'sum_kzt']).sum()),
        'weak_components_edge_graph': nx.number_weakly_connected_components(edge_graph),
        'weak_components_all_nodes': nx.number_weakly_connected_components(graph), 'isolated': int(f.isolated.sum()),
        'out_gt_in_audit': comparisons, 'role_counts': f.role.value_counts().to_dict(), 'clusters': len(clusters),
        'triage_summary': context['summary'],
        'boundary_terminal_count': int((f.boundary & f.role.eq('terminal')).sum()),
        'elapsed_seconds': round(time.perf_counter() - start, 4),
        'versions': {'python': platform.python_version(), 'pandas': pd.__version__, 'networkx': nx.__version__},
        'input_sha256': {name: hashlib.sha256((Path(data) / name).read_bytes()).hexdigest() for name in ['nodes.parquet', 'edges.parquet', 'transactions.parquet']},
        'interpretation': 'Roles are hypotheses; scores are evidence strength / review priority, never guilt probabilities. Observed flows are not balances.',
    }
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    # Validate before replacing outputs; never publish a half-written individual CSV.
    with tempfile.TemporaryDirectory(dir=out, prefix='.building-') as tmp:
        stage = Path(tmp)
        for name, frame in [('nodes_roles.csv', node_output), ('clusters.csv', clusters), ('top_nodes.csv', top)]:
            frame.to_csv(stage / name, index=False, float_format='%.10f')
        (stage / 'node_context.json').write_text(json.dumps(context, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
        (stage / 'structural_evidence.json').write_text(json.dumps(structural_evidence, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
        (stage / 'seed_convergence.json').write_text(json.dumps(seed_convergence, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
        report['elapsed_seconds'] = round(time.perf_counter() - start, 4)
        (stage / 'run_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        for file in stage.iterdir():
            file.replace(out / file.name)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=DEFAULT_DATA)
    parser.add_argument('--out', type=Path, default=ROOT / 'outputs')
    parser.add_argument('--top', type=int, default=50)
    args = parser.parse_args()
    print(json.dumps(run(args.data, args.out, args.top), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
