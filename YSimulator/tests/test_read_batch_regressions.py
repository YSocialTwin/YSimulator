from types import SimpleNamespace

from YSimulator.YClient.LLM_interactions.vllm_service import VLLMService


class _FakeOutput:
    def __init__(self, text):
        self.outputs = [SimpleNamespace(text=text)]


def test_generate_read_reaction_batch_uses_read_prompt_family():
    captured_prompts = []

    service = object.__new__(VLLMService.__ray_actor_class__)
    service.prompts_config = {
        "generate_read_reaction": {
            "system_template": "{persona} READ_ONLY_REACTIONS",
            "user_template": "READ_PROMPT::{post_content}",
        },
        "decide_reaction": {
            "system_template": "{persona} COMMENT_ALLOWED",
            "user_template": "DECIDE_PROMPT::{post_content}",
        },
    }
    service._build_persona = lambda cluster_id, agent_attrs=None: f"persona-{cluster_id}"
    service._format_prompt = (
        lambda system_msg, user_msg: captured_prompts.append((system_msg, user_msg))
        or f"{system_msg}\n{user_msg}"
    )
    service.sampling_params = object()
    service.llm = SimpleNamespace(
        generate=lambda prompts, sampling_params: [_FakeOutput("LIKE")] * len(prompts)
    )

    results = service.generate_read_reaction_batch(
        [{"cluster_id": 1, "post_content": "hello world", "agent_attrs": {}}]
    )

    assert results == ["LIKE"]
    assert captured_prompts, "Batch read path should build prompts"
    system_msg, user_msg = captured_prompts[0]
    assert "READ_ONLY_REACTIONS" in system_msg
    assert "READ_PROMPT::hello world" in user_msg
    assert "COMMENT_ALLOWED" not in system_msg
    assert "DECIDE_PROMPT::" not in user_msg
