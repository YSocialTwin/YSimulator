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

    def generate_news_commentary(self, article: dict, website_name: str = None) -> str:
        """
        Generate engaging social media commentary for a news article.
        
        Args:
            article: Article dictionary with 'title' and 'summary' keys
            website_name: Name of the website/page sharing the article
            
        Returns:
            str: Generated commentary (max 280 characters)
        """
        # Extract article information
        article_title = article.get('title', 'News Article')
        article_text = article.get('summary', article.get('description', ''))
        
        # Truncate article text if too long (keep first 500 chars)
        if len(article_text) > 500:
            article_text = article_text[:500] + "..."
        
        # Default website name if not provided
        if not website_name:
            website_name = "this website"
        
        # Create a prompt asking LLM to act as social media manager
        system_msg = f"You are the social media manager for {website_name}. Your job is to present news articles to your audience in an engaging way."
        user_msg = f"""Here's a news article to share:

Title: {article_title}

Content: {article_text}

Write a brief, engaging tweet (max 280 characters) to present this article to your followers. Be professional but engaging. Do NOT include hashtags or links - just your commentary."""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_msg),
            ("user", user_msg)
        ])
        
        # Get commentary from LLM
        try:
            chain = prompt | self.llm | StrOutputParser()
            commentary = chain.invoke({})
            
            # Ensure commentary doesn't exceed tweet length
            if len(commentary) > 280:
                commentary = commentary[:277] + "..."
                
            return commentary
        except Exception as e:
            # Fallback if LLM fails - truncate title if too long
            title = article_title if len(article_title) <= 97 else article_title[:97] + "..."
            return f"Check out this article: {title}"
    
    def generate_comment(self, cluster_id: int, post_content: str) -> str:
        """
        Generate a comment on a post to continue the discussion.
        
        This method is called remotely via Ray actor (e.g., self.llm.generate_comment.remote(...)).
        
        Args:
            cluster_id: Cluster/persona ID of the agent
            post_content: Content of the post to comment on
            
        Returns:
            str: Generated comment text
        """
        # Get persona from configuration
        persona = self.prompts_config["personas"].get(
            str(cluster_id),
            "You are a social media user."
        )
        
        # Create a prompt asking LLM to generate a thoughtful comment
        system_msg = f"{persona} You engage in discussions by commenting on posts."
        user_msg = f"""Someone posted this:

"{post_content}"

Write a brief, thoughtful comment to continue the discussion. Max 100 characters. Be authentic to your persona."""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_msg),
            ("user", user_msg)
        ])
        
        try:
            chain = prompt | self.llm | StrOutputParser()
            comment = chain.invoke({}).strip()
            
            # Ensure comment doesn't exceed length
            if len(comment) > 280:
                comment = comment[:277] + "..."
                
            return comment
        except Exception as e:
            # Fallback if LLM fails
            return "Interesting perspective!"
    
    def generate_read_reaction(self, cluster_id: int, post_content: str) -> str:
        """
        Decide how to react to a post discovered via read/recommendation.
        
        This method is called remotely via Ray actor for the read action.
        
        Args:
            cluster_id: Cluster/persona ID of the agent
            post_content: Content of the post to react to
            
        Returns:
            str: Reaction type - one of: LIKE, LOVE, LAUGH, ANGRY, SAD, IGNORE
        """
        # Get persona from configuration
        persona = self.prompts_config["personas"].get(
            str(cluster_id),
            "You are a social media user."
        )
        
        # Create a prompt asking LLM to decide reaction
        system_msg = f"{persona} You're deciding how to react to content you discovered."
        user_msg = f"""You found this post:

"{post_content}"

How do you react? Reply with ONLY ONE WORD from these options:
- LIKE (positive, agree)
- LOVE (strongly positive)
- LAUGH (funny, humorous)
- ANGRY (negative, disagree, dislike)
- SAD (disappointing, concerning)
- IGNORE (not interested, skip)

Your reaction:"""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_msg),
            ("user", user_msg)
        ])
        
        try:
            chain = prompt | self.llm | StrOutputParser()
            result = chain.invoke({}).strip().upper()
            
            # Parse LLM response - look for valid reactions
            if "LOVE" in result: return "LOVE"
            if "LIKE" in result: return "LIKE"
            if "LAUGH" in result: return "LAUGH"
            if "ANGRY" in result or "DISLIKE" in result: return "ANGRY"  # Map DISLIKE to ANGRY
            if "SAD" in result: return "SAD"
            if "IGNORE" in result: return "IGNORE"
            
            # Default to LIKE if unclear
            return "LIKE"
        except Exception as e:
            # Fallback if LLM fails - default to LIKE
            return "LIKE"
    
    def generate_follow_decision(self, cluster_id: int, candidate_users: list) -> str:
        """
        Decide whether to follow one of the suggested users.
        
        This method is called remotely via Ray actor for the follow action.
        
        Args:
            cluster_id: Cluster/persona ID of the agent
            candidate_users: List of user IDs that could be followed
            
        Returns:
            str: User ID to follow, or None to skip following
        """
        import random
        
        # If no candidates, return None
        if not candidate_users:
            return None
        
        # Get persona from configuration
        persona = self.prompts_config["personas"].get(
            str(cluster_id),
            "You are a social media user."
        )
        
        # For simplicity, LLM-based agents randomly select from candidates
        # In future versions, this could query user profiles and make informed decisions
        # For now, we keep it simple: randomly select one candidate
        
        # Simple heuristic: follow with 70% probability
        if random.random() < 0.7:
            return random.choice(candidate_users)
        else:
            return None  # Skip following this time
    
    def generate_secondary_follow_decision(self, cluster_id: int, post_content: str, is_currently_following: bool) -> str:
        """
        Decide whether to follow or unfollow a post author based on interaction.
        
        This method is called after an agent has read or commented on a post,
        to determine if they want to establish or break a social tie with the author.
        
        Args:
            cluster_id: Cluster/persona ID of the agent
            post_content: Content of the post the agent interacted with
            is_currently_following: Whether the agent currently follows the author
            
        Returns:
            str: Decision - "follow", "unfollow", or "no_change"
        """
        import random
        
        # Get persona from configuration
        persona = self.prompts_config["personas"].get(
            str(cluster_id),
            "You are a social media user."
        )
        
        # For simplicity, use a heuristic approach:
        # - If not following: 30% chance to follow
        # - If following: 10% chance to unfollow
        # This could be enhanced with actual LLM prompts in future versions
        
        if not is_currently_following:
            # Not following yet, consider following
            if random.random() < 0.3:
                return "follow"
        else:
            # Already following, consider unfollowing
            if random.random() < 0.1:
                return "unfollow"
        
        return "no_change"