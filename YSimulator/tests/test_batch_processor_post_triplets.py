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
            return [[["Peer", "supports", "content"]]]

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
    assert out == [[["Peer", "supports", "content"]]]
    assert actor.captured[0]["author"] == "peer_user"


def test_heuristic_fallback_generates_non_empty_triplets():
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
    absorb = bp._heuristic_absorb_triplets(
        "Sam Altman discusses energy demand at #Disrupt2026 conference", "author-1"
    )
    reflection = bp._heuristic_reflection_triplets(
        "I support open science and discuss energy policy #AI"
    )
    assert len(absorb) >= 1
    assert len(reflection) >= 1


def test_ground_absorb_triplets_drops_unrelated_prompt_example_triplets():
    input_triplets = [
        ["UBI", "reduces", "poverty"],
        ["NewsPage", "announces", "new model"],
    ]
    text = "NewsPage announces a new AI model for edge devices."
    grounded = BatchProcessor._ground_absorb_triplets(input_triplets, text, "NewsPage")
    assert ["NewsPage", "announces", "new model"] in grounded
    assert ["UBI", "reduces", "poverty"] not in grounded


def test_get_post_text_supports_text_and_tweet_keys():
    assert BatchProcessor._get_post_text({"text": "hello"}) == "hello"
    assert BatchProcessor._get_post_text({"tweet": "world"}) == "world"


def test_resolve_author_label_prefers_username_over_uuid(monkeypatch):
    class _Server:
        class _GetUser:
            @staticmethod
            def remote(user_id, client_id=None):
                return {"id": user_id, "username": "news_page"}

        get_user = _GetUser()

    bp = BatchProcessor(
        server=_Server(),
        client_id="c1",
        llm=object(),
        enable_sentiment=False,
        enable_toxicity=False,
        enable_emotions=False,
        perspective_api_key=None,
        logger=__import__("logging").getLogger("test"),
    )
    monkeypatch.setattr("YSimulator.YClient.simulation.batch_processor.ray.get", lambda x: x)
    author = bp._resolve_author_label({"user_id": "4ef8052b-608d-50f2-9785-91b2bce1d72a"})
    assert author == "news_page"


def test_normalize_absorb_triplet_entities_maps_self_and_uuid_target(monkeypatch):
    class _Server:
        class _GetUser:
            @staticmethod
            def remote(user_id, client_id=None):
                if user_id == "4ef8052b-608d-50f2-9785-91b2bce1d72a":
                    return {"id": user_id, "username": "target_user"}
                return {"id": user_id, "username": "unknown"}

        get_user = _GetUser()

    bp = BatchProcessor(
        server=_Server(),
        client_id="c1",
        llm=object(),
        enable_sentiment=False,
        enable_toxicity=False,
        enable_emotions=False,
        perspective_api_key=None,
        logger=__import__("logging").getLogger("test"),
    )
    monkeypatch.setattr("YSimulator.YClient.simulation.batch_processor.ray.get", lambda x: x)

    out = bp._normalize_absorb_triplet_entities(
        [["self", "mentions", "4ef8052b-608d-50f2-9785-91b2bce1d72a"]], "agent-1"
    )
    assert out == [["I", "mentions", "target_user"]]


def test_build_reaction_reflection_triplet_uses_reaction_as_relation():
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
    out = bp._build_reaction_reflection_triplets(
        reaction_type="LIKE",
        observed_content="This post discusses open-source AI tooling",
        target_post_id="p-1",
    )
    assert len(out) == 1
    assert out[0][0] == "LIKE"
    assert "open-source ai tooling" in out[0][1].lower()
