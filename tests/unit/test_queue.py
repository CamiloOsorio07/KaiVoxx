import pytest
from domain.repositories.queue_repository import MusicQueue
from domain.entities.song import Song

def test_enqueue_and_dequeue():
    q = MusicQueue(limit=2)
    s1 = Song("u1", "t1", "r1", None)
    s2 = Song("u2", "t2", "r2", None)
    assert q.enqueue(s1) is True
    assert q.enqueue(s2) is True
    assert len(q) == 2
    assert q.enqueue(Song("u3","t3","r3",None)) is False
    out = q.dequeue()
    assert out.title == "t1"
    assert len(q) == 1
    q.clear()
    assert len(q) == 0

def test_list_titles_empty():
    q = MusicQueue()
    assert q.list_titles() == []
