"""Last-hop diversity of external seed reach; not disjoint paths or money tracing."""
import math
from collections import Counter


def calculate(graph, seeds):
    seeds = set(seeds)
    if not seeds <= set(graph):
        raise ValueError('Seed missing from graph')
    predecessors = {v: tuple(sorted(graph.predecessors(v))) for v in graph}
    result = {}
    for target in sorted(graph):
        branches = {}
        for predecessor in predecessors[target]:
            # Reverse traversal in G minus target. A return cycle is not a new arrival.
            seen, pending = {target}, [predecessor]
            reached = set()
            while pending:
                node = pending.pop()
                if node in seen:
                    continue
                seen.add(node)
                if node in seeds:
                    reached.add(node)
                pending.extend(p for p in predecessors[node] if p not in seen)
            if reached:
                branches[predecessor] = reached
        multiplicity = Counter(seed for reached in branches.values() for seed in reached)
        masses = {p: math.fsum(1 / multiplicity[s] for s in sorted(reached))
                  for p, reached in branches.items()}
        total = math.fsum(masses.values())
        shares = {p: mass / total for p, mass in masses.items()} if total else {}
        effective = math.exp(-math.fsum(q * math.log(q) for q in shares.values())) if shares else 0.0
        result[str(target)] = {
            'external_seed_count': len(multiplicity),
            'self_seed_excluded': target in seeds,
            'last_hop_effective_branches': effective,
            'supported_predecessor_count': len(branches),
            'branches': [{'predecessor_gid': str(p), 'seed_count': len(branches[p]),
                          'seed_credit_mass': masses[p], 'share': shares[p]} for p in branches],
        }
    return result


def build(graph, frame):
    values = calculate(graph, frame.index[frame.is_seed])
    return {'schema_version': 1,
            'scope': 'External seed credits split over last-hop predecessors reachable without the target. Not independent paths; no missing paths inferred.',
            'nodes': [{'gid': str(r.Index), 'seed_convergence': {
                'reachable_seed_count': int(r.reachable_seed_count), **values[str(r.Index)]}}
                for r in frame.sort_index().itertuples()]}
