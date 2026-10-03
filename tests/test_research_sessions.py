import importlib.util
from idx_evidence_lab.research_types import ResearchContext
import pytest


def store(**kwargs):
    assert importlib.util.find_spec('idx_evidence_lab.research_sessions'), 'Missing session store'
    from idx_evidence_lab.research_sessions import ResearchSessionStore
    return ResearchSessionStore(**kwargs)


def test_late_reply_cannot_overwrite_new_turn():
    s = store(); session = s.create()
    a, revision = s.begin_turn(session.id, 'BBCA', 0, ResearchContext(entities=['BBCA']))
    b, newer = s.begin_turn(session.id, 'TLKM', revision, ResearchContext(entities=['TLKM']))
    assert not s.finish_turn(session.id, a, revision, {'blocks': []})
    assert s.finish_turn(session.id, b, newer, {'blocks': []})
    assert s.get(session.id).context.entities == ['TLKM']


def test_two_sessions_do_not_share_context():
    s = store(); a = s.create(); b = s.create()
    s.begin_turn(a.id, 'BBCA', 0, ResearchContext(entities=['BBCA']))
    assert s.get(b.id).context.entities == []
    snapshot = s.get(a.id); snapshot.context.entities.clear()
    assert s.get(a.id).context.entities == ['BBCA']


def test_cancel_invalidates_pending_reply():
    s = store(); a = s.create()
    request, rev = s.begin_turn(a.id, 'x', 0, ResearchContext())
    assert s.cancel_turn(a.id, rev) == 2
    assert not s.finish_turn(a.id, request, rev, {})


def test_revision_conflict_keeps_existing_messages():
    s = store(); a = s.create()
    s.begin_turn(a.id, 'x', 0, ResearchContext())
    with pytest.raises(ValueError):
        s.begin_turn(a.id, 'duplicate', 0, ResearchContext())
    assert len(s.get(a.id).messages) == 1


def test_expired_session_requires_new_session():
    clock = [0]
    s = store(ttl_seconds=1, clock=lambda: clock[0]); a = s.create()
    clock[0] = 2
    with pytest.raises(KeyError):
        s.get(a.id)


def test_message_cap_reports_history_truncation():
    s = store(max_messages=2); a = s.create()
    for rev in range(3):
        s.begin_turn(a.id, str(rev), rev, ResearchContext())
    current = s.get(a.id)
    assert len(current.messages) == 2
    assert current.history_truncated


def test_session_capacity_is_bounded():
    s = store(max_sessions=1); first = s.create(); s.create()
    with pytest.raises(KeyError):
        s.get(first.id)
