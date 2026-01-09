#!/usr/bin/env python3
"""
Generate a population of 5000 agents (0 LLM, 5000 rule-based) and 1 page agent
with an initial random social network (total: 5001 agents).
"""

import json
import random
import uuid

# Set seed for reproducibility
random.seed(42)


def generate_agent_population():
    """Generate 5000 agents and 1 page agent."""
    agents = []

    # 1 Page agent (always LLM-enabled)
    page_agent = {
        "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, "NewsPage")),
        "username": "NewsPage",
        "email": "news@pages.local",
        "leaning": "neutral",
        "user_type": "page",
        "age": 0,
        "language": "en",
        "education_level": "graduate",
        "gender": "other",
        "nationality": "US",
        "profession": "News Publisher",
        "activity_profile": "Always On",
        "archetype": None,
        "cluster": 0,
        "llm": True,
        "toxicity": "no",
        "daily_activity_level": 4,
        "round_actions": 6,
        "is_page": 1,
        "feed_url": "https://techcrunch.com/feed/",
        "recsys_type": "random",
        "frecsys_type": "random",
        "interests": [["News", "Current Events", "Information"], [10, 10, 8]],
    }
    agents.append(page_agent)

    # Archetypes distribution
    archetypes = ["validator", "broadcaster", "explorer"]

    # Political leanings
    leanings = ["left", "center", "right", "neutral"]

    # Activity profiles
    activity_profiles = ["Always On", "Morning Active", "Evening Active"]

    # Recommendation systems
    recsys_types = ["random", "rchrono", "rchrono_followers"]
    frecsys_types = [
        "random",
        "common_neighbors",
        "jaccard",
        "adamic_adar",
        "preferential_attachment",
    ]

    # Interest topics for agents
    interests_options = [
        (["Analysis", "Facts", "Verification"], [7, 5, 4]),
        (["Learning", "Education", "Technology"], [5, 5, 2]),
        (["News", "Trends", "Engagement"], [8, 6, 5]),
        (["Discovery", "Learning", "Curiosity"], [8, 5, 5]),
        (["Education", "Learning", "Teaching"], [8, 6, 4]),
    ]

    # Generate 5000 agents
    for i in range(5000):
        # First 5000 are rule-based, next 0 are LLM
        is_llm = i >= 5000

        username = f"agent_{i:04d}"
        agent_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, username))

        # Distribute across archetypes evenly
        archetype = archetypes[i % 3]
        cluster = i % 3

        # Random attributes
        age = random.randint(18, 65)
        leaning = random.choice(leanings)
        activity_profile = random.choice(activity_profiles)
        daily_activity_level = random.randint(1, 3)
        round_actions = random.randint(2, 5)

        agent = {
            "id": agent_id,
            "username": username,
            "email": f"{username}@simulation.local",
            "leaning": leaning,
            "user_type": "agent",
            "age": age,
            "language": "en",
            "education_level": random.choice(["high_school", "college", "graduate"]),
            "gender": random.choice(["male", "female", "other"]),
            "nationality": random.choice(["US", "UK", "CA", "AU"]),
            "profession": random.choice(["Engineer", "Teacher", "Doctor", "Artist", "Student"]),
            "activity_profile": activity_profile,
            "archetype": archetype,
            "cluster": cluster,
            "llm": is_llm,
            "toxicity": "no",
            "daily_activity_level": daily_activity_level,
            "round_actions": round_actions,
            "is_page": 0,
            "recsys_type": random.choice(recsys_types),
            "frecsys_type": random.choice(frecsys_types),
            "interests": random.choice(interests_options),
        }
        agents.append(agent)

    return {
        "agents": agents,
        "generation_config": {
            "num_additional_agents": 0,
            "cluster_distribution": {"weights": [0.33, 0.33, 0.34]},
            "llm_enabled_probability": 0.0,
            "age_range": [18, 65],
            "default_settings": {
                "leaning": "neutral",
                "user_type": "agent",
                "language": "en",
                "toxicity": "no",
                "password": "simulation_agent",
                "education_level": "college",
                "round_actions": 3,
                "is_page": 0,
                "recsys_type": "random",
                "frecsys_type": "random",
            },
        },
    }


def generate_random_network(agents, avg_degree=10):
    """
    Generate a random social network with approximately avg_degree connections per node.
    Uses Erdős–Rényi random graph model.
    """
    edges = []
    usernames = [agent["username"] for agent in agents]
    n = len(usernames)

    # Calculate probability for desired average degree
    # avg_degree ≈ p * (n - 1), so p = avg_degree / (n - 1)
    p = avg_degree / (n - 1) if n > 1 else 0

    # Generate edges
    for i, follower in enumerate(usernames):
        for j, followee in enumerate(usernames):
            if i != j and random.random() < p:
                edges.append((follower, followee))

    return edges


def write_network_csv(edges, filepath):
    """Write network edges to CSV file."""
    with open(filepath, "w") as f:
        for follower, followee in edges:
            f.write(f"{follower},{followee}\n")


