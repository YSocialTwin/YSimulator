import ray
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser


# Use standard Ray actor (CPU) - the GPU is managed by Ollama internally
@ray.remote
class LLMService:
    def __init__(self, llm_config=None, prompts_config=None):
        # Load configuration with defaults
        if llm_config is None:
            llm_config = {
                "address": "localhost",
                "port": 11434,
                "model": "llama3.2",
                "temperature": 0.7
            }
        
        if prompts_config is None:
            prompts_config = {
                "personas": {
                    "0": "You are a 'Validator'. Skeptical, brief, authentic.",
                    "1": "You are a 'Broadcaster'. High energy, viral, controversial.",
                    "2": "You are an 'Explorer'. Curious, asking questions."
                },
                "generate_post": {
                    "system_template": "{persona}",
                    "user_template": "Write a tweet for Day {day} Slot {slot}. Max 15 words."
                },
                "decide_reaction": {
                    "system_template": "You are user type {cluster_id}. Read post. Reply ONLY: 'LIKE', 'COMMENT', 'IGNORE'.",
                    "user_template": "{post_content}"
                }
            }
        
        # Store prompts configuration
        self.prompts_config = prompts_config
        
        # Build base_url from address and port
        base_url = f"http://{llm_config['address']}:{llm_config['port']}"
        
        # Initialize LLM with configuration
        self.llm = ChatOllama(
            model=llm_config["model"],
            temperature=llm_config["temperature"],
            base_url=base_url
        )

    def generate_post(self, cluster_id: int, day: int, slot: int) -> str:
        """Generate content based on Persona."""
        # Get persona from configuration
        persona = self.prompts_config["personas"].get(
            str(cluster_id),
            "You are a social media user."
        )
        
        # Get prompt templates from configuration
        system_template = self.prompts_config["generate_post"]["system_template"]
        user_template = self.prompts_config["generate_post"]["user_template"]
        
        # Format templates
        system_msg = system_template.format(persona=persona)
        user_msg = user_template.format(day=day, slot=slot)

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_msg),
            ("user", user_msg)
        ])
        chain = prompt | self.llm | StrOutputParser()
        return chain.invoke({})

    def decide_reaction(self, cluster_id: int, post_content: str) -> str:
        """Decide: LIKE, COMMENT, or IGNORE."""
        # Get prompt templates from configuration
        system_template = self.prompts_config["decide_reaction"]["system_template"]
        user_template = self.prompts_config["decide_reaction"]["user_template"]
        
        # Format templates
        system_msg = system_template.format(cluster_id=cluster_id)
        user_msg = user_template.format(post_content=post_content)
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_msg),
            ("user", user_msg)
        ])
        chain = prompt | self.llm | StrOutputParser()
        result = chain.invoke({}).strip().upper()

        if "LIKE" in result: return "LIKE"
        if "COMMENT" in result: return "COMMENT"
        return "IGNORE"