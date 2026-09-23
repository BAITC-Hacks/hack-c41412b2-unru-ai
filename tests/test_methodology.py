import copy
import hashlib
import re
from pathlib import Path
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from moneygraph import roles, observability
from moneygraph.methodology import breakdown, rule_specs
from moneygraph.server import create_app

@pytest.fixture(scope='module')
def app():
    return create_app()


def test_page_without_key_anchors_and_real_breakdown(app,monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    client=TestClient(app)
    page=client.get('/methodology?gid=100000008603629100')
    assert page.status_code==200
    for anchor in ['data','graph','metrics','roles','priority','clusters','observability','queues','dependency','convergence','stability','resilience','temporal','routes','anomalies','ai','limitations',*roles.ROLE_ORDER,'peripheral']:
        assert f'id="{anchor}"' in page.text
    assert page.text.count('class="method-section panel"')==17
    assert 'Выбранный узел: 100000008603629100' in page.text
    assert 'sk-proj-' not in page.text
    assert client.get('/methodology?gid=999').status_code==404
    assert client.get('/methodology?gid=<script>').status_code==422
    assert client.get('/methodology').status_code==200


def test_all_node_all_role_contributions_match_engine(app):
    assert set(rule_specs())==set(roles.ROLE_ORDER)
    for node in app.state.store.nodes.values():
        row = dict(node)
        if row['observed_out_in_ratio'] is None: row['observed_out_in_ratio'] = float('nan')
        expected=roles.classify_row(SimpleNamespace(**row))
        for name in roles.ROLE_ORDER:
            actual=breakdown(node,name)
            assert actual['score']==pytest.approx(expected[3][name],abs=1e-12)
        assert breakdown(node,node['role'])['score']==pytest.approx(node['role_score'],abs=1e-8)


def test_documentation_is_read_only_and_csv_unchanged(app):
    before=copy.deepcopy(app.state.store.nodes)
    hashes={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('outputs').glob('*.csv')}
    client=TestClient(app)
    for gid in list(app.state.store.nodes)[:3]:
        assert client.get('/methodology',params={'gid':gid}).status_code==200
    assert before==app.state.store.nodes
    assert hashes=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in hashes}


def test_queue_constants_appear_in_page(app):
    page=TestClient(app).get('/methodology').text
    assert f'приоритет &lt; {observability.PRIORITY_THRESHOLD}' in page
    assert f'достаточность ≥ {observability.ACCEPTABLE_OBSERVABILITY}' in page
    assert f'сила роли ≥ {observability.EVIDENCE_THRESHOLD}' in page


def test_explanatory_prose_review_guard():
    # A change to an algorithm requires explicit review of the associated prose.
    import json
    manifest=json.loads(Path('tests/methodology_source_hashes.json').read_text())
    for name, expected in manifest.items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==expected, f'Review methodology prose after changing {name}'


def test_navigation_and_deep_link():
    for name in ['index.html','ai-archive.html']:
        text=Path('web',name).read_text()
        assert 'href="/methodology"' in text
    assert '/methodology?gid=${encodeURIComponent(n.gid)}#${esc(n.primary_role)}' in Path('web/app.js').read_text()
