#!/usr/bin/env python3
"""
Generate all population examples for YSimulator.
Creates variations with different population sizes and LLM/rule-based ratios.
"""

import os
import sys
import shutil
import json
import subprocess

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Configuration for all populations to generate
POPULATIONS = [
    # LLM populations (all agents are LLM-enabled)
    {"name": "llm_population_100", "total": 100, "llm_ratio": 1.0, "type": "llm"},
    {"name": "llm_population_5000", "total": 5000, "llm_ratio": 1.0, "type": "llm"},
    {"name": "llm_population_10000", "total": 10000, "llm_ratio": 1.0, "type": "llm"},
    # Mixed populations (50% LLM, 50% rule-based)
    {"name": "mixed_population_1000", "total": 1000, "llm_ratio": 0.5, "type": "mixed"},
    {"name": "mixed_population_5000", "total": 5000, "llm_ratio": 0.5, "type": "mixed"},
    {"name": "mixed_population_10000", "total": 10000, "llm_ratio": 0.5, "type": "mixed"},
    # Rule-based populations (all agents are rule-based)
    {"name": "rule_population_100", "total": 100, "llm_ratio": 0.0, "type": "rule"},
    {"name": "rule_population_1000", "total": 1000, "llm_ratio": 0.0, "type": "rule"},
    {"name": "rule_population_5000", "total": 5000, "llm_ratio": 0.0, "type": "rule"},
    {"name": "rule_population_10000", "total": 10000, "llm_ratio": 0.0, "type": "rule"},
]


def get_blueprint_dir(pop_type):
    """Get the blueprint directory based on population type."""
    if pop_type == "llm":
        return "llm_population_1000"
    elif pop_type == "mixed":
        return "mixed_population_100"
    else:  # rule
        return "mixed_population_100"  # We'll modify it to be rule-based


def create_population_directory(example_dir, pop_config):
    """Create directory structure for a population example."""
    pop_dir = os.path.join(example_dir, pop_config["name"])

    # Create directory if it doesn't exist
    os.makedirs(pop_dir, exist_ok=True)

    print(f"\nCreating {pop_config['name']}...")
    print(f"  Total agents: {pop_config['total']}")
    print(f"  LLM ratio: {pop_config['llm_ratio']}")

    return pop_dir


def copy_static_files(source_dir, dest_dir, pop_config):
    """Copy static configuration files from blueprint."""
    # Files that don't need modification
    static_files = ["llm_prompts.json", "prompts.json"]

    # Only copy LLM prompts if population has LLM agents
    if pop_config["llm_ratio"] == 0.0:
        static_files = ["prompts.json"]

    for filename in static_files:
        src = os.path.join(source_dir, filename)
        dst = os.path.join(dest_dir, filename)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            print(f"  ✓ Copied {filename}")


