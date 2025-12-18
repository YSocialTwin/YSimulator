import ray
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

SERVER_URL = "http://127.0.0.1:5000"
OLLAMA_MODEL = "llama3.2"


@ray.remote(num_gpus=0.25)
class LLMService:
    def __init__(self):
        self.llm = ChatOllama(model=OLLAMA_MODEL, temperature=0.7)

    def generate_broadcast(self, iteration: int):
        """
        Specialized generation for Broadcasters only.
        """
        system_role = "You are a 'Broadcaster' influencer. High energy, use emojis, controversial."
        task_desc = f"Write a viral tweet about a new tech trend in iteration {iteration}."

        chain = (
                ChatPromptTemplate.from_messages([("system", system_role), ("user", task_desc)])
                | self.llm
                | StrOutputParser()
        )
        return chain.invoke({"iteration": iteration})

    def evaluate_content(self, post_content: str) -> str:
        """
        Analyzes text and returns 'LIKE', 'DISLIKE', or 'IGNORE'.
        """
        system_role = (
            "You are a critical social media user. "
            "Read the post and decide whether to LIKE, DISLIKE, or IGNORE it. "
            "Reply ONLY with one of those three words."
        )
        # We assume the broadcaster dislikes boring or 'validated' content
        chain = (
                ChatPromptTemplate.from_messages([("system", system_role), ("user", post_content)])
                | self.llm
                | StrOutputParser()
        )

        # Clean up response to ensure it matches our expected keywords
        decision = chain.invoke({}).strip().upper()
        if "LIKE" in decision: return "like"
        if "DISLIKE" in decision: return "dislike"
        return "ignore"