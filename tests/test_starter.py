import subprocess
import sys
import json
import hashlib
from pathlib import Path
from moneygraph.pipeline import ROOT


def test_starter_from_other_directory_generates_full_results(tmp_path):
    out=tmp_path/'results'
    result=subprocess.run([sys.executable,str(ROOT/'starter.py'),'--no-ui','--out',str(out)],cwd=tmp_path,capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
    for name,h in json.loads((ROOT/'tests/phase1_csv_sha256.json').read_text()).items():
        assert hashlib.sha256((out/name).read_bytes()).hexdigest()==h
    assert len(json.loads((out/'patterns.json').read_text())['nodes'])==2248
    assert len(json.loads((out/'stability.json').read_text())['nodes'])==2248
    assert 'Готово' in result.stdout
