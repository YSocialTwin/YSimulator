#!/usr/bin/env python3
"""
Generate a multi-client experiment with 4 clients, each managing 10000 LLM agents.
Total: 40004 agents (40000 agents + 4 page agents, one per client).

This script creates:
- 4 separate agent population files (one per client)
- 4 simulation_config files with unique client names
- 1 shared network topology (network.csv)
- 1 server configuration
"""

import json
import os
import random
import uuid

# Set seed for reproducibility
random.seed(42)


def generate_agent_population(client_id, start_idx, num_agents=10000):
    """
    Generate agent population for a specific client.

    Args:
        client_id: Client identifier (1-4)
        start_idx: Starting index for agent numbering
        num_agents: Number of agents to generate (default: 10000)

    Returns:
        Dict with agents and generation config
    """
    agents = []

    # 1 Page agent per client (always LLM-enabled)
    page_agent = {
        "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"NewsPage_Client{client_id}")),
        "username": f"NewsPage_Client{client_id}",
        "email": f"news{client_id}@pages.local",
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

    # Generate agents for this client
    for i in range(num_agents):
        agent_idx = start_idx + i
        is_llm = True  # All agents are LLM-enabled

        username = f"agent_{agent_idx:05d}"
        agent_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, username))

        # Distribute across archetypes evenly
        archetype = archetypes[agent_idx % 3]
        cluster = agent_idx % 3

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
            "llm_enabled_probability": 1.0,
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


def generate_shared_network(all_agents, avg_degree=10):
    """
    Generate a shared random social network across all clients.
    Uses Erdős–Rényi random graph model.

    Args:
        all_agents: List of all agents from all clients
        avg_degree: Average number of connections per agent

    Returns:
        List of tuples (follower, followee)
    """
    edges = []
    usernames = [agent["username"] for agent in all_agents]
    n = len(usernames)

    # Calculate probability for desired average degree
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


def generate_simulation_config(client_id):
    """
    Generate simulation configuration for a specific client with vLLM backend.

    Args:
        client_id: Client identifier (1-4)

    Returns:
        Dict with simulation configuration
    """
    return {
        "client_name": f"client_{client_id}",
        "namespace": "social_sim",
        "server": {"address": None, "port": None},
        "llm": {
            "backend": "vllm",
            "model": "AMead10/Llama-3.2-3B-Instruct-AWQ",
            "temperature": 0.9,
            "max_tokens": 256,
            "max_model_len": 4096,
            "tensor_parallel_size": 1,
            "gpu_memory_utilization": 0.15,
            "enable_flashattention": False,
            "num_actors": 4,
            "gpu_per_actor": 1,
            "reuse_actors": False,
            "actor_name_prefix": f"ysim_llm_client{client_id}",
            "note": "FlashAttention disabled by default (requires GPU compute capability >= 8.0). Set to true to enable on compatible GPUs. max_model_len sets the maximum sequence length (default: 40000). num_actors specifies how many vLLM instances to start for parallel processing (default: 1). With 4 actors, achieve ~30x speedup vs sequential Ollama. gpu_per_actor specifies GPU allocation per actor (default: 1.0). Set to 0.25 to fit 4 actors on 1 GPU, or 0.5 for 2 actors per GPU. reuse_actors (default: false) allows clients to share existing vLLM instances on the same machine - set to true to reuse actors from another client. actor_name_prefix is unique per client to avoid conflicts.",
        },
        "llm_v": {
            "model": "openbmb/MiniCPM-V-2_6-int4",
            "temperature": 0.5,
            "max_tokens": 300,
            "max_model_len": 4096,
            "gpu_memory_utilization": 0.15,
            "note": "max_model_len sets the maximum sequence length for the vision model (default: 40000).",
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
                "agent_downcast": True,
                "distribution": {"validator": 0.33, "broadcaster": 0.33, "explorer": 0.34},
            },
            "enable_sentiment": True,
            "emotion_annotation": True,
            "enable_toxicity": False,
            "perspective_api_key": None,
        },
        "agents": {
            "reading_from_follower_ratio": 0.6,
            "max_length_thread_reading": 5,
            "attention_window": 336,
            "probability_of_daily_follow": 0.1,
            "probability_of_secondary_follow": 0.1,
            "follow_action_decay": {
                "enabled": False,
                "decay_function": "exponential",
                "half_life_rounds": 168,
                "decay_rate": 0.01,
                "min_probability_ratio": 0.1,
            },
            "batch_size": 100,
            "churn": {
                "enabled": True,
                "churn_probability": 0.01,
                "inactivity_threshold": 5,
                "churn_percentage": 0.1,
            },
            "new_agents": {
                "enabled": True,
                "probability_new_agents": 0.01,
                "percentage_new_agents": 0.01,
            },
        },
        "logging": {
            "enable_execution_log": True,
            "enable_actor_log": True,
            "enable_client_log": True,
            "enable_console_log": True,
            "enable_llm_usage_log": True,
        },
        "opinion_dynamics": {
            "enabled": True,
            "model_name": "llm_evaluation",
            "note": "Uses LLM-based opinion evaluation with natural language reasoning. Requires LLM agents.",
            "parameters": {
                "evaluation_scope": "neighbors",
                "cold_start": "neutral",
                "note": "evaluation_scope='neighbors' considers opinions of followed users. cold_start='neutral' initializes new opinions at 0.5.",
            },
            "opinion_groups": {
                "Strongly against": [0.0, 0.2],
                "Against": [0.2, 0.4],
                "Neutral": [0.4, 0.6],
                "In favor": [0.6, 0.8],
                "Strongly in favor": [0.8, 1.0],
            },
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
        "min_to_start": 1,  # Allow clients to start sequentially (enables GPU actor reuse)
        "timeout_seconds": 300,  # Increased timeout for large network
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
        "logging": {
            "enable_server_log": True,
            "enable_actor_log": True,
            "enable_request_log": True,
            "enable_console_log": True,
        },
    }


