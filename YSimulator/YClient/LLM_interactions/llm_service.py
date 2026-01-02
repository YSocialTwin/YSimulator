import random
import ray
from typing import Optional, List
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser


# Constants
DEFAULT_FALLBACK_REACTION = "LIKE"

# Default prompt templates for image description
DEFAULT_IMAGE_DESCRIPTION_PROMPTS = {
    "system_template": "You are an image description assistant. Describe images accurately and concisely in English.",
    "user_template": "Describe the following image. Write in english. <img {url}>"
}

# Use standard Ray actor (CPU) - the GPU is managed by Ollama internally
@ray.remote
class LLMService:
    def __init__(self, llm_config=None, prompts_config=None, llm_v_config=None):
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
                },
                "decide_search_action": {
                    "system_template": "{persona} You searched for posts on a topic you're interested in and found relevant content. Decide how to engage with it.",
                    "user_template": "You found this post on your topic of interest:\n\n\"{post_content}\"\n\nHow do you want to engage? Reply with ONLY ONE WORD from these options:\n- COMMENT (engage in discussion, share your thoughts)\n- SHARE (reshare with your followers)\n- LIKE (positive, agree)\n- LOVE (strongly positive)\n- LAUGH (funny, humorous)\n- ANGRY (negative, disagree)\n- SAD (disappointing, concerning)\n- IGNORE (not interested, skip)\n\nYour choice:"
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
        
        # Initialize vision LLM if config provided
        self.llm_v = None
        if llm_v_config:
            base_url_v = f"http://{llm_v_config['address']}:{llm_v_config['port']}"
            self.llm_v = ChatOllama(
                model=llm_v_config["model"],
                temperature=llm_v_config.get("temperature", 0.5),
                base_url=base_url_v
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
        
        # Get opinion on the topic if available
        topic_opinion = agent_attrs.get("topic_opinion") if agent_attrs else None
        
        # Get prompt templates from configuration
        system_template = self.prompts_config["generate_post"]["system_template"]
        user_template = self.prompts_config["generate_post"]["user_template"]
        
        # Format templates
        system_msg = system_template.format(persona=persona, toxicity=toxicity)
        
        # Build topic instruction with opinion if available
        if topic and topic_opinion:
            topic_instruction = f" Topic: {topic}. Your opinion on this topic is: {topic_opinion}. Express this viewpoint in your post."
        elif topic:
            topic_instruction = f" Topic: {topic}."
        else:
            topic_instruction = ""
        
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
    
    def generate_comment(self, cluster_id: int, post_content: str, agent_attrs: dict = None, author_name: str = "Someone", thread_context: list = None) -> str:
        """
        Generate a comment on a post to continue the discussion.
        
        This method is called remotely via Ray actor (e.g., self.llm.generate_comment.remote(...)).
        
        Args:
            cluster_id: Cluster/persona ID of the agent
            post_content: Content of the post to comment on
            agent_attrs: Dict with agent attributes for dynamic persona building
            author_name: Username of the post author
            thread_context: List of dicts with thread context (preceding posts/comments in chronological order)
                           Each dict has keys: username, tweet
            
        Returns:
            str: Generated comment text
        """
        # Build persona using attributes or fallback
        persona = self._build_persona(cluster_id, agent_attrs)
        
        # Get toxicity level (default to "no" if not provided)
        toxicity = agent_attrs.get("toxicity", "no") if agent_attrs else "no"
        
        # Get opinions on the post's topics if available
        opinion_instruction = ""
        if agent_attrs and "post_topics" in agent_attrs and agent_attrs["post_topics"]:
            topics = agent_attrs["post_topics"]
            opinions = agent_attrs.get("post_opinions", {})
            
            if topics and opinions:
                opinion_parts = []
                for topic in topics:
                    if topic in opinions:
                        opinion_parts.append(f"{topic}: {opinions[topic]}")
                
                if opinion_parts:
                    opinion_str = ", ".join(opinion_parts)
                    opinion_instruction = f" Your opinions on the discussed topics: {opinion_str}. Express your viewpoint accordingly."
        
        # Get prompt templates from configuration
        system_template = self.prompts_config["generate_comment"]["system_template"]
        user_template = self.prompts_config["generate_comment"]["user_template"]
        
        # Format thread context if provided
        thread_context_str = ""
        thread_context_instruction = ""
        if thread_context and len(thread_context) > 0:
            thread_context_lines = []
            for ctx in thread_context:
                username = ctx.get("username", "Someone")
                tweet = ctx.get("tweet", "")
                thread_context_lines.append(f"{username}: {tweet}")
            thread_context_str = "\n".join(thread_context_lines)
            thread_context_instruction = f"Previous discussion in this thread:\n{thread_context_str}\n\n"
        
        # Format templates
        system_msg = system_template.format(persona=persona, toxicity=toxicity)
        user_msg = user_template.format(
            author_name=author_name, 
            post_content=post_content,
            thread_context_instruction=thread_context_instruction
        )
        
        # Add opinion instruction if available
        if opinion_instruction:
            user_msg += opinion_instruction
        
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
        
        # Get opinions on the post's topics if available
        opinion_instruction = ""
        if agent_attrs and "post_topics" in agent_attrs and agent_attrs["post_topics"]:
            topics = agent_attrs["post_topics"]
            opinions = agent_attrs.get("post_opinions", {})
            
            if topics and opinions:
                opinion_parts = []
                for topic in topics:
                    if topic in opinions:
                        opinion_parts.append(f"{topic}: {opinions[topic]}")
                
                if opinion_parts:
                    opinion_str = ", ".join(opinion_parts)
                    opinion_instruction = f" Your opinions on the discussed topics: {opinion_str}. React accordingly."
        
        # Get prompt templates from configuration
        system_template = self.prompts_config["generate_read_reaction"]["system_template"]
        user_template = self.prompts_config["generate_read_reaction"]["user_template"]
        
        # Format templates
        system_msg = system_template.format(persona=persona)
        user_msg = user_template.format(post_content=post_content)
        
        # Add opinion instruction if available
        if opinion_instruction:
            user_msg += opinion_instruction
        
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
            
            # Default to fallback reaction if unclear
            return DEFAULT_FALLBACK_REACTION
        except Exception as e:
            # Fallback if LLM fails
            return DEFAULT_FALLBACK_REACTION
    
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
    
    def decide_search_action(self, cluster_id: int, post_content: str, agent_attrs: dict = None) -> str:
        """
        Decide which action to perform on a searched post: comment, share, or react.
        
        This method is called remotely via Ray actor for the search action.
        LLM agents use this to decide how to engage with discovered content.
        
        Args:
            cluster_id: Cluster/persona ID of the agent
            post_content: Content of the post found via search
            agent_attrs: Dict with agent attributes for dynamic persona building
            
        Returns:
            str: Action type - one of: "COMMENT", "SHARE", "LIKE", "LOVE", "LAUGH", "ANGRY", "SAD", "IGNORE"
        """
        # Build persona using attributes or fallback
        persona = self._build_persona(cluster_id, agent_attrs)
        
        # Get opinions on the post's topics if available
        opinion_instruction = ""
        if agent_attrs and "post_topics" in agent_attrs and agent_attrs["post_topics"]:
            topics = agent_attrs["post_topics"]
            opinions = agent_attrs.get("post_opinions", {})
            
            if topics and opinions:
                opinion_parts = []
                for topic in topics:
                    if topic in opinions:
                        opinion_parts.append(f"{topic}: {opinions[topic]}")
                
                if opinion_parts:
                    opinion_str = ", ".join(opinion_parts)
                    opinion_instruction = f" Your opinions on the discussed topics: {opinion_str}. Consider your viewpoint when deciding how to engage."
        
        # Get prompt templates from configuration
        search_action_config = self.prompts_config.get("decide_search_action", {})
        system_template = search_action_config.get("system_template")
        user_template = search_action_config.get("user_template")
        
        # Validate templates are configured
        if not system_template or not user_template:
            # Log warning and return default fallback
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                "decide_search_action prompts not configured in llm_prompts.json, using default fallback"
            )
            return DEFAULT_FALLBACK_REACTION
        
        # Format templates
        system_msg = system_template.format(persona=persona)
        user_msg = user_template.format(post_content=post_content)
        
        # Add opinion instruction if available
        if opinion_instruction:
            user_msg += opinion_instruction
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_msg),
            ("user", user_msg)
        ])
        
        try:
            chain = prompt | self.llm | StrOutputParser()
            result = chain.invoke({}).strip().upper()
            
            # Parse LLM response - look for valid actions
            if "COMMENT" in result: return "COMMENT"
            if "SHARE" in result: return "SHARE"
            if "LOVE" in result: return "LOVE"
            if "LIKE" in result: return "LIKE"
            if "LAUGH" in result: return "LAUGH"
            if "ANGRY" in result: return "ANGRY"
            if "SAD" in result: return "SAD"
            if "IGNORE" in result: return "IGNORE"
            
            # Default to fallback reaction if unclear
            return DEFAULT_FALLBACK_REACTION
        except Exception as e:
            # Fallback if LLM fails
            return DEFAULT_FALLBACK_REACTION
    
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
            
            # Enforce single-word topics - take only the first word if multiple words present
            single_word_topics = []
            for topic in topics:
                # Split on whitespace and take the first word
                words = topic.split()
                if words:
                    # Take first word and convert to lowercase for consistency
                    single_word = words[0].lower()
                    # Remove any punctuation from the word
                    single_word = ''.join(char for char in single_word if char.isalnum() or char == '-' or char == '_')
                    if single_word:  # Only add if not empty after cleaning
                        single_word_topics.append(single_word)
            
            # Return up to 2 single-word topics
            return single_word_topics[:2]
        except Exception as e:
            # If extraction fails, return empty list
            return []

    def extract_emotions(self, text: str) -> list:
        """
        Extract emotions from text using LLM based on GoEmotions taxonomy.
        
        The model identifies which emotions from the GoEmotions taxonomy the text elicits.
        Returns a list of emotion names that apply to the given text.
        
        Args:
            text: Text content to analyze for emotions
            
        Returns:
            list: List of emotion names from GoEmotions taxonomy (e.g., ["joy", "excitement"])
        """
        # Get prompts from configuration
        system_template = self.prompts_config.get("extract_emotions", {}).get("system_template", 
            "You are an emotion classification assistant. Identify which emotions from the GoEmotions taxonomy the given text elicits.")
        user_template = self.prompts_config.get("extract_emotions", {}).get("user_template",
            "Identify emotions from this text. Choose ONLY from: {emotion_list}\n\nText: \"{text}\"\n\nReturn emotions as comma-separated list:")
        
        # Build emotion list for the prompt
        emotion_list = "admiration, amusement, anger, annoyance, approval, caring, confusion, curiosity, desire, disappointment, disapproval, disgust, embarrassment, excitement, fear, gratitude, grief, joy, love, nervousness, optimism, pride, realization, relief, remorse, sadness, surprise, trust"
        
        # Build prompts
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_template),
            ("user", user_template)
        ])
        chain = prompt | self.llm | StrOutputParser()
        
        try:
            response = chain.invoke({"text": text, "emotion_list": emotion_list})
            # Parse response - split by comma and clean up
            emotions = [e.strip().lower() for e in response.split(',') if e.strip()]
            # Filter to only valid emotions from the taxonomy
            valid_emotions = emotion_list.split(', ')
            emotions = [e for e in emotions if e in valid_emotions]
            return emotions
        except Exception as e:
            # If extraction fails, return empty list
            return []
    
    def describe_image(self, image_url: str) -> Optional[str]:
        """
        Generate a description of an image using the vision LLM.
        
        This method uses the llm_v (vision) model to analyze and describe an image
        from a given URL. The description is generated in English.
        
        Args:
            image_url: URL of the image to describe
            
        Returns:
            Optional[str]: Description of the image, or None if vision LLM not available or error occurs
        """
        # Check if vision LLM is available
        if not self.llm_v:
            logger.warning(f" Vision LLM (llm_v) not configured, cannot describe image")
            return None
        
        # Get prompts from configuration with defaults
        describe_image_config = self.prompts_config.get("describe_image", DEFAULT_IMAGE_DESCRIPTION_PROMPTS)
        system_template = describe_image_config.get("system_template", DEFAULT_IMAGE_DESCRIPTION_PROMPTS["system_template"])
        user_template = describe_image_config.get("user_template", DEFAULT_IMAGE_DESCRIPTION_PROMPTS["user_template"])
        
        # Format templates
        system_msg = system_template
        user_msg = user_template.format(url=image_url)
        
        # Build prompts
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_msg),
            ("user", user_msg)
        ])
        
        try:
            logger.info(f" Calling vision LLM to describe image: {image_url[:80]}...")
            chain = prompt | self.llm_v | StrOutputParser()
            description = chain.invoke({})
            
            if description:
                result = description.strip()
                logger.info(f" Vision LLM returned description ({len(result)} chars)")
                return result
            else:
                logger.warning(f" Vision LLM returned empty description")
                return None
        except Exception as e:
            # If description fails, return None
            logger.error(f" Vision LLM failed to describe image: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def infer_article_opinion(self, article_content: str, topic_name: str, opinion_groups: dict) -> float:
        """
        Infer opinion on a topic from article content using discrete opinion categories.
        
        Uses LLM to classify the article's stance on a topic using predefined opinion groups,
        then maps the selected category to a numeric value in [0, 1] range.
        
        Args:
            article_content: Article text to analyze (first 1000 chars)
            topic_name: Topic to infer opinion about
            opinion_groups: Dict mapping opinion labels to [min, max] ranges
                          e.g., {"Strongly against": [0.0, 0.2], "Neutral": [0.4, 0.6], ...}
            
        Returns:
            float: Opinion value in [0, 1] range (midpoint of selected category range)
        """
        try:
            # Get prompts from configuration
            config = self.prompts_config.get("infer_article_opinion", {})
            system_template = config.get("system_template",
                "You are an opinion classification assistant. Analyze articles and determine their stance on topics.")
            user_template = config.get("user_template",
                "Analyze this article and determine its stance on the topic '{topic}'.\n\n" +
                "Article excerpt:\n{article_text}\n\n" +
                "What is the article's stance? Choose ONLY ONE from these options:\n{opinion_options}\n\n" +
                "Your choice (ONE WORD ONLY):")
            
            # Format opinion options for prompt
            opinion_options = "\n".join([f"- {label}" for label in opinion_groups.keys()])
            
            # Truncate article content
            article_excerpt = article_content[:1000] if len(article_content) > 1000 else article_content
            
            # Build prompt
            prompt = ChatPromptTemplate.from_messages([
                ("system", system_template),
                ("user", user_template)
            ])
            
            chain = prompt | self.llm | StrOutputParser()
            response = chain.invoke({
                "topic": topic_name,
                "article_text": article_excerpt,
                "opinion_options": opinion_options
            }).strip()
            
            # Find which opinion group the LLM selected
            response_lower = response.lower()
            selected_group = None
            for label in opinion_groups.keys():
                if label.lower() in response_lower:
                    selected_group = label
                    break
            
            if selected_group and selected_group in opinion_groups:
                # Map to numeric value using midpoint of range
                range_values = opinion_groups[selected_group]
                opinion_value = (range_values[0] + range_values[1]) / 2.0
                return opinion_value
            else:
                # LLM response didn't match any category, use random
                import random
                return random.random()
                
        except Exception as e:
            # If extraction fails, return random value
            import random
            return random.random()
    
    def generate_image_commentary(self, image_description: str, topics: List[str] = None, 
                                   agent_attrs: dict = None, cluster_id: int = 0) -> str:
        """
        Generate commentary for sharing an image on social media.
        
        Uses the agent's persona to create engaging content that references the image.
        
        Args:
            image_description: Description of the image from the database
            topics: Optional list of topic names related to the image
            agent_attrs: Optional dict with agent attributes for persona building
            cluster_id: Agent cluster ID for fallback persona
            
        Returns:
            str: Generated commentary text
        """
        # Build persona
        persona = self._build_persona(cluster_id, agent_attrs)
        
        # Get toxicity level
        toxicity = ""
        if agent_attrs and "toxicity" in agent_attrs:
            toxicity_level = agent_attrs.get("toxicity", "").lower()
            if toxicity_level in ["low", "medium", "high"]:
                toxicity = toxicity_level
        
        # Build topics instruction
        topics_instruction = ""
        if topics:
            topics_str = ", ".join(topics)
            topics_instruction = f"Related topics: {topics_str}. "
        
        # Get prompts from configuration
        config = self.prompts_config.get("generate_image_commentary", {})
        system_template = config.get("system_template", 
            "{persona} You are sharing an image on social media.")
        user_template = config.get("user_template",
            "You are sharing an image described as: \"{image_description}\"\n\n{topics_instruction}Write a brief, engaging post to share this image (max 280 characters).")
        
        # Format templates
        system_msg = system_template.format(persona=persona, toxicity=toxicity)
        user_msg = user_template.format(
            image_description=image_description,
            topics_instruction=topics_instruction
        )
        
        # Build prompts
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_msg),
            ("user", user_msg)
        ])
        
        try:
            chain = prompt | self.llm | StrOutputParser()
            commentary = chain.invoke({})
            return commentary.strip() if commentary else "IMAGE"
        except Exception as e:
            # If generation fails, return fallback
            logger.error(f" Failed to generate image commentary: {e}")
            return "IMAGE"
    
    def evaluate_opinion(self, agent_opinion: str, author_opinion: str, post_text: str, 
                        topic: str, peers_opinions: list = None) -> str:
        """
        Evaluate how an agent's opinion should change after reading a post.
        
        Uses LLM to determine if the agent agrees, disagrees, or remains neutral
        about the expressed opinion in the post.
        
        Args:
            agent_opinion: Agent's current opinion label (e.g., "Neutral", "In favor")
            author_opinion: Post author's opinion label
            post_text: Content of the post being evaluated
            topic: Topic name being discussed
            peers_opinions: Optional list of (opinion_label, count) tuples for neighbors
            
        Returns:
            str: LLM response - "AGREE", "DISAGREE", or "NEUTRAL"
        """
        # Build the evaluation prompt
        prompt_text = (
            f"Read the following text on the topic '{topic.upper()}': '{post_text}'.\n"
            f"The author has opinion '{author_opinion}' on the topic.\n"
            f"Your initial opinion is '{agent_opinion}'"
        )
        
        # Add peers' opinions if provided (evaluation_scope="neighbors")
        if peers_opinions and len(peers_opinions) > 0:
            prompt_text += "\n\nThe following are the opinions of your friends:\n"
            for op, count in peers_opinions:
                prompt_text += f"Opinion: '{op}' ({count})\n"
        
        prompt_text += (
            "\nWhat do you think about the expressed opinion? "
            "Answer with a single word among the options: AGREE|DISAGREE|NEUTRAL."
        )
        
        # Get prompts from configuration with defaults
        system_template = self.prompts_config.get("evaluate_opinion", {}).get(
            "system_template",
            "You are evaluating opinions on various topics. Consider the content and opinions presented."
        )
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_template),
            ("user", prompt_text)
        ])
        
        try:
            chain = prompt | self.llm | StrOutputParser()
            response = chain.invoke({}).strip().upper()
            
            # Parse response - look for valid reactions
            if "AGREE" in response:
                return "AGREE"
            elif "DISAGREE" in response:
                return "DISAGREE"
            elif "NEUTRAL" in response:
                return "NEUTRAL"
            
            # Default to neutral if unclear
            return "NEUTRAL"
        except Exception as e:
            logger.error(f" Failed to evaluate opinion: {e}")
            return "NEUTRAL"