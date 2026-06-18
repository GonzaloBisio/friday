"""Tests para friday.storage.chat_repo — ChatRepository."""

import pytest

from friday.storage.chat_repo import ChatMessage, ChatRepository
from friday.storage.db import get_connection


@pytest.fixture()
def repo():
    conn = get_connection(":memory:")
    yield ChatRepository(conn)
    conn.close()


class TestChatRepository:
    def test_create_session_returns_id(self, repo):
        sid = repo.create_session("Test session")
        assert len(sid) == 16
        sessions = repo.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["title"] == "Test session"

    def test_save_and_load_messages(self, repo):
        sid = repo.create_session()
        msg = ChatMessage(session_id=sid, role="user", content="Hola")
        mid = repo.save_message(msg)
        assert mid is not None

        msgs = repo.load_session(sid)
        assert len(msgs) == 1
        assert msgs[0].role == "user"
        assert msgs[0].content == "Hola"

    def test_save_many_messages(self, repo):
        sid = repo.create_session()
        msgs = [
            ChatMessage(session_id=sid, role="user", content="q1"),
            ChatMessage(session_id=sid, role="assistant", content="a1"),
            ChatMessage(session_id=sid, role="user", content="q2"),
        ]
        count = repo.save_messages(msgs)
        assert count == 3
        assert repo.count_messages(sid) == 3

    def test_load_session_ordered_by_time(self, repo):
        sid = repo.create_session()
        repo.save_message(ChatMessage(session_id=sid, role="user", content="first"))
        repo.save_message(ChatMessage(session_id=sid, role="assistant", content="second"))
        msgs = repo.load_session(sid)
        assert msgs[0].content == "first"
        assert msgs[1].content == "second"

    def test_empty_session_loads_empty(self, repo):
        sid = repo.create_session()
        msgs = repo.load_session(sid)
        assert msgs == []

    def test_list_sessions_returns_recent_first(self, repo):
        s1 = repo.create_session("older")
        s2 = repo.create_session("newer")
        sessions = repo.list_sessions()
        assert sessions[0]["id"] == s2
        assert sessions[1]["id"] == s1

    def test_count_messages(self, repo):
        sid = repo.create_session()
        assert repo.count_messages(sid) == 0
        repo.save_message(ChatMessage(session_id=sid, role="user", content="test"))
        assert repo.count_messages(sid) == 1

    def test_message_has_model_and_tokens(self, repo):
        sid = repo.create_session()
        msg = ChatMessage(
            session_id=sid, role="assistant", content="respuesta",
            model="gemini-2.5-flash", tokens_in=100, tokens_out=50,
        )
        repo.save_message(msg)
        msgs = repo.load_session(sid)
        assert msgs[0].model == "gemini-2.5-flash"
        assert msgs[0].tokens_in == 100
        assert msgs[0].tokens_out == 50
