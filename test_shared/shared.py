import ray
import sqlite3
import random
import asyncio
import numpy as np


# --- 1. SHARED DATABASE ACTOR ---
@ray.remote
class DbWriter:
    def __init__(self):
        self.conn = sqlite3.connect("shared_simulation.db")
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")
        self._init_tables()
        print("💾 Global DB Writer Started")

    def _init_tables(self):
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY, uuid TEXT, hour INTEGER, content TEXT)")
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS likes (id INTEGER PRIMARY KEY, uuid TEXT, post_id INTEGER, hour INTEGER, type TEXT)")
        self.conn.execute("CREATE TABLE IF NOT EXISTS logs (id INTEGER PRIMARY KEY, msg TEXT, hour INTEGER)")
        self.conn.commit()

    def write_batch(self, posts, likes):
        if posts: self.conn.executemany("INSERT INTO posts (uuid, hour, content) VALUES (?, ?, ?)", posts)
        if likes: self.conn.executemany("INSERT INTO likes (uuid, post_id, hour, type) VALUES (?, ?, ?, ?)", likes)
        self.conn.commit()

    def log(self, msg, hour):
        self.conn.execute("INSERT INTO logs (msg, hour) VALUES (?, ?)", (msg, hour))
        self.conn.commit()

    def get_feed(self, limit=50):
        # Return list of (id, content)
        return self.conn.execute("SELECT id, content FROM posts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    def get_stats(self):
        p = self.conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        l = self.conn.execute("SELECT COUNT(*) FROM likes").fetchone()[0]
        return p, l


# --- 2. TIME KEEPER ACTOR ---
@ray.remote
class TimeKeeper:
    def __init__(self):
        self.hour = 0

    def get_time(self): return self.hour

    def advance(self):
        self.hour = (self.hour + 1) % 24
        return self.hour


# --- 3. GPU/LLM SERVICE ---
@ray.remote(num_gpus=0.25)
class LLMService:
    def __init__(self): pass

    async def generate(self):
        await asyncio.sleep(0.02)  # Simulate thinking
        return "🔥 Viral Post"

    async def evaluate(self, text):
        return "like" if random.random() > 0.5 else "ignore"


# --- 4. AGENT BATCH (The Logic Engine) ---
@ray.remote
class AgentBatch:
    def __init__(self, start_id, size, llm_names, db_name):
        self.start_id = start_id
        self.size = size
        self.llm_names = llm_names  # List of strings ["LLM_0", "LLM_1"]
        self.db_name = db_name

        # Connect to DB Actor (Look up by name)
        self.db_actor = ray.get_actor(db_name)

        # Connect to LLM Actors
        self.llm_pool = [ray.get_actor(name) for name in llm_names]

        # Logic: 20% Broadcasters
        self.is_broadcaster = np.random.rand(size) < 0.20

    async def run_hour(self, hour, activation_rate=0.03):
        # 1. Vectorized Activation
        active_mask = np.random.rand(self.size) < activation_rate
        active_indices = np.where(active_mask)[0]
        if len(active_indices) == 0: return (0, 0)

        # 2. Fetch Feed
        try:
            feed = await self.db_actor.get_feed.remote()
        except:
            feed = []

        batch_posts = []
        batch_likes = []
        gpu_tasks = []

        for idx in active_indices:
            uuid = f"user_{self.start_id + idx}"
            broadcaster = self.is_broadcaster[idx]
            dice = random.random()

            # --- LOGIC ---
            if broadcaster:
                if dice < 0.8:  # Post
                    worker = random.choice(self.llm_pool)
                    # We append 3 items here: UUID, Action, Future
                    gpu_tasks.append((uuid, "post", worker.generate.remote()))
                else:  # Like
                    if feed:
                        target = random.choice(feed)
                        worker = random.choice(self.llm_pool)
                        # We append 3 items here too
                        gpu_tasks.append((uuid, f"eval:{target[0]}", worker.evaluate.remote(target[1])))
            else:
                # Standard Agent logic (Unchanged)
                if dice < 0.1:
                    batch_posts.append((uuid, hour, "Standard log"))
                elif dice < 0.6 and feed:
                    target = random.choice(feed)
                    batch_likes.append((uuid, target[0], hour, random.choice(["like", "dislike"])))

        if gpu_tasks:
            uuids, actions, futures = zip(*gpu_tasks)

            results = await asyncio.gather(*futures)

            for i, res in enumerate(results):
                uuid = uuids[i]
                action = actions[i]

                if action == "post":
                    batch_posts.append((uuid, hour, res))
                elif action.startswith("eval"):
                    if res != "ignore":
                        post_id = int(action.split(":")[1])
                        batch_likes.append((uuid, post_id, hour, res))

        # 4. Write
        if batch_posts or batch_likes:
            self.db_actor.write_batch.remote(batch_posts, batch_likes)

        return len(batch_posts), len(batch_likes)