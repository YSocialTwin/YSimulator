from YSimulator.YClient.simulation.batch_processor import BatchProcessor


def test_extract_selected_post_topics_collects_and_deduplicates():
    topics = BatchProcessor._extract_selected_post_topics(
        "AI",
        {
            "topic": "AI",
            "post_topics": ["Ethics", "AI", "Policy"],
        },
    )
    assert topics == ["AI", "Ethics", "Policy"]


def test_extract_selected_post_topics_skips_article_uuid():
    topics = BatchProcessor._extract_selected_post_topics(
        "4ef8052b-608d-50f2-9785-91b2bce1d72a",
        {"post_topics": ["Economy"]},
    )
    assert topics == ["Economy"]


def test_ensure_topic_subject_triplets_adds_missing_topic_subjects():
    triplets = [["I", "support", "AI"], ["Economy", "is", "volatile"]]
    selected_topics = ["AI", "Economy", "Policy"]

    enriched = BatchProcessor._ensure_topic_subject_triplets(triplets, selected_topics)
    sources = {row[0] for row in enriched}

    assert "AI" in sources
    assert "Economy" in sources
    assert "Policy" in sources


def test_filter_absorb_triplets_for_peer_removes_i_subject():
    input_triplets = [
        ["I", "support", "X"],
        ["Author", "claims", "Y"],
        ["Topic", "is_expressed_in", "text"],
    ]
    filtered = BatchProcessor._filter_absorb_triplets_for_author(
        input_triplets, agent_id="agent-1", author="Author"
    )
    assert ["I", "support", "X"] not in filtered
    assert ["Author", "claims", "Y"] in filtered
    assert ["Topic", "is_expressed_in", "text"] in filtered


def test_extract_absorb_triplets_batch_uses_request_author(monkeypatch):
    class _RemoteMethod:
        def __init__(self, fn):
            self._fn = fn

        def remote(self, *args, **kwargs):
            return self._fn(*args, **kwargs)

    class _Actor:
        def __init__(self):
            self.captured = None
            self.extract_ghostkg_absorb_triplets_batch = _RemoteMethod(self._batch)

        def _batch(self, payload):
            self.captured = payload
            return [[["Peer", "supports", "topic"]]]

    actor = _Actor()
    bp = BatchProcessor(
        server=None,
        client_id="c1",
        llm=object(),
        enable_sentiment=False,
        enable_toxicity=False,
        enable_emotions=False,
        perspective_api_key=None,
        logger=__import__("logging").getLogger("test"),
    )
    bp._get_llm_actor = lambda agent_id=None: actor
    monkeypatch.setattr("YSimulator.YClient.simulation.batch_processor.ray.get", lambda x: x)

    out = bp._extract_absorb_triplets_batch(
        [{"agent_id": "agent-1", "author": "peer_user", "text": "Some content"}]
    )
    assert out == [[["Peer", "supports", "topic"]]]
    assert actor.captured[0]["author"] == "peer_user"