def main():
    """Generate all configuration files for multi-client experiment."""
    output_dir = os.path.dirname(os.path.abspath(__file__))

    print("=" * 70)
    print("Generating Multi-Client Experiment Configuration")
    print("4 Clients × 10,000 Agents = 40,000 Total Agents (+ 4 page agents)")
    print("=" * 70)

    all_agents = []

    # Generate agent populations for each client
    for client_id in range(1, 5):
        print(f"\nGenerating agent population for client_{client_id}...")
        start_idx = (client_id - 1) * 10000
        agent_data = generate_agent_population(client_id, start_idx, num_agents=10000)

        # Save agent population
        filename = f"client_{client_id}_agent_population.json"
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w") as f:
            json.dump(agent_data, f, indent=2)

        print(f"✓ Created {filename}")
        print(f"  - 1 page agent (NewsPage_Client{client_id})")
        print(
            f"  - 10,000 LLM-enabled agents (agent_{start_idx:05d} to agent_{start_idx+9999:05d})"
        )

        all_agents.extend(agent_data["agents"])

        # Generate simulation config for this client
        print(f"  Generating simulation configuration for client_{client_id}...")
        sim_config = generate_simulation_config(client_id)
        sim_filename = f"client_{client_id}_simulation_config.json"
        sim_filepath = os.path.join(output_dir, sim_filename)
        with open(sim_filepath, "w") as f:
            json.dump(sim_config, f, indent=2)
        print(f"✓ Created {sim_filename}")

    # Generate shared network topology
    print("\n" + "=" * 70)
    print("Generating shared social network topology...")
    print("This may take a few minutes for 40,004 agents...")
    edges = generate_shared_network(all_agents, avg_degree=10)
    network_path = os.path.join(output_dir, "network.csv")
    write_network_csv(edges, network_path)
    print(f"✓ Created network.csv with {len(edges)} follow relationships")
    print(f"  - Average degree: ~{len(edges) / len(all_agents):.1f} connections per agent")

    # Generate server configuration
    print("\nGenerating server configuration...")
    server_config = generate_server_config()
    server_filepath = os.path.join(output_dir, "server_config.json")
    with open(server_filepath, "w") as f:
        json.dump(server_config, f, indent=2)
    print("✓ Created server_config.json")
    print("  - Configured to wait for 4 clients before starting")
    print("  - Timeout increased to 300 seconds for network loading")

    print("\n" + "=" * 70)
    print("Configuration generation complete!")
    print("=" * 70)
    print("\nGenerated files:")
    print("  - 4 × client_N_agent_population.json (agent definitions)")
    print("  - 4 × client_N_simulation_config.json (client configurations)")
    print("  - 1 × network.csv (shared social network)")
    print("  - 1 × server_config.json (server settings)")
    print("\nNext steps:")
    print("  1. Copy prompts.json from another example (e.g., llm_population_10000)")
    print("  2. Start the server: python run_server.py --config example/llm_4clients_40000")
    print("  3. Start each client in parallel (see README.md for details)")


if __name__ == "__main__":
    main()
