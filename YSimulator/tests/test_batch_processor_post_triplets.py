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
