import inspect


def test_llm_prompt_contracts_require_content_only_output():
    from YSimulator.YClient.LLM_interactions import llm_service, vllm_service

    llm_source = inspect.getsource(llm_service)
    vllm_source = inspect.getsource(vllm_service)

    assert "Return only the final comment text." in llm_source
    assert "Return only the final share commentary text." in llm_source
    assert "Write a single natural comment" in llm_source
    assert "Do not explain, summarize, quote the prompt, add preambles, or wrap it in markdown." in llm_source

    assert "Return only the final comment text." in vllm_source
    assert "Return only the final share commentary text." in vllm_source
    assert "Do not add explanations, " in vllm_source
    assert "examples, quotations, labels, or formatting." in vllm_source
