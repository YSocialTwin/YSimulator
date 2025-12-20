#!/usr/bin/env python3
"""
Convert agent IDs from integers to UUIDs in agent_population.json files.
This ensures consistency with the database schema that uses UUID primary keys.
"""

import json
import uuid
from pathlib import Path

def convert_agent_ids_to_uuid(json_file_path):
    """Convert all agent IDs in the JSON file from integers to UUIDs."""
    
    # Read the JSON file
    with open(json_file_path, 'r') as f:
        data = json.load(f)
    
    # Create a mapping of old IDs to new UUIDs
    id_mapping = {}
    
    # Convert agent IDs
    if "agents" in data:
        for agent in data["agents"]:
            old_id = agent["id"]
            if isinstance(old_id, int):
                # Generate a deterministic UUID based on the old ID for consistency
                # This allows us to reproduce the same UUIDs if needed
                namespace = uuid.UUID('12345678-1234-5678-1234-567812345678')
                new_uuid = str(uuid.uuid5(namespace, f"agent_{old_id}"))
                id_mapping[old_id] = new_uuid
                agent["id"] = new_uuid
                print(f"Converted agent {old_id} -> {new_uuid} ({agent.get('username', 'unknown')})")
    
    # Write back to the file
    with open(json_file_path, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"\nConversion complete for {json_file_path}")
    print(f"Converted {len(id_mapping)} agents")
    return id_mapping

if __name__ == "__main__":
    # Convert the main agent population file
    main_file = Path("example/agent_population.json")
    if main_file.exists():
        print(f"Converting {main_file}...")
        convert_agent_ids_to_uuid(main_file)
    
    # Convert the small agent population file
    small_file = Path("example/agent_population_small.json")
    if small_file.exists():
        print(f"\nConverting {small_file}...")
        convert_agent_ids_to_uuid(small_file)
