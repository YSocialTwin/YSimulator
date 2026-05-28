from YSimulator.YClient.LLM_interactions.llm_service import (
    _append_custom_features_to_persona as append_ollama_persona,
)
from YSimulator.YClient.LLM_interactions.vllm_service import (
    _append_custom_features_to_persona as append_vllm_persona,
)


def test_ollama_persona_appends_custom_features():
    persona = append_ollama_persona(
        "You are a social media user.",
        {"custom_features": {"Class": "Mage", "Guild": "North"}},
    )

    assert "Additional personal details:" in persona
    assert "Class: Mage" in persona
    assert "Guild: North" in persona


def test_vllm_persona_appends_custom_features():
    persona = append_vllm_persona(
        "You are a social media user.",
        {"custom_features": {"Class": "Mage", "Guild": "North"}},
    )

    assert "Additional personal details:" in persona
    assert "Class: Mage" in persona
    assert "Guild: North" in persona


def test_persona_helpers_leave_plain_persona_unchanged():
    plain = "You are a social media user."

    assert append_ollama_persona(plain, {}) == plain
    assert append_vllm_persona(plain, None) == plain
