import ray
import requests
import uuid
import random

from test_shared.schemas import AgentConfig, ContentPost, LikeAction

SERVER_URL = "http://127.0.0.1:5000"


# --- 2. LOGIC LAYER (Hybrid ABM + LLM) ---
@ray.remote
class SimAgent:
    def __init__(self, name: str, behavior_type: str, llm_pool: list):
        self.config = AgentConfig(
            uuid=str(uuid.uuid4()),
            name=name,
            behavior_type=behavior_type,
            ip_address=ray.util.get_node_ip_address()
        )
        self.llm_pool = llm_pool
        self._register()

    def _register(self):
        try:
            requests.post(f"{SERVER_URL}/register", json=self.config.to_dict())
        except Exception:
            pass

    async def _do_post(self, iteration: int):
        """
        Hybrid Logic:
        - If Broadcaster -> Call GPU Actor (Async/Await)
        - If Others -> Return Static Text (Instant)
        """
        if self.config.behavior_type == "Broadcaster":
            # --- EXPENSIVE PATH (LLM) ---
            worker = self.llm_pool[iteration % len(self.llm_pool)]
            try:
                content = await worker.generate_broadcast.remote(iteration)
                status = "POSTED (LLM)"
            except Exception as e:
                content = f"[Error] {e}"
                status = "ERR"

        else:
            # --- CHEAP PATH (Standard ABM) ---
            # Standard agents just output data/logs
            if self.config.behavior_type == "Validator":
                content = f"[Log] System validated at iter {iteration}. All checks passed."
            else:  # Explorer
                content = f"[Log] New connection node discovered at iter {iteration}."

            status = "POSTED (Text)"

        # Send to Server
        post = ContentPost(self.config.uuid, iteration, content)
        requests.post(f"{SERVER_URL}/post_content", json=post.to_dict())
        return f"{self.config.name}: {status}"

    async def _do_like(self, iteration: int):
        """
        Refined Logic:
        - Broadcasters: LLM reads post -> Decides (Like/Dislike/Ignore)
        - Others: Randomly Like or Dislike
        """
        try:
            # 1. Fetch Feed
            resp = requests.get(f"{SERVER_URL}/feed")
            feed = resp.json()
            if not feed: return f"{self.config.name}: SKIP (Empty Feed)"

            # 2. Pick a Target Post
            target_post = random.choice(feed)
            post_id = target_post['id']
            post_body = target_post['content_body']

            # 3. Decision Logic
            if self.config.behavior_type == "Broadcaster":
                # --- INTELLIGENT DECISION (LLM) ---
                worker = self.llm_pool[iteration % len(self.llm_pool)]
                try:
                    # Ask GPU worker to read the text
                    decision = await worker.evaluate_content.remote(post_body)
                except Exception:
                    decision = "ignore"  # Fallback on error

                if decision == "ignore":
                    return f"{self.config.name}: READ Post #{post_id} -> IGNORED"

                action_type = decision  # "like" or "dislike"

            else:
                # --- RANDOM DECISION (Standard Agents) ---
                # 50/50 Chance to like or dislike
                action_type = random.choice(["like", "dislike"])

            # 4. Send Reaction to Server
            like_action = LikeAction(
                agent_uuid=self.config.uuid,
                post_id=post_id,
                iteration=iteration,
                action_type=action_type
            )
            requests.post(f"{SERVER_URL}/like", json=like_action.to_dict())

            return f"{self.config.name}: {action_type.upper()} Post #{post_id}"

        except Exception as e:
            return f"{self.config.name}: REACTION FAILED ({str(e)})"

    async def act(self, iteration: int):
        """
        Decide action based on Persona Probabilities.
        """
        dice_roll = random.random()

        # 1. Broadcaster: Loves to Post (80%), rarely Likes
        if self.config.behavior_type == "Broadcaster":
            action = "like" if dice_roll < 0.2 else "post"

        # 2. Validator: Loves to Like (70%), rarely Posts
        elif self.config.behavior_type == "Validator":
            action = "like" if dice_roll < 0.7 else "post"

        # 3. Explorer: Balanced (50/50)
        else:
            action = "like" if dice_roll < 0.5 else "post"

        if action == "post":
            return await self._do_post(iteration)
        else:
            return await self._do_like(iteration)
