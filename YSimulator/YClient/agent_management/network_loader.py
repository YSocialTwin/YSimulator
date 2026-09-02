"""
Network Loader for Agent Management.

Handles social network topology loading and follow relationship creation.
"""

import csv
import logging
import time
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
        self, network_csv_path: Path, agent_profiles: List[AgentProfile], batch_size: int = 20000
    ) -> int:
        """
        Load network edges from CSV and create follow relationships on server.

        Args:
            network_csv_path: Path to network edges CSV file
            agent_profiles: List of agent profiles for username-to-ID mapping
            batch_size: Number of edges to process in each batch (default: 20000)

        Returns:
            Number of follow relationships successfully created
        """
        edges = self.parse_network_edges(network_csv_path, agent_profiles)

        if not edges:
            self.logger.warning("No edges to create")
            return 0

        initial_round_id = self._resolve_initial_round_id()
        self._send_startup_heartbeat()

        # Create follow relationships in batches
        success_count = 0
        failed_count = 0
        total_edges = len(edges)
        total_batches = (total_edges + batch_size - 1) // batch_size
        start_time = time.time()
        log_interval = max(1, total_batches // 50) if total_batches > 50 else 1
        last_log_time = start_time
        tag = f"[{self.client_id}]" if self.client_id else "[NetworkLoader]"

        print(
            f"{tag} [Network Setup] Starting bulk insertion of {total_edges:,} edges in {total_batches:,} batch(es) (batch_size={batch_size:,})...",
            flush=True,
        )

        for i in range(0, total_edges, batch_size):
            self._send_startup_heartbeat()
            batch = edges[i : i + batch_size]
            batch_num = i // batch_size + 1
            batched_edges = [
                (follower_id, user_id, initial_round_id) for follower_id, user_id in batch
            ]

            try:
                # Send batch to server using the correct method name
                batch_count = ray.get(
                    self.server.add_follow_relationships_batch.remote(
                        batched_edges, client_id=self.client_id
                    )
                )

                success_count += batch_count

                if batch_count != len(batch):
                    if batch_count > 0:
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

                # Periodic and terminal ETA progress reporting
                now = time.time()
                is_first = batch_num == 1
                is_last = batch_num == total_batches
                is_periodic = (batch_num % log_interval == 0) or (now - last_log_time >= 2.0)

                if is_first or is_last or is_periodic:
                    last_log_time = now
                    elapsed = max(0.001, now - start_time)
                    processed = min(i + len(batch), total_edges)
                    percent = (processed / total_edges) * 100
                    rate_edges = processed / elapsed
                    rate_batches = batch_num / elapsed
                    remaining_batches = total_batches - batch_num
                    eta_seconds = remaining_batches / rate_batches if rate_batches > 0 else 0

                    eta_str = time.strftime(
                        "%H:%M:%S" if eta_seconds >= 3600 else "%M:%S",
                        time.gmtime(eta_seconds),
                    )
                    elapsed_str = time.strftime(
                        "%H:%M:%S" if elapsed >= 3600 else "%M:%S",
                        time.gmtime(elapsed),
                    )

                    progress_msg = (
                        f"{tag} [Network Setup] Batch {batch_num}/{total_batches} ({percent:5.1f}%) | "
                        f"{processed:,}/{total_edges:,} edges ({rate_edges:,.0f} edges/s) | "
                        f"Elapsed: {elapsed_str} | ETA: {eta_str}"
                    )
                    print(progress_msg, flush=True)
                    self.logger.info(progress_msg)

            except Exception as e:
                failed_count += len(batch)
                self.logger.error(
                    f"Error creating follow relationships batch: {e}",
                    extra={"extra_data": {"batch_size": len(batch), "error": str(e)}},
                )
            finally:
                self._send_startup_heartbeat()

        total_elapsed = max(0.001, time.time() - start_time)
        completion_msg = (
            f"{tag} [Network Setup] Completed in {total_elapsed:.1f}s: "
            f"{success_count:,} successful, {failed_count:,} failed out of {total_edges:,} total edges "
            f"({(success_count / total_elapsed):,.0f} edges/s)"
        )
        print(completion_msg, flush=True)
        self.logger.info(completion_msg)

        return success_count

    def _send_startup_heartbeat(self) -> None:
        """Keep the registered client alive while startup network loading runs."""
        try:
            if hasattr(self.server, "heartbeat"):
                ray.get(self.server.heartbeat.remote(self.client_id))
        except Exception as e:
            self.logger.debug(f"Startup heartbeat skipped during network loading: {e}")

    def _resolve_initial_round_id(self):
        """
        Resolve the first simulation round used to anchor initial network edges.

        Returns:
            The first round UUID when available, otherwise None.
        """
        try:
            if hasattr(self.server, "get_first_round_id"):
                round_id = ray.get(self.server.get_first_round_id.remote())
                if round_id:
                    return round_id
        except Exception as e:
            self.logger.warning(
                f"Unable to resolve initial round ID for network loading: {e}",
                extra={"extra_data": {"error": str(e)}},
            )

        return None
