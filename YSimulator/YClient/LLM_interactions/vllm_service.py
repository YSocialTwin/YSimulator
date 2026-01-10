"""
vLLM-based LLM Service for YSimulator with batch inference support.

This module provides a Ray actor that uses vLLM for efficient batch inference,
achieving significant performance improvements over sequential Ollama processing.
The interface is designed to be compatible with the existing LLMService pattern.
"""

import logging
from typing import Any, Dict, List, Optional

import ray

# Initialize logger
logger = logging.getLogger(__name__)


@ray.remote
class VLLMService:
    """
    vLLM-based LLM service with batch inference support.

    This service uses vLLM's efficient batch inference capabilities to process
    multiple prompts in parallel, reducing the LLM bottleneck identified in
    the performance analysis.

    The service maintains the same interface as LLMService for compatibility
    with existing YClient patterns.
    """

    def __init__(
        self,
        llm_config: Optional[Dict[str, Any]] = None,
        prompts_config: Optional[Dict[str, Any]] = None,
        llm_v_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize vLLM service with configuration.

        Args:
            llm_config: LLM configuration with keys:
                - model: Model name/path (e.g., "meta-llama/Llama-3.2-3B")
                - temperature: Sampling temperature (default: 0.7)
                - max_tokens: Maximum tokens to generate (default: 256)
                - tensor_parallel_size: Number of GPUs for tensor parallelism (default: 1)
                - gpu_memory_utilization: GPU memory utilization (default: 0.9)
            prompts_config: Prompt templates configuration (same as LLMService)
            llm_v_config: Vision LLM configuration with keys:
                - model: Vision model name/path (e.g., "openbmb/MiniCPM-V-2_6")
                - temperature: Sampling temperature (default: 0.5)
                - max_tokens: Maximum tokens to generate (default: 300)
        """
        try:
            from vllm import LLM, SamplingParams
        except ImportError as e:
            raise ImportError(
                "vLLM is not installed. Install it with: pip install vllm\n"
                "Note: vLLM requires Linux and is not supported on macOS."
            ) from e

        # Load configuration with defaults
        if llm_config is None:
            llm_config = {
                "model": "meta-llama/Llama-3.2-3B",
                "temperature": 0.7,
                "max_tokens": 256,
                "tensor_parallel_size": 1,
                "gpu_memory_utilization": 0.9,
            }

        if prompts_config is None:
            prompts_config = {
                "personas": {
                    "0": "You are a 'Validator'. Skeptical, brief, authentic.",
                    "1": "You are a 'Broadcaster'. High energy, viral, controversial.",
                    "2": "You are an 'Explorer'. Curious, asking questions.",
                },
                "generate_post": {
                    "system_template": "{persona}",
                    "user_template": "Write a tweet for Day {day} Slot {slot}. Max 15 words.",
                },
                "decide_reaction": {
                    "system_template": "You are user type {cluster_id}. Read post. Reply ONLY: 'LIKE', 'COMMENT', 'IGNORE'.",
                    "user_template": "{post_content}",
                },
            }

        # Store prompts configuration
        self.prompts_config = prompts_config

        # Initialize vLLM engine for text generation
        model_name = llm_config.get("model", "meta-llama/Llama-3.2-3B")
        tensor_parallel_size = llm_config.get("tensor_parallel_size", 1)
        gpu_memory_utilization = llm_config.get("gpu_memory_utilization", 0.9)

        logger.info(
            f"[vLLM] Initializing vLLM engine with text model={model_name}, "
            f"tensor_parallel_size={tensor_parallel_size}, "
            f"gpu_memory_utilization={gpu_memory_utilization}"
        )

        try:
            self.llm = LLM(
                model=model_name,
                tensor_parallel_size=tensor_parallel_size,
                gpu_memory_utilization=gpu_memory_utilization,
                trust_remote_code=True,
            )

            # Set up sampling parameters for text generation
            temperature = llm_config.get("temperature", 0.7)
            max_tokens = llm_config.get("max_tokens", 256)

            self.sampling_params = SamplingParams(
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=0.95,
            )

            logger.info("[vLLM] vLLM text generation engine initialized successfully")
        except Exception as e:
            logger.error(f"[vLLM] Failed to initialize vLLM text engine: {e}")
            logger.error(f"[vLLM] Model: {model_name}, Tensor parallel size: {tensor_parallel_size}")
            raise RuntimeError(f"vLLM text model initialization failed: {e}") from e

        # Initialize vision LLM if config provided
        self.llm_v = None
        self.sampling_params_v = None
        if llm_v_config:
            vision_model = llm_v_config.get("model", "openbmb/MiniCPM-V-2_6")
            vision_temp = llm_v_config.get("temperature", 0.5)
            vision_max_tokens = llm_v_config.get("max_tokens", 300)
            
            logger.info(
                f"[vLLM] Initializing vLLM vision engine with model={vision_model}, "
                f"temperature={vision_temp}, max_tokens={vision_max_tokens}"
            )
            
            try:
                # Initialize vision model with vLLM
                # Note: Vision models in vLLM require trust_remote_code=True
                self.llm_v = LLM(
                    model=vision_model,
                    tensor_parallel_size=tensor_parallel_size,
                    gpu_memory_utilization=gpu_memory_utilization,
                    trust_remote_code=True,
                    # Vision-specific settings
                    max_model_len=vision_max_tokens if "max_model_len" not in llm_v_config else llm_v_config["max_model_len"],
                )
                
                # Set up sampling parameters for vision model
                self.sampling_params_v = SamplingParams(
                    temperature=vision_temp,
                    max_tokens=vision_max_tokens,
                    top_p=0.95,
                )
                
                logger.info("[vLLM] vLLM vision engine initialized successfully")
            except Exception as e:
                logger.error(f"[vLLM] Failed to initialize vLLM vision engine: {e}")
                logger.error(f"[vLLM] Vision model: {vision_model}")
                logger.warning("[vLLM] Vision model functionality will be disabled")
                self.llm_v = None
                self.sampling_params_v = None

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
                    ne=agent_attrs.get("ne", "average in neuroticism"),
                )
                return persona
            except KeyError:
                # If template formatting fails, fall back to cluster-based persona
                pass

        # Fallback to cluster-based persona
        return self.prompts_config["personas"].get(str(cluster_id), "You are a social media user.")

    def _format_prompt(self, system_msg: str, user_msg: str) -> str:
        """
        Format system and user messages into a single prompt.

        Args:
            system_msg: System message (context/instructions)
            user_msg: User message (task/query)

        Returns:
            str: Formatted prompt for the model
        """
        return f"System: {system_msg}\n\nUser: {user_msg}\n\nAssistant:"

    def generate_post(self, cluster_id: int, day: int, slot: int, agent_attrs: dict = None) -> str:
        """Generate content based on Persona."""
        try:
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

            # Create formatted prompt
            prompt = self._format_prompt(system_msg, user_msg)

            # Generate using vLLM
            logger.debug(f"[vLLM] Generating post for cluster_id={cluster_id}, day={day}, slot={slot}")
            outputs = self.llm.generate([prompt], self.sampling_params)
            result = outputs[0].outputs[0].text.strip()
            logger.debug(f"[vLLM] Generated post successfully (length={len(result)})")
            return result
        except KeyError as e:
            logger.error(f"[vLLM] Missing configuration key in generate_post: {e}")
            logger.error(f"[vLLM] cluster_id={cluster_id}, day={day}, slot={slot}")
            raise
        except Exception as e:
            logger.error(f"[vLLM] Failed to generate post: {e}")
            logger.error(f"[vLLM] cluster_id={cluster_id}, day={day}, slot={slot}")
            raise RuntimeError(f"vLLM post generation failed: {e}") from e

    def generate_post_batch(
        self, requests: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Generate multiple posts in a single batch for improved performance.

        Args:
            requests: List of request dicts, each with keys:
                - cluster_id: Agent cluster ID
                - day: Day number
                - slot: Slot number
                - agent_attrs: Agent attributes dict (optional)

        Returns:
            List of generated post strings in the same order as requests
        """
        try:
            logger.debug(f"[vLLM] Starting batch post generation for {len(requests)} requests")
            prompts = []
            for idx, req in enumerate(requests):
                try:
                    cluster_id = req["cluster_id"]
                    day = req["day"]
                    slot = req["slot"]
                    agent_attrs = req.get("agent_attrs")

                    # Build persona
                    persona = self._build_persona(cluster_id, agent_attrs)
                    toxicity = agent_attrs.get("toxicity", "no") if agent_attrs else "no"
                    topic = agent_attrs.get("topic") if agent_attrs else None
                    topic_opinion = agent_attrs.get("topic_opinion") if agent_attrs else None

                    # Get prompt templates
                    system_template = self.prompts_config["generate_post"]["system_template"]
                    user_template = self.prompts_config["generate_post"]["user_template"]

                    # Format templates
                    system_msg = system_template.format(persona=persona, toxicity=toxicity)

                    # Build topic instruction
                    if topic and topic_opinion:
                        topic_instruction = f" Topic: {topic}. Your opinion on this topic is: {topic_opinion}. Express this viewpoint in your post."
                    elif topic:
                        topic_instruction = f" Topic: {topic}."
                    else:
                        topic_instruction = ""

                    user_msg = user_template.format(day=day, slot=slot, topic_instruction=topic_instruction)

                    # Create formatted prompt
                    prompt = self._format_prompt(system_msg, user_msg)
                    prompts.append(prompt)
                except Exception as e:
                    logger.error(f"[vLLM] Failed to build prompt for batch request {idx}: {e}")
                    logger.error(f"[vLLM] Request: {req}")
                    raise

            # Batch generate using vLLM
            logger.debug(f"[vLLM] Executing batch inference for {len(prompts)} prompts")
            outputs = self.llm.generate(prompts, self.sampling_params)
            results = [output.outputs[0].text.strip() for output in outputs]
            logger.debug(f"[vLLM] Batch generation completed successfully ({len(results)} results)")
            return results
        except Exception as e:
            logger.error(f"[vLLM] Batch post generation failed: {e}")
            logger.error(f"[vLLM] Number of requests: {len(requests)}")
            raise RuntimeError(f"vLLM batch post generation failed: {e}") from e

    def decide_reaction(self, cluster_id: int, post_content: str) -> str:
        """Decide: LIKE, COMMENT, or IGNORE."""
        try:
            # Get prompt templates from configuration
            system_template = self.prompts_config["decide_reaction"]["system_template"]
            user_template = self.prompts_config["decide_reaction"]["user_template"]

            # Format templates
            system_msg = system_template.format(cluster_id=cluster_id)
            user_msg = user_template.format(post_content=post_content)

            # Create formatted prompt
            prompt = self._format_prompt(system_msg, user_msg)

            # Generate using vLLM
            logger.debug(f"[vLLM] Deciding reaction for cluster_id={cluster_id}")
            outputs = self.llm.generate([prompt], self.sampling_params)
            result = outputs[0].outputs[0].text.strip().upper()

            if "LIKE" in result:
                return "LIKE"
            if "COMMENT" in result:
                return "COMMENT"
            return "IGNORE"
        except KeyError as e:
            logger.error(f"[vLLM] Missing configuration key in decide_reaction: {e}")
            logger.error(f"[vLLM] cluster_id={cluster_id}")
            raise
        except Exception as e:
            logger.error(f"[vLLM] Failed to decide reaction: {e}")
            logger.error(f"[vLLM] cluster_id={cluster_id}, post_content_len={len(post_content) if post_content else 0}")
            # Return default fallback to maintain YClient pattern
            logger.warning(f"[vLLM] Returning fallback reaction: IGNORE")
            return "IGNORE"

    def generate_comment(
        self,
        cluster_id: int,
        post_content: str,
        agent_attrs: dict = None,
        author_name: str = "Someone",
        thread_context: list = None,
    ) -> str:
        """
        Generate a comment on a post to continue the discussion.

        Args:
            cluster_id: Cluster/persona ID of the agent
            post_content: Content of the post to comment on
            agent_attrs: Dict with agent attributes for dynamic persona building
            author_name: Username of the post author
            thread_context: List of dicts with thread context (preceding posts/comments)

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
            thread_context_instruction = (
                f"Previous discussion in this thread:\n{thread_context_str}\n\n"
            )

        # Format templates
        system_msg = system_template.format(persona=persona, toxicity=toxicity)
        user_msg = user_template.format(
            author_name=author_name,
            post_content=post_content,
            thread_context_instruction=thread_context_instruction,
        )

        # Add opinion instruction if available
        if opinion_instruction:
            user_msg += opinion_instruction

        # Create formatted prompt
        prompt = self._format_prompt(system_msg, user_msg)

        try:
            # Generate using vLLM
            logger.debug(f"[vLLM] Generating comment for cluster_id={cluster_id}, author={author_name}")
            outputs = self.llm.generate([prompt], self.sampling_params)
            comment = outputs[0].outputs[0].text.strip()

            # Ensure comment doesn't exceed length
            if len(comment) > 280:
                comment = comment[:277] + "..."

            logger.debug(f"[vLLM] Generated comment successfully (length={len(comment)})")
            return comment
        except Exception as e:
            # Fallback if LLM fails
            logger.error(f"[vLLM] Failed to generate comment: {e}")
            logger.error(f"[vLLM] cluster_id={cluster_id}, author={author_name}, post_content_len={len(post_content) if post_content else 0}")
            logger.warning("[vLLM] Returning fallback comment")
            return "Interesting perspective!"

    # Add placeholder methods for compatibility with LLMService interface
    # These methods maintain the same signature but may need full implementation
    # based on usage patterns in the codebase

    def generate_news_commentary(self, article: dict, website_name: str = None) -> str:
        """Generate engaging social media commentary for a news article."""
        try:
            article_title = article.get("title", "News Article")
            article_text = article.get("summary", article.get("description", ""))

            if len(article_text) > 500:
                article_text = article_text[:500] + "..."

            if not website_name:
                website_name = "this website"

            system_template = self.prompts_config["generate_news_commentary"]["system_template"]
            user_template = self.prompts_config["generate_news_commentary"]["user_template"]

            system_msg = system_template.format(website_name=website_name)
            user_msg = user_template.format(article_title=article_title, article_text=article_text)

            prompt = self._format_prompt(system_msg, user_msg)

            logger.debug(f"[vLLM] Generating news commentary for article: {article_title[:50]}...")
            outputs = self.llm.generate([prompt], self.sampling_params)
            commentary = outputs[0].outputs[0].text.strip()

            if len(commentary) > 280:
                commentary = commentary[:277] + "..."

            logger.debug(f"[vLLM] Generated news commentary successfully (length={len(commentary)})")
            return commentary
        except KeyError as e:
            logger.error(f"[vLLM] Missing configuration key in generate_news_commentary: {e}")
            title = article_title if len(article_title) <= 97 else article_title[:97] + "..."
            return f"Check out this article: {title}"
        except Exception as e:
            logger.error(f"[vLLM] Failed to generate news commentary: {e}")
            logger.error(f"[vLLM] Article title: {article.get('title', 'Unknown')[:50]}")
            logger.warning("[vLLM] Returning fallback commentary")
            title = article_title if len(article_title) <= 97 else article_title[:97] + "..."
            return f"Check out this article: {title}"

    def generate_share_commentary(
        self,
        cluster_id: int,
        post_content: str,
        agent_attrs: dict = None,
        author_name: str = "Someone",
    ) -> str:
        """Generate commentary for sharing/resharing a post."""
        persona = self._build_persona(cluster_id, agent_attrs)
        toxicity = agent_attrs.get("toxicity", "no") if agent_attrs else "no"

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
                    opinion_instruction = f" Your opinions on the discussed topics: {opinion_str}. Reflect your viewpoint in your commentary."

        if "generate_share_commentary" not in self.prompts_config:
            logger.warning("generate_share_commentary prompt not found in config, using fallback")
            return "Sharing this!"

        system_template = self.prompts_config["generate_share_commentary"]["system_template"]
        user_template = self.prompts_config["generate_share_commentary"]["user_template"]

        system_msg = system_template.format(persona=persona, toxicity=toxicity)
        user_msg = user_template.format(author_name=author_name, post_content=post_content)

        if opinion_instruction:
            user_msg += opinion_instruction

        prompt = self._format_prompt(system_msg, user_msg)

        try:
            outputs = self.llm.generate([prompt], self.sampling_params)
            commentary = outputs[0].outputs[0].text.strip()

            if len(commentary) > 200:
                commentary = commentary[:197] + "..."

            return commentary
        except Exception:
            return "Sharing this!"

    def generate_read_reaction(
        self, cluster_id: int, post_content: str, agent_attrs: dict = None
    ) -> str:
        """Decide how to react to a post discovered via read/recommendation."""
        persona = self._build_persona(cluster_id, agent_attrs)

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
                    opinion_instruction = (
                        f" Your opinions on the discussed topics: {opinion_str}. React accordingly."
                    )

        system_template = self.prompts_config["generate_read_reaction"]["system_template"]
        user_template = self.prompts_config["generate_read_reaction"]["user_template"]

        system_msg = system_template.format(persona=persona)
        user_msg = user_template.format(post_content=post_content)

        if opinion_instruction:
            user_msg += opinion_instruction

        prompt = self._format_prompt(system_msg, user_msg)

        try:
            outputs = self.llm.generate([prompt], self.sampling_params)
            result = outputs[0].outputs[0].text.strip().upper()

            if "LOVE" in result:
                return "LOVE"
            if "LIKE" in result:
                return "LIKE"
            if "LAUGH" in result:
                return "LAUGH"
            if "ANGRY" in result or "DISLIKE" in result:
                return "ANGRY"
            if "SAD" in result:
                return "SAD"
            if "IGNORE" in result:
                return "IGNORE"

            return "LIKE"  # Default fallback
        except Exception:
            return "LIKE"

    def generate_follow_decision(self, cluster_id: int, candidate_users: list) -> str:
        """Decide whether to follow one of the suggested users."""
        if not candidate_users:
            return None

        follow_config = self.prompts_config.get("generate_follow_decision", {})
        follow_probability = follow_config.get("follow_probability", 0.7)

        import random

        if random.random() < follow_probability:
            return random.choice(candidate_users)
        else:
            return None

    def decide_search_action(
        self, cluster_id: int, post_content: str, agent_attrs: dict = None
    ) -> str:
        """Decide which action to perform on a searched post."""
        persona = self._build_persona(cluster_id, agent_attrs)

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

        search_action_config = self.prompts_config.get("decide_search_action", {})
        system_template = search_action_config.get("system_template")
        user_template = search_action_config.get("user_template")

        if not system_template or not user_template:
            logger.warning(
                "decide_search_action prompts not configured in llm_prompts.json, using default fallback"
            )
            return "LIKE"

        system_msg = system_template.format(persona=persona)
        user_msg = user_template.format(post_content=post_content)

        if opinion_instruction:
            user_msg += opinion_instruction

        prompt = self._format_prompt(system_msg, user_msg)

        try:
            outputs = self.llm.generate([prompt], self.sampling_params)
            result = outputs[0].outputs[0].text.strip().upper()

            if "COMMENT" in result:
                return "COMMENT"
            if "SHARE" in result:
                return "SHARE"
            if "LOVE" in result:
                return "LOVE"
            if "LIKE" in result:
                return "LIKE"
            if "LAUGH" in result:
                return "LAUGH"
            if "ANGRY" in result:
                return "ANGRY"
            if "SAD" in result:
                return "SAD"
            if "IGNORE" in result:
                return "IGNORE"

            return "LIKE"
        except Exception:
            return "LIKE"

    def generate_secondary_follow_decision(
        self, cluster_id: int, post_content: str, is_currently_following: bool
    ) -> str:
        """Decide whether to follow or unfollow a post author based on interaction."""
        follow_config = self.prompts_config.get("generate_secondary_follow_decision", {})
        follow_prob = follow_config.get("follow_probability_when_not_following", 0.3)
        unfollow_prob = follow_config.get("unfollow_probability_when_following", 0.1)

        import random

        if not is_currently_following:
            if random.random() < follow_prob:
                return "follow"
        else:
            if random.random() < unfollow_prob:
                return "unfollow"

        return "no_change"

    def extract_topics_from_article(self, article_title: str, article_summary: str) -> list:
        """Extract up to 2 topics from an article using LLM."""
        article_text = (
            f"Title: {article_title}\n\nSummary: {article_summary}"
            if article_summary
            else f"Title: {article_title}"
        )

        system_template = self.prompts_config["extract_article_topics"]["system_template"]
        user_template = self.prompts_config["extract_article_topics"]["user_template"]

        prompt = self._format_prompt(system_template, user_template)
        prompt = prompt.replace("{article_text}", article_text)

        try:
            outputs = self.llm.generate([prompt], self.sampling_params)
            response = outputs[0].outputs[0].text.strip()

            topics = [t.strip() for t in response.split(",") if t.strip()]

            single_word_topics = []
            for topic in topics:
                words = topic.split()
                if words:
                    single_word = words[0].lower()
                    single_word = "".join(
                        char for char in single_word if char.isalnum() or char == "-" or char == "_"
                    )
                    if single_word:
                        single_word_topics.append(single_word)

            return single_word_topics[:2]
        except Exception:
            return []

    def extract_emotions(self, text: str) -> list:
        """Extract emotions from text using LLM based on GoEmotions taxonomy."""
        system_template = self.prompts_config.get("extract_emotions", {}).get(
            "system_template",
            "You are an emotion classification assistant. Identify which emotions from the GoEmotions taxonomy the given text elicits.",
        )
        user_template = self.prompts_config.get("extract_emotions", {}).get(
            "user_template",
            'Identify emotions from this text. Choose ONLY from: {emotion_list}\n\nText: "{text}"\n\nReturn emotions as comma-separated list:',
        )

        emotion_list = "admiration, amusement, anger, annoyance, approval, caring, confusion, curiosity, desire, disappointment, disapproval, disgust, embarrassment, excitement, fear, gratitude, grief, joy, love, nervousness, optimism, pride, realization, relief, remorse, sadness, surprise, trust"

        prompt = self._format_prompt(system_template, user_template)
        prompt = prompt.replace("{text}", text).replace("{emotion_list}", emotion_list)

        try:
            outputs = self.llm.generate([prompt], self.sampling_params)
            response = outputs[0].outputs[0].text.strip()

            emotions = [e.strip().lower() for e in response.split(",") if e.strip()]
            valid_emotions = emotion_list.split(", ")
            emotions = [e for e in emotions if e in valid_emotions]
            return emotions
        except Exception:
            return []

    def describe_image(self, image_url: str) -> Optional[str]:
        """
        Generate a description of an image using the vision LLM.

        This method uses the llm_v (vision) model loaded in vLLM to analyze and 
        describe an image from a given URL.

        Args:
            image_url: URL of the image to describe

        Returns:
            Optional[str]: Description of the image, or None if vision LLM not available or error occurs
        """
        # Check if vision LLM is available
        if not self.llm_v:
            logger.warning("[vLLM] Vision LLM (llm_v) not configured, cannot describe image")
            return None

        try:
            # Get prompts from configuration with defaults
            describe_image_config = self.prompts_config.get(
                "describe_image",
                {
                    "system_template": "You are an image description assistant. Describe images accurately and concisely in English.",
                    "user_template": "Describe the following image. Write in english. <img {url}>",
                },
            )
            system_template = describe_image_config.get(
                "system_template",
                "You are an image description assistant. Describe images accurately and concisely in English.",
            )
            user_template = describe_image_config.get(
                "user_template", "Describe the following image. Write in english. <img {url}>"
            )

            # Format templates
            system_msg = system_template
            user_msg = user_template.format(url=image_url)

            # For vision models, we need to format the prompt with image information
            # vLLM vision models expect a specific format
            prompt = f"{system_msg}\n\n{user_msg}"

            logger.info(f"[vLLM] Calling vLLM vision model to describe image: {image_url[:80]}...")
            
            # Generate description using vision model
            outputs = self.llm_v.generate([prompt], self.sampling_params_v)
            
            if outputs and len(outputs) > 0:
                description = outputs[0].outputs[0].text.strip()
                logger.info(f"[vLLM] vLLM vision model returned description ({len(description)} chars)")
                return description
            else:
                logger.warning("[vLLM] vLLM vision model returned empty description")
                return None
        except Exception as e:
            # If description fails, return None
            logger.error(f"[vLLM] vLLM vision model failed to describe image: {e}")
            logger.error(f"[vLLM] Image URL: {image_url[:100] if image_url else 'None'}")
            import traceback

            traceback.print_exc()
            return None

    def infer_article_opinion(
        self, article_content: str, topic_name: str, opinion_groups: dict
    ) -> float:
        """Infer opinion on a topic from article content using discrete opinion categories."""
        try:
            config = self.prompts_config.get("infer_article_opinion", {})
            system_template = config.get(
                "system_template",
                "You are an opinion classification assistant. Analyze articles and determine their stance on topics.",
            )
            user_template = config.get(
                "user_template",
                "Analyze this article and determine its stance on the topic '{topic}'.\n\n"
                + "Article excerpt:\n{article_text}\n\n"
                + "What is the article's stance? Choose ONLY ONE from these options:\n{opinion_options}\n\n"
                + "Your choice (ONE WORD ONLY):",
            )

            opinion_options = "\n".join([f"- {label}" for label in opinion_groups.keys()])
            article_excerpt = (
                article_content[:1000] if len(article_content) > 1000 else article_content
            )

            prompt = self._format_prompt(system_template, user_template)
            prompt = (
                prompt.replace("{topic}", topic_name)
                .replace("{article_text}", article_excerpt)
                .replace("{opinion_options}", opinion_options)
            )

            outputs = self.llm.generate([prompt], self.sampling_params)
            response = outputs[0].outputs[0].text.strip()

            response_lower = response.lower()
            selected_group = None
            for label in opinion_groups.keys():
                if label.lower() in response_lower:
                    selected_group = label
                    break

            if selected_group and selected_group in opinion_groups:
                range_values = opinion_groups[selected_group]
                opinion_value = (range_values[0] + range_values[1]) / 2.0
                return opinion_value
            else:
                import random

                return random.random()

        except Exception:
            import random

            return random.random()

    def generate_image_commentary(
        self,
        image_description: str,
        topics: List[str] = None,
        agent_attrs: dict = None,
        cluster_id: int = 0,
    ) -> str:
        """Generate commentary for sharing an image on social media."""
        persona = self._build_persona(cluster_id, agent_attrs)

        toxicity = ""
        if agent_attrs and "toxicity" in agent_attrs:
            toxicity_level = agent_attrs.get("toxicity", "").lower()
            if toxicity_level in ["low", "medium", "high"]:
                toxicity = toxicity_level

        topics_instruction = ""
        if topics:
            topics_str = ", ".join(topics)
            topics_instruction = f"Related topics: {topics_str}. "

        config = self.prompts_config.get("generate_image_commentary", {})
        system_template = config.get(
            "system_template", "{persona} You are sharing an image on social media."
        )
        user_template = config.get(
            "user_template",
            'You are sharing an image described as: "{image_description}"\n\n{topics_instruction}Write a brief, engaging post to share this image (max 280 characters).',
        )

        system_msg = system_template.format(persona=persona, toxicity=toxicity)
        user_msg = user_template.format(
            image_description=image_description, topics_instruction=topics_instruction
        )

        prompt = self._format_prompt(system_msg, user_msg)

        try:
            outputs = self.llm.generate([prompt], self.sampling_params)
            commentary = outputs[0].outputs[0].text.strip()
            return commentary if commentary else "IMAGE"
        except Exception as e:
            logger.error(f"Failed to generate image commentary: {e}")
            return "IMAGE"

    def evaluate_opinion(
        self,
        agent_opinion: str,
        author_opinion: str,
        post_text: str,
        topic: str,
        peers_opinions: list = None,
    ) -> str:
        """Evaluate how an agent's opinion should change after reading a post."""
        prompt_text = (
            f"Read the following text on the topic '{topic.upper()}': '{post_text}'.\n"
            f"The author has opinion '{author_opinion}' on the topic.\n"
            f"Your initial opinion is '{agent_opinion}'"
        )

        if peers_opinions and len(peers_opinions) > 0:
            prompt_text += "\n\nThe following are the opinions of your friends:\n"
            for op, count in peers_opinions:
                prompt_text += f"Opinion: '{op}' ({count})\n"

        prompt_text += (
            "\nWhat do you think about the expressed opinion? "
            "Answer with a single word among the options: AGREE|DISAGREE|NEUTRAL."
        )

        system_template = self.prompts_config.get("evaluate_opinion", {}).get(
            "system_template",
            "You are evaluating opinions on various topics. Consider the content and opinions presented.",
        )

        prompt = self._format_prompt(system_template, prompt_text)

        try:
            outputs = self.llm.generate([prompt], self.sampling_params)
            response = outputs[0].outputs[0].text.strip().upper()

            if "AGREE" in response:
                return "AGREE"
            elif "DISAGREE" in response:
                return "DISAGREE"
            elif "NEUTRAL" in response:
                return "NEUTRAL"

            return "NEUTRAL"
        except Exception as e:
            logger.error(f"Failed to evaluate opinion: {e}")
            return "NEUTRAL"
