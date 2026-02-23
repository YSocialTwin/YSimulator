from YSimulator.YClient.LLM_interactions.llm_service import LLMService
from YSimulator.YClient.LLM_interactions.vllm_service import VLLMService


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


def test_sanitize_absorb_triplets_accepts_list_of_dict_triplets():
    payload = [
        {"source": "NewsPage", "relation": "announces", "target": "new model"},
        {"subject": "Policy", "predicate": "affects", "object": "startups"},
    ]
    out = LLMService._sanitize_absorb_triplets(payload)
    assert ["NewsPage", "announces", "new model"] in out
    assert ["Policy", "affects", "startups"] in out


def test_sanitize_reflection_triplets_accepts_alternative_section_names():
    payload = {"my_reaction": [{"predicate": "support", "object": "open science", "score": 0.8}]}
    out = LLMService._sanitize_reflection_triplets(payload)
    assert out == [["support", "open science", 0.8]]


def test_safe_template_format_preserves_literal_json_braces():
    template = (
        "Analyze {text} by {author}.\n"
        "Return JSON: { \"world_facts\": [{\"source\":\"X\",\"relation\":\"r\",\"target\":\"Y\"}] }"
    )
    rendered = LLMService._safe_format_template(
        template, {"text": "sample", "author": "peer"}
    )
    assert "sample" in rendered
    assert "peer" in rendered
    assert "\"world_facts\"" in rendered


def test_safe_template_format_vllm_preserves_literal_json_braces():
    template = (
        "Analyze {text}.\n"
        "Return JSON: { \"my_expressed_stances\": [{\"relation\":\"r\",\"target\":\"t\"}] }"
    )
    rendered = VLLMService._safe_format_template(template, {"text": "hello"})
    assert "hello" in rendered
    assert "\"my_expressed_stances\"" in rendered


def test_sanitize_absorb_triplets_vllm_accepts_list_of_dict_triplets():
    payload = [
        {"source": "Researcher", "relation": "reports", "target": "benchmark gains"},
        {"subject": "Model", "predicate": "outperforms", "object": "baseline"},
    ]
    out = VLLMService._sanitize_absorb_triplets(payload)
    assert ["Researcher", "reports", "benchmark gains"] in out
    assert ["Model", "outperforms", "baseline"] in out