def create_generate_script(dest_dir, pop_config):
    """Create the generate_population.py script for this configuration."""
    total = pop_config["total"]
    llm_ratio = pop_config["llm_ratio"]
    llm_count = int(total * llm_ratio)
    rule_count = total - llm_count

    script_content = f'''#!/usr/bin/env python3
"""
Generate a population of {total} agents ({llm_count} LLM, {rule_count} rule-based) and 1 page agent
with an initial random social network (total: {total + 1} agents).
"""

import json
import random
import uuid

# Set seed for reproducibility
random.seed(42)

def generate_agent_population():
    """Generate {total} agents and 1 page agent."""
    agents = []
    
    # 1 Page agent (always LLM-enabled)
    page_agent = {{
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
        "interests": [
            ["News", "Current Events", "Information"],
            [10, 10, 8]
        ]
    }}
    agents.append(page_agent)
    
    # Archetypes distribution
    archetypes = ["validator", "broadcaster", "explorer"]
    
    # Political leanings
    leanings = ["left", "center", "right", "neutral"]
    
    # Activity profiles
    activity_profiles = ["Always On", "Morning Active", "Evening Active"]
    
    # Recommendation systems
    recsys_types = ["random", "rchrono", "rchrono_followers"]
    frecsys_types = ["random", "common_neighbors", "jaccard", "adamic_adar", "preferential_attachment"]
    
    # Interest topics for agents
    interests_options = [
        (["Analysis", "Facts", "Verification"], [7, 5, 4]),
        (["Learning", "Education", "Technology"], [5, 5, 2]),
        (["News", "Trends", "Engagement"], [8, 6, 5]),
        (["Discovery", "Learning", "Curiosity"], [8, 5, 5]),
        (["Education", "Learning", "Teaching"], [8, 6, 4])
    ]
    
    # Generate {total} agents
    for i in range({total}):
        # First {rule_count} are rule-based, next {llm_count} are LLM
        is_llm = i >= {rule_count}
        
        username = f"agent_{{i:0{len(str(total))}d}}"
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
        
        agent = {{
            "id": agent_id,
            "username": username,
            "email": f"{{username}}@simulation.local",
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
            "interests": random.choice(interests_options)
        }}
        agents.append(agent)
    
    return {{
        "agents": agents,
        "generation_config": {{
            "num_additional_agents": 0,
            "cluster_distribution": {{
                "weights": [0.33, 0.33, 0.34]
            }},
            "llm_enabled_probability": {llm_ratio},
            "age_range": [18, 65],
            "default_settings": {{
                "leaning": "neutral",
                "user_type": "agent",
                "language": "en",
                "toxicity": "no",
                "password": "simulation_agent",
                "education_level": "college",
                "round_actions": 3,
                "is_page": 0,
                "recsys_type": "random",
                "frecsys_type": "random"
            }}
        }}
    }}

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
    with open(filepath, 'w') as f:
        for follower, followee in edges:
            f.write(f"{{follower}},{{followee}}\\n")

def generate_simulation_config():
    """Generate simulation configuration with discussion topics."""
    return {{
        "client_name": "client_1",
        "namespace": "social_sim",
        "server": {{
            "address": None,
            "port": None
        }},
        "llm": {{
            "address": "localhost",
            "port": 11434,
            "model": "llama3.2",
            "temperature": 0.9,
            "llm_api_key": "NULL",
            "llm_max_tokens": -1
        }},
        "llm_v": {{
            "address": "localhost",
            "port": 11434,
            "model": "minicpm-v",
            "temperature": 0.5,
            "llm_api_key": "NULL",
            "llm_max_tokens": 300
        }},
        "simulation": {{
            "num_days": 3,
            "num_slots_per_day": 24,
            "heartbeat_interval": 5,
            "note": "num_days=0 means infinite simulation, set to a positive number to limit duration. heartbeat_interval in seconds (default: 5).",
            "percentage_new_agents_iteration": 0.0,
            "percentage_removed_agents_iteration": 0.0,
            "discussion_topics": ["war", "politics", "sport", "books", "movies"],
            "activity_profiles": {{
                "Always On": "0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23",
                "Morning Active": "6,7,8,9,10,11,12",
                "Evening Active": "17,18,19,20,21,22,23",
                "Weekend Warrior": "0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23"
            }},
            "hourly_activity": {{
                "0": 0.023, "1": 0.021, "2": 0.02, "3": 0.02, "4": 0.018, "5": 0.017,
                "6": 0.017, "7": 0.018, "8": 0.02, "9": 0.02, "10": 0.021, "11": 0.022,
                "12": 0.024, "13": 0.027, "14": 0.03, "15": 0.032, "16": 0.032, "17": 0.032,
                "18": 0.032, "19": 0.031, "20": 0.03, "21": 0.029, "22": 0.027, "23": 0.025
            }},
            "actions_likelihood": {{
                "post": 3.0,
                "image": 0.0,
                "news": 0.0,
                "comment": 5.0,
                "read": 2.0,
                "share": 1.0,
                "search": 5.0,
                "cast": 0.0,
                "share_link": 0.0,
                "follow": 0.1
            }},
            "agent_archetypes": {{
                "enabled": True,
                "distribution": {{
                    "validator": 0.33,
                    "broadcaster": 0.33,
                    "explorer": 0.34
                }}
            }},
            "emotion_annotation": False
        }},
        "agents": {{
            "reading_from_follower_ratio": 0.6,
            "max_length_thread_reading": 5,
            "attention_window": 336,
            "probability_of_daily_follow": 0.1,
            "probability_of_secondary_follow": 0.1
        }}
    }}

def generate_server_config():
    """Generate server configuration."""
    return {{
        "server_name": "orchestrator_server",
        "namespace": "social_sim",
        "address": "auto",
        "port": None,
        "database": {{
            "type": "sqlite",
            "sqlite": {{
                "filename": "simulation.db"
            }},
            "postgresql": {{
                "host": "localhost",
                "port": 5432,
                "database": "ysimulator",
                "username": "postgres",
                "password": "password"
            }},
            "mysql": {{
                "host": "localhost",
                "port": 3306,
                "database": "ysimulator",
                "username": "root",
                "password": "password"
            }}
        }},
        "min_to_start": 1,
        "timeout_seconds": 180,
        "redis": {{
            "enabled": False,
            "host": "localhost",
            "port": 6379,
            "db": 0,
            "password": None,
            "sliding_window_days": 2
        }},
        "posts": {{
            "visibility_rounds": 36
        }},
        "simulation": {{
            "agent_archetypes": {{
                "enabled": True,
                "distribution": {{
                    "validator": 0.33,
                    "broadcaster": 0.33,
                    "explorer": 0.34
                }},
                "transitions": {{
                    "validator": {{
                        "validator": 0.85,
                        "broadcaster": 0.10,
                        "explorer": 0.05
                    }},
                    "broadcaster": {{
                        "validator": 0.10,
                        "broadcaster": 0.80,
                        "explorer": 0.10
                    }},
                    "explorer": {{
                        "validator": 0.05,
                        "broadcaster": 0.10,
                        "explorer": 0.85
                    }}
                }}
            }}
        }}
    }}

def main():
    """Generate all configuration files."""
    import os
    
    output_dir = os.path.dirname(os.path.abspath(__file__))
    
    print("Generating agent population...")
    agent_data = generate_agent_population()
    
    with open(os.path.join(output_dir, "agent_population.json"), 'w') as f:
        json.dump(agent_data, f, indent=2)
    print(f"✓ Created agent_population.json with {{len(agent_data['agents'])}} agents")
    print(f"  - 1 page agent (LLM-enabled)")
    print(f"  - {llm_count} LLM-enabled agents")
    print(f"  - {rule_count} rule-based agents")
    
    print("\\nGenerating random social network...")
    edges = generate_random_network(agent_data['agents'], avg_degree=10)
    network_path = os.path.join(output_dir, "network.csv")
    write_network_csv(edges, network_path)
    print(f"✓ Created network.csv with {{len(edges)}} follow relationships")
    print(f"  - Average degree: ~{{len(edges) / len(agent_data['agents']):.1f}} connections per agent")
    
    print("\\nGenerating simulation configuration...")
    sim_config = generate_simulation_config()
    with open(os.path.join(output_dir, "simulation_config.json"), 'w') as f:
        json.dump(sim_config, f, indent=2)
    print("✓ Created simulation_config.json")
    
    print("\\nGenerating server configuration...")
    server_config = generate_server_config()
    with open(os.path.join(output_dir, "server_config.json"), 'w') as f:
        json.dump(server_config, f, indent=2)
    print("✓ Created server_config.json")
    
    print("\\n" + "="*60)
    print("Configuration generation complete!")
    print("="*60)

if __name__ == "__main__":
    main()
'''

    script_path = os.path.join(dest_dir, "generate_population.py")
    with open(script_path, "w") as f:
        f.write(script_content)
    os.chmod(script_path, 0o755)
    print(f"  ✓ Created generate_population.py")


