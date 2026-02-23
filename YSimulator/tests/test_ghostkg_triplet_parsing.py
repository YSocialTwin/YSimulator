from YSimulator.YClient.LLM_interactions.llm_service import LLMService


def test_extract_json_block_handles_embedded_list_payload():
    raw = "model output: [{'source':'A','relation':'supports','target':'B'}]"
    payload = LLMService._extract_json_block(raw)
    if isinstance(payload, list):
        assert payload[0]["source"] == "A"
    else:
        assert payload["source"] == "A"


def test_sanitize_absorb_triplets_accepts_list_triplets():
    payload = [["Author", "supports", "AI"], ["Fact", "reduces", "costs"]]
    out = LLMService._sanitize_absorb_triplets(payload)
    assert ["Author", "supports", "AI"] in out
    assert ["Fact", "reduces", "costs"] in out


def test_sanitize_reflection_triplets_accepts_alternative_section_names():
    payload = {"my_reaction": [{"predicate": "support", "object": "open science", "score": 0.8}]}
    out = LLMService._sanitize_reflection_triplets(payload)
    assert out == [["support", "open science", 0.8]]
