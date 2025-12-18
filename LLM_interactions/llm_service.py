import ray
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser


# Use standard Ray actor (CPU) - the GPU is managed by Ollama internally
@ray.remote
class LLMService:
    def __init__(self):
        # We assume Ollama is running at localhost:11434
        self.llm = ChatOllama(model="llama3.2", temperature=0.7)

    def generate_post(self, cluster_id: int, day: int, slot: int) -> str:
        """Generate content based on Persona."""
        if cluster_id == 1:
            persona = "You are a 'Broadcaster'. High energy, viral, controversial."
        elif cluster_id == 0:
            persona = "You are a 'Validator'. Skeptical, brief, authentic."
        else:
            persona = "You are an 'Explorer'. Curious, asking questions."

        prompt = ChatPromptTemplate.from_messages([
            ("system", persona),
            ("user", f"Write a tweet for Day {day} Slot {slot}. Max 15 words.")
        ])
        chain = prompt | self.llm | StrOutputParser()
        return chain.invoke({})

    def decide_reaction(self, cluster_id: int, post_content: str) -> str:
        """Decide: LIKE, COMMENT, or IGNORE."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", f"You are user type {cluster_id}. Read post. Reply ONLY: 'LIKE', 'COMMENT', 'IGNORE'."),
            ("user", post_content)
        ])
        chain = prompt | self.llm | StrOutputParser()
        result = chain.invoke({}).strip().upper()

        if "LIKE" in result: return "LIKE"
        if "COMMENT" in result: return "COMMENT"
        return "IGNORE"