def create_readme(dest_dir, pop_config):
    """Create README.md for this population example."""
    total = pop_config["total"]
    llm_count = int(total * pop_config["llm_ratio"])
    rule_count = total - llm_count
    pop_type = pop_config["type"].capitalize()

    if pop_config["llm_ratio"] == 1.0:
        agent_desc = f"**{total} LLM-enabled agents**"
    elif pop_config["llm_ratio"] == 0.0:
        agent_desc = f"**{total} rule-based agents**"
    else:
        agent_desc = f"**{llm_count} LLM-enabled agents** and **{rule_count} rule-based agents**"

    readme_content = f"""# {pop_config["name"].replace("_", " ").title()}

This example demonstrates a YSimulator configuration with:
- **{total + 1} agents total**: {agent_desc} and **1 news page**
- **Initial random social network** with ~{total * 10} follow relationships (~10 connections per agent)
- **Discussion topics**: war, politics, sport, books, movies
- **Dynamic follow actions** using multiple recommendation strategies
- **Agent archetypes**: Validator, Broadcaster, Explorer

## Agent Distribution

- **1 Page Agent** (`NewsPage`): LLM-enabled news publisher with RSS feed
- **{llm_count} LLM Agents**: AI-powered decision making using language models
- **{rule_count} Rule-based Agents**: Heuristic-based decision making

## Quick Start

### 1. Generate Configuration

```bash
cd example/{pop_config["name"]}
python generate_population.py
```

This creates:
- `agent_population.json` - Agent definitions
- `network.csv` - Initial social network
- `simulation_config.json` - Simulation parameters
- `server_config.json` - Server settings

### 2. Start Server

```bash
# From repository root
python run_server.py --config example/{pop_config["name"]}/server_config.json
```

### 3. Start Client

```bash
# In a separate terminal
python run_client.py --config example/{pop_config["name"]}/simulation_config.json \\
                     --agents example/{pop_config["name"]}/agent_population.json \\
                     --prompts example/{pop_config["name"]}/{"llm_prompts.json" if llm_count > 0 else "prompts.json"}
```

## Configuration Files

### agent_population.json
Defines all {total + 1} agents with diverse characteristics:
- Political leanings: left, center, right, neutral
- Activity profiles: Always On, Morning Active, Evening Active
- Professions: Engineer, Teacher, Doctor, Artist, Student
- Content recommendation: random, rchrono, rchrono_followers
- Follow recommendation: random, common_neighbors, jaccard, adamic_adar, preferential_attachment

### network.csv
Initial social network with approximately {total * 10} directed follow edges using Erdős–Rényi random graph model.

### simulation_config.json
Main simulation parameters:
- Duration: 3 days, 24 slots per day (72 rounds)
- Discussion topics: war, politics, sport, books, movies
- Action likelihoods: post (3.0), comment (5.0), read (2.0), share (1.0), search (5.0), follow (0.1)
- Follow probabilities: 10% daily, 10% secondary after interactions

### server_config.json
Server settings:
- Database: SQLite (configurable for PostgreSQL/MySQL)
- Timeout: 180 seconds for network loading
- Redis: Optional caching (disabled by default)

## Performance Notes

- **Network loading**: Expect ~{int(total * 10 / 1000)} seconds for initial network loading
- **LLM requirements**: {llm_count} LLM agents will make API calls to Ollama/OpenAI
- **Memory usage**: ~{int((total + 1) * 0.5)}MB for agent population
- **Database size**: Grows with simulation length and agent activity

## Customization

Edit `generate_population.py` to modify:
- Average network degree (default: 10)
- Agent attribute distributions
- Archetype ratios
- LLM/rule-based split

Edit `simulation_config.json` to adjust:
- Simulation duration
- Discussion topics
- Action likelihoods
- Follow probabilities

## Troubleshooting

### Network not loading
- Check `ysimulator.log` for "Loading social network from network.csv"
- Verify network.csv is in the same directory as simulation_config.json

### LLM errors (if LLM agents present)
- Ensure Ollama is running: `ollama serve`
- Check model availability: `ollama list`
- Verify model name in simulation_config.json

### Performance issues
- Increase `heartbeat_interval` in simulation_config.json
- Reduce `num_days` for shorter simulations
- Consider PostgreSQL for better database performance

## See Also

- [llm_population_1000](../llm_population_1000/) - 1000 LLM agents example
- [mixed_population_100](../mixed_population_100/) - 50/50 mixed agents example
- [YSimulator Documentation](../../docs/) - Full documentation
"""

    readme_path = os.path.join(dest_dir, "README.md")
    with open(readme_path, "w") as f:
        f.write(readme_content)
    print(f"  ✓ Created README.md")


