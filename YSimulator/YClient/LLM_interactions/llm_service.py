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

    def _build_persona(self, cluster_id: int, agent_attrs: dict = None) -> str:
        """
        Build a persona string for an agent using either attributes or fallback.
        
        Args:
            cluster_id: Cluster/persona ID for fallback
            agent_attrs: Dict with agent attributes (name, age, gender, nationality, 
                        profession, political_leaning, oe, co, ex, ag, ne, toxicity)
        
        Returns:
            str: Formatted persona string
        """
        # If agent attributes are provided, use the persona template
        if agent_attrs and self.prompts_config.get("persona_template"):
            template = self.prompts_config["persona_template"]
            try:
                # Build persona from template with agent attributes
                persona = template.format(
                    name=agent_attrs.get("name", "Anonymous"),
                    age=agent_attrs.get("age", "unknown"),
                    gender=agent_attrs.get("gender", "person"),
                    nationality=agent_attrs.get("nationality", "citizen"),
                    profession=agent_attrs.get("profession", "individual"),
                    political_leaning=agent_attrs.get("political_leaning", "neutral"),
                    oe=agent_attrs.get("oe", "average in openness"),
                    co=agent_attrs.get("co", "average in conscientiousness"),
                    ex=agent_attrs.get("ex", "average in extraversion"),
                    ag=agent_attrs.get("ag", "average in agreeableness"),
                    ne=agent_attrs.get("ne", "average in neuroticism")
                )
                return persona
            except KeyError as e:
                # If template formatting fails, fall back to cluster-based persona
                pass
        
        # Fallback to cluster-based persona
        return self.prompts_config["personas"].get(
            str(cluster_id),
            "You are a social media user."
        )

    def generate_post(self, cluster_id: int, day: int, slot: int, agent_attrs: dict = None) -> str:
        """Generate content based on Persona."""
        # Build persona using attributes or fallback
        persona = self._build_persona(cluster_id, agent_attrs)
        
        # Get toxicity level (default to "no" if not provided)
        toxicity = agent_attrs.get("toxicity", "no") if agent_attrs else "no"
        
        # Get topic if available
        topic = agent_attrs.get("topic") if agent_attrs else None
        
        # Get prompt templates from configuration
        system_template = self.prompts_config["generate_post"]["system_template"]
        user_template = self.prompts_config["generate_post"]["user_template"]
        
        # Format templates
        system_msg = system_template.format(persona=persona, toxicity=toxicity)
        
        # Build topic instruction
        topic_instruction = f" Topic: {topic}." if topic else ""
        
        # Format user message with topic instruction
        user_msg = user_template.format(day=day, slot=slot, topic_instruction=topic_instruction)

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
        
        # Get prompt templates from configuration
        system_template = self.prompts_config["generate_news_commentary"]["system_template"]
        user_template = self.prompts_config["generate_news_commentary"]["user_template"]
        
        # Format templates
        system_msg = system_template.format(website_name=website_name)
        user_msg = user_template.format(article_title=article_title, article_text=article_text)
        
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
    
    def generate_comment(self, cluster_id: int, post_content: str, agent_attrs: dict = None, author_name: str = "Someone") -> str:
        """
        Generate a comment on a post to continue the discussion.
        
        This method is called remotely via Ray actor (e.g., self.llm.generate_comment.remote(...)).
        
        Args:
            cluster_id: Cluster/persona ID of the agent
            post_content: Content of the post to comment on
            agent_attrs: Dict with agent attributes for dynamic persona building
            author_name: Username of the post author
            
        Returns:
            str: Generated comment text
        """
        # Build persona using attributes or fallback
        persona = self._build_persona(cluster_id, agent_attrs)
        
        # Get toxicity level (default to "no" if not provided)
        toxicity = agent_attrs.get("toxicity", "no") if agent_attrs else "no"
        
        # Get prompt templates from configuration
        system_template = self.prompts_config["generate_comment"]["system_template"]
        user_template = self.prompts_config["generate_comment"]["user_template"]
        
        # Format templates
        system_msg = system_template.format(persona=persona, toxicity=toxicity)
        user_msg = user_template.format(author_name=author_name, post_content=post_content)
        
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
    
    def generate_read_reaction(self, cluster_id: int, post_content: str, agent_attrs: dict = None) -> str:
        """
        Decide how to react to a post discovered via read/recommendation.
        
        This method is called remotely via Ray actor for the read action.
        
        Args:
            cluster_id: Cluster/persona ID of the agent
            post_content: Content of the post to react to
            agent_attrs: Dict with agent attributes for dynamic persona building
            
        Returns:
            str: Reaction type - one of: LIKE, LOVE, LAUGH, ANGRY, SAD, IGNORE
        """
        # Build persona using attributes or fallback
        persona = self._build_persona(cluster_id, agent_attrs)
        
        # Get prompt templates from configuration
        system_template = self.prompts_config["generate_read_reaction"]["system_template"]
        user_template = self.prompts_config["generate_read_reaction"]["user_template"]
        
        # Format templates
        system_msg = system_template.format(persona=persona)
        user_msg = user_template.format(post_content=post_content)
        
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
        
        # Get follow probability from configuration
        follow_config = self.prompts_config.get("generate_follow_decision", {})
        follow_probability = follow_config.get("follow_probability", 0.7)
        
        # Simple heuristic: follow with configured probability
        if random.random() < follow_probability:
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
        
        # Get follow decision probabilities from configuration
        follow_config = self.prompts_config.get("generate_secondary_follow_decision", {})
        follow_prob = follow_config.get("follow_probability_when_not_following", 0.3)
        unfollow_prob = follow_config.get("unfollow_probability_when_following", 0.1)
        
        if not is_currently_following:
            # Not following yet, consider following
            if random.random() < follow_prob:
                return "follow"
        else:
            # Already following, consider unfollowing
            if random.random() < unfollow_prob:
                return "unfollow"
        
        return "no_change"
    
    def extract_topics_from_article(self, article_title: str, article_summary: str) -> list:
        """
        Extract up to 2 topics from an article using LLM.
        
        Args:
            article_title: Title of the article
            article_summary: Summary/content of the article
            
        Returns:
            list: List of up to 2 topic strings
        """
        # Combine title and summary for analysis
        article_text = f"Title: {article_title}\n\nSummary: {article_summary}" if article_summary else f"Title: {article_title}"
        
        # Get prompts from configuration
        system_template = self.prompts_config["extract_article_topics"]["system_template"]
        user_template = self.prompts_config["extract_article_topics"]["user_template"]
        
        # Build prompts with article text
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_template),
            ("user", user_template)
        ])
        chain = prompt | self.llm | StrOutputParser()
        
        try:
            response = chain.invoke({"article_text": article_text})
            # Parse response - split by comma and clean up
            topics = [t.strip() for t in response.split(',') if t.strip()]
            # Return up to 2 topics
            return topics[:2]
        except Exception as e:
            # If extraction fails, return empty list
            return []