def generate_simulation_config():
    """Generate simulation configuration with discussion topics."""
    return {
        "client_name": "client_1",
        "namespace": "social_sim",
        "server": {"address": None, "port": None},
        "llm": {
            "address": "localhost",
            "port": 11434,
            "model": "llama3.2",
            "temperature": 0.9,
            "llm_api_key": "NULL",
            "llm_max_tokens": -1,
        },
        "llm_v": {
            "address": "localhost",
            "port": 11434,
            "model": "minicpm-v",
            "temperature": 0.5,
            "llm_api_key": "NULL",
            "llm_max_tokens": 300,
        },
        "simulation": {
            "num_days": 3,
            "num_slots_per_day": 24,
            "heartbeat_interval": 5,
            "note": "num_days=0 means infinite simulation, set to a positive number to limit duration. heartbeat_interval in seconds (default: 5).",
            "percentage_new_agents_iteration": 0.0,
            "percentage_removed_agents_iteration": 0.0,
            "discussion_topics": ["war", "politics", "sport", "books", "movies"],
            "activity_profiles": {
                "Always On": "0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23",
                "Morning Active": "6,7,8,9,10,11,12",
                "Evening Active": "17,18,19,20,21,22,23",
                "Weekend Warrior": "0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23",
            },
            "hourly_activity": {
                "0": 0.023,
                "1": 0.021,
                "2": 0.02,
                "3": 0.02,
                "4": 0.018,
                "5": 0.017,
                "6": 0.017,
                "7": 0.018,
                "8": 0.02,
                "9": 0.02,
                "10": 0.021,
                "11": 0.022,
                "12": 0.024,
                "13": 0.027,
                "14": 0.03,
                "15": 0.032,
                "16": 0.032,
                "17": 0.032,
                "18": 0.032,
                "19": 0.031,
                "20": 0.03,
                "21": 0.029,
                "22": 0.027,
                "23": 0.025,
            },
            "actions_likelihood": {
                "post": 3.0,
                "image": 0.0,
                "news": 0.0,
                "comment": 5.0,
                "read": 2.0,
                "share": 1.0,
                "search": 5.0,
                "cast": 0.0,
                "share_link": 0.0,
                "follow": 0.1,
            },
            "agent_archetypes": {
                "enabled": True,
                "distribution": {"validator": 0.33, "broadcaster": 0.33, "explorer": 0.34},
            },
            "emotion_annotation": False,
        },
        "agents": {
            "reading_from_follower_ratio": 0.6,
            "max_length_thread_reading": 5,
            "attention_window": 336,
            "probability_of_daily_follow": 0.1,
            "probability_of_secondary_follow": 0.1,
        },
    }


def generate_server_config():
    """Generate server configuration."""
    return {
        "server_name": "orchestrator_server",
        "namespace": "social_sim",
        "address": "auto",
        "port": None,
        "database": {
            "type": "sqlite",
            "sqlite": {"filename": "simulation.db"},
            "postgresql": {
                "host": "localhost",
                "port": 5432,
                "database": "ysimulator",
                "username": "postgres",
                "password": "password",
            },
            "mysql": {
                "host": "localhost",
                "port": 3306,
                "database": "ysimulator",
                "username": "root",
                "password": "password",
            },
        },
        "min_to_start": 1,
        "timeout_seconds": 180,
        "redis": {
            "enabled": False,
            "host": "localhost",
            "port": 6379,
            "db": 0,
            "password": None,
            "sliding_window_days": 2,
        },
        "posts": {"visibility_rounds": 36},
        "simulation": {
            "agent_archetypes": {
                "enabled": True,
                "distribution": {"validator": 0.33, "broadcaster": 0.33, "explorer": 0.34},
                "transitions": {
                    "validator": {"validator": 0.85, "broadcaster": 0.10, "explorer": 0.05},
                    "broadcaster": {"validator": 0.10, "broadcaster": 0.80, "explorer": 0.10},
                    "explorer": {"validator": 0.05, "broadcaster": 0.10, "explorer": 0.85},
                },
            }
        },
    }


def main():
    """Generate all configuration files."""
    import os

    output_dir = os.path.dirname(os.path.abspath(__file__))

    print("Generating agent population...")
    agent_data = generate_agent_population()

    with open(os.path.join(output_dir, "agent_population.json"), "w") as f:
        json.dump(agent_data, f, indent=2)
    print(f"✓ Created agent_population.json with {len(agent_data['agents'])} agents")
    print("  - 1 page agent (LLM-enabled)")
    print("  - 0 LLM-enabled agents")
    print("  - 5000 rule-based agents")

    print("\nGenerating random social network...")
    edges = generate_random_network(agent_data["agents"], avg_degree=10)
    network_path = os.path.join(output_dir, "network.csv")
    write_network_csv(edges, network_path)
    print(f"✓ Created network.csv with {len(edges)} follow relationships")
    print(
        f"  - Average degree: ~{len(edges) /
                                  len(agent_data['agents']):.1f} connections per agent"
    )

    print("\nGenerating simulation configuration...")
    sim_config = generate_simulation_config()
    with open(os.path.join(output_dir, "simulation_config.json"), "w") as f:
        json.dump(sim_config, f, indent=2)
    print("✓ Created simulation_config.json")

    print("\nGenerating server configuration...")
    server_config = generate_server_config()
    with open(os.path.join(output_dir, "server_config.json"), "w") as f:
        json.dump(server_config, f, indent=2)
    print("✓ Created server_config.json")

    print("\n" + "=" * 60)
    print("Configuration generation complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