def generate_population(pop_dir):
    """Run the generate_population.py script to create configuration files."""
    script_path = os.path.join(pop_dir, "generate_population.py")
    print(f"  Running generate_population.py...")

    try:
        result = subprocess.run(
            ["python3", script_path],
            cwd=pop_dir,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )

        if result.returncode == 0:
            print(f"  ✓ Generated configuration files successfully")
            # Print some stats from stdout
            for line in result.stdout.split("\n"):
                if "Created" in line or "agents" in line:
                    print(f"    {line}")
        else:
            print(f"  ✗ Error generating files:")
            print(result.stderr)
            return False

        return True
    except subprocess.TimeoutExpired:
        print(f"  ✗ Timeout generating population (>5 minutes)")
        return False
    except Exception as e:
        print(f"  ✗ Error running script: {e}")
        return False


def main():
    """Main function to generate all population examples."""
    # Get paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)
    example_dir = os.path.join(repo_root, "example")

    print("=" * 70)
    print("YSimulator Population Generator")
    print("=" * 70)
    print(f"\nGenerating {len(POPULATIONS)} population examples...")

    successful = []
    failed = []

    for pop_config in POPULATIONS:
        try:
            # Create directory
            pop_dir = create_population_directory(example_dir, pop_config)

            # Get blueprint directory
            blueprint_name = get_blueprint_dir(pop_config["type"])
            blueprint_dir = os.path.join(example_dir, blueprint_name)

            # Copy static files
            copy_static_files(blueprint_dir, pop_dir, pop_config)

            # Create generate script
            create_generate_script(pop_dir, pop_config)

            # Create README
            create_readme(pop_dir, pop_config)

            # Generate population
            if generate_population(pop_dir):
                successful.append(pop_config["name"])
            else:
                failed.append(pop_config["name"])

        except Exception as e:
            print(f"  ✗ Error: {e}")
            failed.append(pop_config["name"])

    # Summary
    print("\n" + "=" * 70)
    print("Generation Summary")
    print("=" * 70)
    print(f"\n✓ Successful: {len(successful)}/{len(POPULATIONS)}")
    for name in successful:
        print(f"  - {name}")

    if failed:
        print(f"\n✗ Failed: {len(failed)}/{len(POPULATIONS)}")
        for name in failed:
            print(f"  - {name}")

    print("\n" + "=" * 70)
    print("All population examples are in the examples/ directory")
    print("=" * 70)

    return 0 if len(failed) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
