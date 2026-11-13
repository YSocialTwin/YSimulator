"""P13: with crosspost.content including "news" the content of a post about an article carries the article link."""

import uuid

import pytest

pytest.importorskip("ysocial_federation", reason="the federation SDK is not installed")

from sqlalchemy.orm import Session  # noqa: E402
from tests.test_federation_bus import ROUND, U, adapter_for, host, new_post  # noqa: E402,F401

from YSimulator.YServer.classes.models import Article, Post  # noqa: E402


def _content(host, policy):  # noqa: F811
    a = adapter_for(host, crosspost_content=policy)
    plain = new_post(host, 1, "no article")
    nid, pid = str(uuid.uuid4()), str(uuid.uuid4())
    with Session(host.engine) as s:
        s.add(
            Article(
                id=nid,
                title="t",
                summary="s",
                website_id="w",
                fetched_on="0",
                link="https://example.org/story",
            )
        )
        s.add(
            Post(
                id=pid,
                tweet="headline without url",
                user_id=U[1],
                comment_to="-1",
                thread_id=pid,
                round=ROUND,
                news_id=nid,
            )
        )
        s.commit()
        return a._content(s, s.get(Post, pid)), a._content(s, s.get(Post, plain))


def test_the_link_travels_only_when_the_policy_asks_for_news(host):  # noqa: F811
    news, plain = _content(host, ["news"])
    assert news["link"] == "https://example.org/story" and "link" not in plain


@pytest.mark.parametrize("policy", [None, ["all"], ["images"], ["own_content"]])
def test_without_news_the_message_is_unchanged(host, policy):  # noqa: F811
    news, plain = _content(host, policy)
    assert "link" not in news and "link" not in plain


def test_an_invalid_policy_is_refused(host):  # noqa: F811
    with pytest.raises(ValueError):
        adapter_for(host, crosspost_content=["video"])
