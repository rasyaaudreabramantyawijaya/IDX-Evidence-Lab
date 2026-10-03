import ast
import json
from pathlib import Path


def test_validation_notebook_is_visible_portable_and_compiles():
    path=Path(__file__).resolve().parents[1]/'notebooks/studies-calculation-validation.ipynb'
    assert path.is_file()
    book=json.loads(path.read_text())
    headings=[c for c in book['cells'] if c['cell_type']=='markdown']
    assert len(headings)==16
    for cell in book['cells']:
        if cell['cell_type']=='code':
            source=''.join(cell['source']);ast.parse(source)
            assert cell['execution_count'] is None
            assert 'requests.post' not in source and 'urlopen(' not in source
    full=''.join(''.join(c['source']) for c in book['cells'])
    assert 'STUDIES_PROJECT_ROOT' in full
    assert '1.4826' in full and '1e-10' in full and '1e-8' in full
    assert 'reference_correctness' in full and 'issuer_coverage' in full
