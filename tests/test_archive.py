import json
from fastapi.testclient import TestClient
from moneygraph.server import create_app
from moneygraph.analyst import Analyst
from moneygraph import archive


def test_archive_without_key_is_real_saved_result_and_read_only():
    app=create_app();app.state.analyst=Analyst(app.state.store,settings=lambda:('','test'))
    client=TestClient(app);data=client.get('/api/analyst/archive').json()
    assert data['available'] and data['current_data_matches']
    assert data['mode']=='recorded_real_api_results' and len(data['records'])==6
    original=json.loads(archive.SOURCE.read_text())
    for row,record in zip(original,data['records']):
        assert record['result']==row['events'][-1]
        assert isinstance(record['gid'],str)
    assert client.get('/ai-archive').status_code==200
    assert client.get('/api/analyst/archive/download').content==archive.SOURCE.read_bytes()
    assert client.get('/api/analyst/status').json()['available'] is False


def test_changed_inputs_flag_historical_record():
    app=create_app();app.state.store.report['input_sha256']['nodes.parquet']='changed'
    result=archive.read_archive(app.state.store)
    assert result['available'] and not result['current_data_matches']


def test_missing_or_corrupt_archive_does_not_break_core(tmp_path,monkeypatch):
    app=create_app();path=tmp_path/'archive.json';monkeypatch.setattr(archive,'SOURCE',path)
    assert not archive.read_archive(app.state.store)['available']
    path.write_text('[]')
    assert not archive.read_archive(app.state.store)['available']
    assert TestClient(app).get('/api/summary').status_code==200
