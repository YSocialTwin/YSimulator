#!/usr/bin/env python3
"""
Generate a population of 10000 agents (10000 LLM, 0 rule-based) and 1 page agent
with an initial random social network (total: 10001 agents).

This example uses vLLM backend with opinion dynamics (llm_evaluation),
sentiment annotation, and emotion annotation enabled.
"""

import json
import random
import uuid

# Set seed for reproducibility
random.seed(42)


def generate_agent_population():
    """Generate 10000 agents and 1 page agent."""
    agents = []

    # 1 Page agent (always LLM-enabled) - Fox News
    page_agent = {
        "id": str(uuid.uuid5(uuid.NAMESPACE_DNS, "FoxNewsPage")),
        "username": "FoxNewsPage",
        "email": "news@foxnews.local",
        "leaning": "right",
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
        "feed_url": "https://moxie.foxnews.com/google-publisher/latest.xml",
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

    # Professions
    professions = [
        "Software Engineer",
        "Teacher",
        "Doctor",
        "Artist",
        "Student",
        "Lawyer",
        "Journalist",
        "Entrepreneur",
        "Scientist",
        "Nurse",
        "Accountant",
        "Designer",
    ]

    # Generate 10000 agents
    for i in range(10000):
        # All agents are LLM-enabled
        is_llm = True

        username = f"agent_{i:05d}"
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
            "education_level": random.choice(
                ["high_school", "undergraduate", "graduate"]
            ),
            "gender": random.choice(["male", "female", "other"]),
            "nationality": "US",
            "profession": random.choice(professions),
            "activity_profile": activity_profile,
            "archetype": archetype,
            "cluster": cluster,
            "llm": is_llm,
            "toxicity": "no",
            "daily_activity_level": daily_activity_level,
            "round_actions": round_actions,
            "is_page": 0,
            "feed_url": None,
            "recsys_type": random.choice(recsys_types),
            "frecsys_type": random.choice(frecsys_types),
            "interests": random.choice(interests_options),
        }
        agents.append(agent)

    return {"agents": agents}


def generate_social_network(num_agents, avg_degree=10):
    """Generate a random social network using Erdős–Rényi model."""
    # Total agents including 1 page
    total_agents = num_agents + 1
    
    # Calculate edge probability for desired average degree
    p = avg_degree / (total_agents - 1)
    
    edges = []
    
    # Generate random edges
    for i in range(total_agents):
        for j in range(total_agents):
            if i != j and random.random() < p:
                edges.append((i, j))
    
    return edges


def main():
    """Generate agent population and social network."""
    print("Generating 10001 agents (10000 LLM + 1 page)...")
    population = generate_agent_population()
    
    with open("agent_population.json", "w") as f:
        json.dump(population, f, indent=2)
    print(f"✓ Created agent_population.json ({len(population['agents'])} agents)")
    
    print("\nGenerating social network...")
    edges = generate_social_network(10000, avg_degree=10)
    
    with open("network.csv", "w") as f:
        f.write("source,target\n")
        for source, target in edges:
            f.write(f"{source},{target}\n")
    print(f"✓ Created network.csv ({len(edges)} edges)")
    
    print("\n✓ Generation complete!")
    print("\nNext steps:")
    print("1. Start server: python run_server.py --config example/llm_population_10000_vllm")
    print("2. Start client: python run_client.py --config example/llm_population_10000_vllm")


if __name__ == "__main__":
    main()
