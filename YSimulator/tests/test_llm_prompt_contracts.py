import json
from pathlib import Path


def test_prompt_jsons_include_output_contracts():
    prompts_path = Path(
        "external/YSimulator/example/llm_population_100_vllm/prompts.json"
    )
    data = json.loads(prompts_path.read_text())

    comment_prompt = data["generate_comment"]["user_template"]
    share_prompt = data["generate_share_commentary"]["user_template"]
    news_prompt = data["generate_news_commentary"]["user_template"]

    assert "Return only the comment text." in comment_prompt
    assert "Do not explain, summarize, quote the prompt, add preambles, or wrap it in markdown." in comment_prompt

    assert "Return only the commentary text." in share_prompt
    assert "Do not explain, summarize, quote the prompt, add preambles, or wrap it in markdown." in share_prompt

    assert "Return only the tweet text." in news_prompt
    assert "Do not explain, summarize, quote the prompt, add preambles, or wrap it in markdown." in news_prompt
