"""Bounded local sessions; revisions prevent stale replies from committing."""
from copy import deepcopy
from dataclasses import dataclass, field
from threading import RLock
from time import monotonic
from uuid import uuid4
from .research_types import ResearchContext


@dataclass
class Session:
    id: str
    revision: int = 0
    context: ResearchContext = field(default_factory=ResearchContext)
    messages: list[dict] = field(default_factory=list)
    pending_request_id: str | None = None
    history_truncated: bool = False
    touched: float = 0
    attachments: list[dict] = field(default_factory=list)


class ResearchSessionStore:
    def __init__(self, max_sessions=64, ttl_seconds=3600, max_messages=40, *, clock=monotonic):
        if min(max_sessions, ttl_seconds, max_messages) <= 0:
            raise ValueError('Session bounds must be positive')
        self.max_sessions, self.ttl_seconds, self.max_messages = max_sessions, ttl_seconds, max_messages
        self.clock = clock
        self.lock = RLock()
        self.sessions = {}

    def _expire(self):
        now = self.clock()
        for key in list(self.sessions):
            if now - self.sessions[key].touched >= self.ttl_seconds:
                del self.sessions[key]

    def _current(self, id):
        self._expire()
        session = self.sessions[id]
        session.touched = self.clock()
        return session

    def _append(self, session, message):
        session.messages.append(message)
        if len(session.messages) > self.max_messages:
            session.messages = session.messages[-self.max_messages:]
            session.history_truncated = True

    def create(self):
        with self.lock:
            self._expire()
            if len(self.sessions) >= self.max_sessions:
                del self.sessions[min(self.sessions, key=lambda id: self.sessions[id].touched)]
            session = Session(str(uuid4()), touched=self.clock())
            self.sessions[session.id] = session
            return deepcopy(session)

    def get(self, session_id):
        with self.lock:
            return deepcopy(self._current(session_id))

    def add_attachment(self, session_id, value):
        with self.lock:
            session = self._current(session_id)
            if session.pending_request_id:
                raise ValueError('REQUEST_PENDING')
            if any(a['id'] == value['id'] for a in session.attachments):
                return deepcopy(value)
            if len(session.attachments) >= 5:
                raise ValueError('ATTACHMENT_LIMIT')
            session.attachments.append(deepcopy(value))
            return deepcopy(value)

    def remove_attachment(self, session_id, attachment_id):
        if not isinstance(attachment_id, str):
            raise ValueError('INVALID_ATTACHMENT')
        with self.lock:
            session = self._current(session_id)
            if session.pending_request_id:
                raise ValueError('REQUEST_PENDING')
            session.attachments = [a for a in session.attachments if a['id'] != attachment_id]

    def begin_turn(self, session_id, query, expected_revision, context, *, request_id=None):
        with self.lock:
            session = self._current(session_id)
            if session.revision != expected_revision:
                raise ValueError('REVISION_CONFLICT')
            session.revision += 1
            session.pending_request_id = request_id or str(uuid4())
            session.context = deepcopy(context)
            self._append(session, {'role': 'user', 'content': query, 'context': context.to_dict()})
            return session.pending_request_id, session.revision

    def finish_turn(self, session_id, request_id, revision, reply):
        with self.lock:
            try:
                session = self._current(session_id)
            except KeyError:
                return False
            if session.revision != revision or session.pending_request_id != request_id:
                return False
            value = reply.to_dict() if hasattr(reply, 'to_dict') else deepcopy(reply)
            self._append(session, {'role': 'assistant', 'reply': value, 'context': session.context.to_dict()})
            session.pending_request_id = None
            return True

    def cancel_turn(self, session_id, expected_revision):
        with self.lock:
            session = self._current(session_id)
            if session.revision != expected_revision:
                raise ValueError('REVISION_CONFLICT')
            session.revision += 1
            session.pending_request_id = None
            return session.revision
