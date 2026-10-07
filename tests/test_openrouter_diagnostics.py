"""Safe diagnostics must survive HTTP failures without disclosing raw content."""
import io
import json
from urllib.error import HTTPError
from unittest.mock import patch

import pytest

from idx_evidence_lab.openrouter_live import OpenRouterError, OpenRouterSearchAdapter


def reject(body, headers=None):
    error = HTTPError('https://openrouter.ai', 429, 'limit', headers or {},
                      io.BytesIO(json.dumps(body).encode()))
    with patch('idx_evidence_lab.openrouter_live.urlopen', side_effect=error):
        with pytest.raises(OpenRouterError) as caught:
            # One model: the single mocked HTTPError body can only be read once.
            OpenRouterSearchAdapter('test-key', fallback_models=()).interpret('analisa BBCA', ['BBCA'])
    return caught.value


def test_provider_diagnostics_survive_but_raw_and_message_do_not():
    error = reject({'error': {'message': 'PRIVATE_PROMPT sk-or-v1-secret', 'metadata': {
        'provider_name': 'ModelRun', 'error_type': 'rate_limit_exceeded',
        'limit_source': 'provider', 'raw': 'PRIVATE_DOCUMENT'}}}, {'Retry-After': '45'})
    assert error.diagnostics == {'provider_name': 'ModelRun',
                                 'error_type': 'rate_limit_exceeded', 'limit_source': 'provider'}
    assert error.retry_after == 45
    assert 'ModelRun' in str(error)
    assert 'PRIVATE' not in str(error) + json.dumps(error.diagnostics)
    assert 'sk-or-' not in str(error) + json.dumps(error.diagnostics)


def test_missing_metadata_does_not_guess_the_limit_source():
    error = reject({'error': {'message': 'Rate limited'}})
    assert error.diagnostics == {}
    assert error.retry_after is None


def test_untrusted_metadata_cannot_leak_keys_or_nested_objects():
    error = reject({'error': {'metadata': {
        'provider_name': 'sk-or-v1-secret', 'error_type': {'prompt': 'PRIVATE'},
        'limit_source': 'PRIVATE_UNKNOWN', 'raw': 'PRIVATE'}}})
    assert error.diagnostics == {}


def test_http_date_retry_after_is_respected():
    # Unix 0 is Thursday 1970-01-01 00:00:00 UTC; header is 60 seconds later.
    with patch('time.time', return_value=0):
        error = reject({}, {'Retry-After': 'Thu, 01 Jan 1970 00:01:00 GMT'})
    assert error.retry_after == 60
