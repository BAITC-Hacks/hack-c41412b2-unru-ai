"""Read-only access to explicitly recorded live AI demo results; never calls an LLM."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'audit/phase5_live_verification.json'
MANIFEST = ROOT / 'audit/ai_archive_manifest.json'


def read_archive(store):
    try:
        manifest = json.loads(MANIFEST.read_text())
        raw = SOURCE.read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest['source_sha256']:
            return {'available':False,'message':'Архив изменён: контрольная сумма не совпадает. Ответы не показаны.'}
        rows = json.loads(raw)
        records = []
        for index, row in enumerate(rows):
            result = row['events'][-1]
            if result['type'] != 'result': continue
            records.append({'id':str(index+1),'gid':row['gid'],'compare_gid':row['compare_gid'],
                            'question':row['question'],'result':result,
                            'activity':[e['message'] for e in row['events'] if e['type']=='activity']})
        match = manifest['input_sha256'] == store.report['input_sha256']
        match = match and all(hashlib.sha256((store.out/name).read_bytes()).hexdigest()==sha
                             for name,sha in manifest['calculation_sha256'].items())
        return {'available':True,'mode':'recorded_real_api_results','current_data_matches':match,
                'manifest':manifest,'records':records}
    except (OSError,ValueError,KeyError,TypeError):
        return {'available':False,'message':'Сохранённые результаты AI недоступны. Основная аналитика работает.'}
