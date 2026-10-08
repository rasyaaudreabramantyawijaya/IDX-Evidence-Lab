"""Fail-closed promotion from an inspectable local reference-test manifest."""
import hashlib
import json
from xml.etree import ElementTree


def verification_for(root,widget):
    try:
        manifest=json.loads((root/'reports/studies-reference-manifest.json').read_text())
        scope=manifest['widgets'].get(widget)
        if not scope or scope['passed_cases']!=scope['reference_cases'] or scope['reference_cases']<=0:
            return 'NOT_TESTED',None
        for name,digest in scope['source_hashes'].items():
            path=(root/name).resolve()
            if not path.is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
                return 'NOT_TESTED',None
        run=manifest['test_run'];path=(root/run['file']).resolve()
        if not path.is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=run['sha256']:
            return 'NOT_TESTED',None
        suites=ElementTree.fromstring(path.read_bytes()).iter('testsuite')
        counts=[(int(s.get('tests',0)),int(s.get('failures',0)),int(s.get('errors',0)),int(s.get('skipped',0))) for s in suites]
        if not counts or sum(c[0] for c in counts)!=run['passed_tests'] or any(any(c[1:]) for c in counts):
            return 'NOT_TESTED',None
        return 'REFERENCE_VERIFIED',{'reference_cases':scope['reference_cases'],'passed_cases':scope['passed_cases'],
                                    'scope':scope['scope'],'run':run['file']}
    except (OSError,ValueError,KeyError,TypeError,ElementTree.ParseError):
        return 'NOT_TESTED',None
