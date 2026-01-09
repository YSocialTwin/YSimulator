"""
Network Loader for Agent Management.

Handles social network topology loading and follow relationship creation.
"""

import csv
import logging
from pathlib import Path
from typing import List, Tuple

import ray

from YSimulator.YClient.classes.ray_models import AgentProfile


class NetworkLoader:
    """
    Manages social network loading and follow relationship creation.

    Responsibilities:
    - Parse network edges from CSV files
    - Create follow relationships on server
    - Batch processing for optimal performance
    """

    def __init__(self, server, client_id: str, logger: logging.Logger):
        """
        Initialize NetworkLoader.

        Args:
            server: Ray server actor handle
            client_id: Client identifier
            logger: Logger instance
        """
        self.server = server
        self.client_id = client_id
        self.logger = logger

    def parse_network_edges(
        self, network_csv_path: Path, agent_profiles: List[AgentProfile]
    ) -> List[Tuple[str, str]]:
        """
        Parse network edges from CSV file.

        The CSV file format is simple two-column format without headers:
        - Each row: follower_username,followed_username
        - Example: NewsPage,agent_001

        Args:
            network_csv_path: Path to network edges CSV file
            agent_profiles: List of agent profiles for username-to-ID mapping

        Returns:
            List of (source_id, target_id) tuples representing follow relationships
        """
        edges = []

        if not network_csv_path.exists():
            self.logger.error(f"Network edges file not found: {network_csv_path}")
            return edges

        # Create username to ID mapping
        username_to_id = {agent.username: str(agent.id) for agent in agent_profiles}

        try:
            with open(network_csv_path, "r", newline="", encoding="utf-8") as csvfile:
                reader = csv.reader(csvfile)

                for row_num, row in enumerate(reader, start=1):
                    # Skip empty rows
                    if not row or len(row) < 2:
                        continue

                    # Parse the edge: follower follows user
                    follower_name = row[0].strip()
                    user_name = row[1].strip()

                    if not follower_name or not user_name:
                        self.logger.warning(
                            f"Skipping invalid edge at row {row_num}: '{follower_name}' -> '{user_name}'"
                        )
                        continue

                    # Skip if either username is not in our agent population
                    if follower_name not in username_to_id or user_name not in username_to_id:
                        continue

                    # Get agent IDs
                    follower_id = username_to_id[follower_name]
                    user_id = username_to_id[user_name]

                    edges.append((follower_id, user_id))

            self.logger.info(f"Parsed {len(edges)} network edges from {network_csv_path}")

        except Exception as e:
            self.logger.error(f"Error parsing network edges file: {e}")

        return edges

    def load_and_create_social_network(
        self, network_csv_path: Path, agent_profiles: List[AgentProfile], batch_size: int = 100
    ) -> int:
        """
        Load network edges from CSV and create follow relationships on server.

        Args:
            network_csv_path: Path to network edges CSV file
            agent_profiles: List of agent profiles for username-to-ID mapping
            batch_size: Number of edges to process in each batch (default: 100)

        Returns:
            Number of follow relationships successfully created
        """
        edges = self.parse_network_edges(network_csv_path, agent_profiles)

        if not edges:
            self.logger.warning("No edges to create")
            return 0

        # Create follow relationships in batches
        success_count = 0
        failed_count = 0

        for i in range(0, len(edges), batch_size):
            batch = edges[i : i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (len(edges) + batch_size - 1) // batch_size

            try:
                # Send batch to server using the correct method name
                batch_count = ray.get(
                    self.server.add_follow_relationships_batch.remote(
                        batch, client_id=self.client_id
                    )
                )

                success_count += batch_count

                if batch_count == len(batch):
                    self.logger.info(
                        f"Successfully created {batch_count} follow relationships "
                        f"(batch {batch_num}/{total_batches})"
                    )
                elif batch_count > 0:
                    failed_count += len(batch) - batch_count
                    self.logger.warning(
                        f"Partial batch success: {batch_count}/{len(batch)} follow relationships created "
                        f"(batch {batch_num}/{total_batches})"
                    )
                else:
                    failed_count += len(batch)
                    self.logger.warning(
                        f"Failed to create batch of {len(batch)} follow relationships "
                        f"(batch {batch_num}/{total_batches})"
                    )

            except Exception as e:
                failed_count += len(batch)
                self.logger.error(
                    f"Error creating follow relationships batch: {e}",
                    extra={"extra_data": {"batch_size": len(batch), "error": str(e)}},
                )

        self.logger.info(
            f"Network creation complete: {success_count} successful, {failed_count} failed out of {len(edges)} total edges"
        )

        return success_count
