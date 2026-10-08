"""Local research orchestration with explicit inference consent and safe fallback."""
from collections import OrderedDict
from copy import deepcopy
import hashlib
import json
import re
from threading import RLock
from time import monotonic
from uuid import uuid4
from .task_navigation import resolve_research_plan
from .research_retrieval import retrieve_research_evidence
from .research_context import load_research_metrics, build_evidence_pack, _read
from .research_types import ResearchContext, EvidenceItem
from .research_validation import compose_local_reply
from .openrouter_live import OpenRouterError


class ResearchService:
    def __init__(self, root, index, store, adapter_factory, *, known_tickers=None, clock=monotonic):
        self.root, self.index, self.store, self.adapter_factory = root, index, store, adapter_factory
        self.known_tickers = known_tickers or sorted({r['ticker'] for r in index.as_records() if r['ticker']})
        self.clock = clock
        self.lock = RLock()
        self.turns = OrderedDict()
        self.cooldown_until = 0
        self.last_model_status = {'status': 'NOT_TESTED'}

    def targets(self):
        rows = _read(self.root / 'docs/prototypes/market-overview-data.json').get('sectorHeatmap', {}).get('sectors', [])
        sectors = [{'value': r['sector'], 'members': sorted(set(r.get('member_tickers', [])) & set(self.known_tickers))}
                   for r in rows if isinstance(r, dict) and isinstance(r.get('sector'), str)]
        return {'tickers': self.known_tickers, 'sectors': [r for r in sectors if r['members']]}

    def answer(self, session_id, expected_revision, query, use_model, artifact_refs, *, request_id=None, target=None, attachment_ids=None, share_attachments=False, on_event=None):
        """Answer one turn; on_event(name, data) streams validated model blocks when the model is used."""
        if not isinstance(query, str) or not 1 <= len(query.strip()) <= 4000 or not isinstance(use_model, bool):
            raise ValueError('INVALID_QUERY')
        if not isinstance(expected_revision, int) or isinstance(expected_revision, bool) or expected_revision < 0:
            raise ValueError('INVALID_REVISION')
        if not isinstance(artifact_refs, list) or len(artifact_refs) > 10 or any(not isinstance(r, str) for r in artifact_refs):
            raise ValueError('INVALID_ARTIFACT_REFS')
        if request_id is not None and (not isinstance(request_id, str) or not re.fullmatch(r'[\w-]{1,80}', request_id)):
            raise ValueError('INVALID_REQUEST_ID')
        query = query.strip()
        attachment_ids = [] if attachment_ids is None else attachment_ids
        if not isinstance(share_attachments, bool) or not isinstance(attachment_ids, list) or len(attachment_ids) > 5 or any(not isinstance(i, str) for i in attachment_ids):
            raise ValueError('INVALID_ATTACHMENTS')
        request_id = request_id or str(uuid4())
        selected = None
        if target is not None:
            if not isinstance(target, dict) or set(target) != {'kind', 'value'} or not isinstance(target['value'], str):
                raise ValueError('INVALID_TARGET')
            if target['kind'] == 'issuer' and target['value'] in self.known_tickers:
                selected = ResearchContext(entities=[target['value']], scope='issuer')
            elif target['kind'] == 'sector':
                members = next((r['members'] for r in self.targets()['sectors'] if r['value'] == target['value']), [])
                if not members or len(members) > 64:
                    raise ValueError('TARGET_UNAVAILABLE_OR_TOO_BROAD')
                selected = ResearchContext(entities=members, scope='sector', assumptions=['Sektor: ' + target['value'] + '; keanggotaan snapshot lokal, bukan universe historis.'])
            else:
                raise ValueError('INVALID_TARGET')
        fingerprint = hashlib.sha256(json.dumps([query, use_model, artifact_refs, target, attachment_ids, share_attachments]).encode()).hexdigest()
        key = (session_id, request_id)
        with self.lock:
            session = self.store.get(session_id)
            attachments = [a for a in session.attachments if a['id'] in attachment_ids]
            if set(attachment_ids) != {a['id'] for a in attachments}:
                raise ValueError('UNKNOWN_ATTACHMENT')
            if key in self.turns:
                record = self.turns[key]
                if record['fingerprint'] != fingerprint:
                    raise ValueError('REQUEST_ID_REUSED')
                if record['result'] is None:
                    raise ValueError('REQUEST_PENDING')
                return deepcopy(record['result'])
            planning_context = deepcopy(selected or session.context)
            planning_context.entities = planning_context.entities[:10]
            plan = resolve_research_plan(query, planning_context, self.known_tickers)
            if selected:
                explicit = resolve_research_plan(query, None, self.known_tickers).context.entities
                if explicit and not set(explicit).issubset(set(selected.entities)):
                    raise ValueError('TARGET_QUERY_CONFLICT')
                plan.context.entities = selected.entities.copy()
                plan.context.scope = selected.scope
                plan.context.assumptions = selected.assumptions.copy()
            metrics = load_research_metrics(self.root, plan, artifact_refs)
            plan.context.artifact_refs = artifact_refs.copy()
            request_id, revision = self.store.begin_turn(session_id, query, expected_revision, plan.context, request_id=request_id)
            self.turns[key] = {'fingerprint': fingerprint, 'result': None}
            while len(self.turns) > 64 * 40:
                self.turns.popitem(last=False)
        try:
            items = [] if plan.clarification else retrieve_research_evidence(self.root, self.index, plan)
        except Exception:
            # Retire failed turns rather than leaving a permanently pending session.
            with self.lock:
                try:
                    self.store.cancel_turn(session_id, revision)
                except (ValueError, KeyError):
                    pass
                self.turns.pop(key, None)
            raise ValueError('LOCAL_RETRIEVAL_FAILED') from None
        uploaded = [EvidenceItem(a['id'], 'user-upload:' + a['sha256'], 'user_owned_research', a['name'],
                    a['text'][:1200], plan.context.entities.copy(), plan.context.topic, source_hash=a['sha256'],
                    access_class='public' if use_model and share_attachments else 'private',
                    limits=['Source uploaded by user; not verified Sectors data.', a['notice']]) for a in attachments if a['text']]
        pack = build_evidence_pack(uploaded + items, metrics)
        pack.missing_inputs.extend(a['name'] + ': ' + a['notice'] for a in attachments if not a['text'])
        reply = compose_local_reply(plan, pack)
        if use_model and not plan.clarification:
            if self.clock() < self.cooldown_until:
                reply.model_status = {'provider': 'local', 'status': 'COOLDOWN', 'retry_after': max(1, int(self.cooldown_until - self.clock()))}
            elif not pack.metrics and not any(i.access_class == 'public' for i in pack.items):
                reply.model_status = {'provider': 'local', 'status': 'NO_PUBLIC_EVIDENCE'}
            else:
                history = []
                for m in session.messages:
                    if m['role'] == 'user':
                        history.append({'role': 'user', 'content': m['content']})
                    elif m.get('reply', {}).get('model_status', {}).get('provider') == 'OpenRouter':
                        history.append({'role': 'assistant', 'source_model': 'OpenRouter', 'content': '\n'.join(b['text'] for b in m['reply']['blocks'])})
                try:
                    adapter = self.adapter_factory()
                    # Only streaming callers pass on_event, so non-streaming adapters keep the 4-argument contract.
                    reply =adapter.compose_chat(query, plan.context, pack, history, on_event=on_event) if on_event else adapter.compose_chat(query, plan.context, pack, history)
                except OpenRouterError as exc:
                    status = 'RATE_LIMIT' if exc.status_code == 429 else 'AUTH' if exc.status_code in {401, 403} else 'CREDIT' if exc.status_code == 402 else 'UNAVAILABLE'
                    reply.model_status = {'provider': 'local', 'status': status, 'notice': str(exc), 'http_status': exc.status_code, 'retry_after': exc.retry_after, 'diagnostics': exc.diagnostics}
                    if exc.status_code == 429:
                        self.cooldown_until = self.clock() + (exc.retry_after or 30)
                except Exception:
                    reply = compose_local_reply(plan, pack)
                    reply.model_status = {'provider': 'local', 'status': 'UNAVAILABLE',
                                          'notice': 'Penyusunan jawaban model gagal; bukti lokal tetap tersedia.'}
        with self.lock:
            if not self.store.finish_turn(session_id, request_id, revision, reply):
                self.turns.pop(key, None)
                raise ValueError('STALE_RESPONSE')
            if use_model:
                self.last_model_status = reply.model_status.copy()
            result = {'session_id': session_id, 'request_id': request_id, 'revision': revision,
                      'reply': reply.to_dict(), 'history_truncated': self.store.get(session_id).history_truncated}
            self.turns[key]['result'] = deepcopy(result)
            return result

    def cancel(self, session_id, expected_revision):
        return {'revision': self.store.cancel_turn(session_id, expected_revision), 'status': 'CANCELLED'}
