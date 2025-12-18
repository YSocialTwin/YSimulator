import ray
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
# Local import prevents pickling errors
from classes.ray_models import ActionDTO, SimulationInstruction


# --- Server Actor Definition ---
@ray.remote
class OrchestratorServer:
    def __init__(self, db_name, min_to_start=1):
        from classes.models import Base
        self.engine = create_engine(f'sqlite:///{db_name}')
        Base.metadata.create_all(self.engine)

        self.min_to_start = min_to_start
        self.registered_clients = set()
        self.submitted_clients = set()
        self.registered_agents = {}  # Track registered agents: {agent_id: username}

        self.day = 1
        self.slot = 1
        self.recent_posts_cache = []
    
    def register_agents(self, agents: list):
        """
        Register agent profiles in the database if they don't already exist.
        
        Args:
            agents: List of AgentProfile dataclass instances
        
        Returns:
            dict: Summary of registration results
        """
        from classes.models import User_mgmt
        import time
        
        session = Session(self.engine)
        registered_count = 0
        updated_count = 0
        skipped_count = 0
        
        try:
            for agent_profile in agents:
                # Check if agent already exists
                existing = session.query(User_mgmt).filter_by(id=agent_profile.id).first()
                
                if existing:
                    skipped_count += 1
                    self.registered_agents[agent_profile.id] = agent_profile.username
                    continue
                
                # Set joined_on if not set
                joined_on = agent_profile.joined_on
                if joined_on == 0:
                    joined_on = int(time.time())
                
                # Create new user record
                user = User_mgmt(
                    id=agent_profile.id,
                    username=agent_profile.username,
                    email=agent_profile.email,
                    password=agent_profile.password,
                    leaning=agent_profile.leaning,
                    user_type=agent_profile.user_type,
                    age=agent_profile.age,
                    oe=agent_profile.oe,
                    co=agent_profile.co,
                    ex=agent_profile.ex,
                    ag=agent_profile.ag,
                    ne=agent_profile.ne,
                    recsys_type=agent_profile.recsys_type,
                    frecsys_type=agent_profile.frecsys_type,
                    language=agent_profile.language,
                    owner=agent_profile.owner,
                    education_level=agent_profile.education_level,
                    joined_on=joined_on,
                    gender=agent_profile.gender,
                    nationality=agent_profile.nationality,
                    round_actions=agent_profile.round_actions,
                    toxicity=agent_profile.toxicity,
                    is_page=agent_profile.is_page,
                    left_on=agent_profile.left_on,
                    daily_activity_level=agent_profile.daily_activity_level,
                    profession=agent_profile.profession,
                    activity_profile=agent_profile.activity_profile,
                    archetype=agent_profile.archetype
                )
                session.add(user)
                registered_count += 1
                self.registered_agents[agent_profile.id] = agent_profile.username
            
            session.commit()
            print(f"[Server] 👥 Agent Registration: {registered_count} new, {skipped_count} existing")
            
            return {
                "registered": registered_count,
                "skipped": skipped_count,
                "total": len(self.registered_agents)
            }
            
        except Exception as e:
            session.rollback()
            print(f"[Server] ❌ Agent registration error: {e}")
            raise
        finally:
            session.close()

    def register_client(self, client_id):
        """
        Dynamic Registration:
        New clients can join anytime. They effectively 'pause' the
        current slot until they catch up and submit their action.
        """
        if client_id not in self.registered_clients:
            self.registered_clients.add(client_id)
            print(f"[Server] 🟢 Client {client_id} joined. Total: {len(self.registered_clients)}")
        return True

    def deregister_client(self, client_id):
        """
        Optional: Call this if a client shuts down gracefully.
        Otherwise, the server might hang waiting for a dead client.
        """
        if client_id in self.registered_clients:
            self.registered_clients.remove(client_id)
            # If we were waiting ONLY for this client, we might be able to advance now
            self.submitted_clients.discard(client_id)
            print(f"[Server] 🔴 Client {client_id} left. Total: {len(self.registered_clients)}")

            # Check if leaving unblocked the barrier
            self._check_barrier_and_advance()
        return True

    def get_instruction(self, client_id) -> SimulationInstruction:
        # 1. Pause if not enough players
        if len(self.registered_clients) < self.min_to_start:
            return SimulationInstruction(status='WAIT')

        # 2. Wait if this client already finished the current slot
        if client_id in self.submitted_clients:
            return SimulationInstruction(status='WAIT')

        # 3. Proceed
        return SimulationInstruction(
            status='PROCEED',
            day=self.day,
            slot=self.slot,
            recent_post_ids=self.recent_posts_cache
        )

    def submit_actions(self, client_id, actions: list[ActionDTO]):
        # [Database Logic is same as before...]
        from classes.models import PostModel, InteractionModel
        session = Session(self.engine)
        new_ids = []
        try:
            for act in actions:
                if act.action_type == 'POST':
                    p = PostModel(agent_id=act.agent_id, cluster_id=act.cluster_id, content=act.content, day=self.day,
                                  slot=self.slot)
                    session.add(p)
                    session.flush()
                    new_ids.append(p.id)
                else:
                    session.add(
                        InteractionModel(agent_id=act.agent_id, post_id=act.target_post_id, type=act.action_type,
                                         content=act.content))
            session.commit()
            if new_ids:
                self.recent_posts_cache.extend(new_ids)
                self.recent_posts_cache = self.recent_posts_cache[-50:]
        except Exception as e:
            print(f"DB Error: {e}")
        finally:
            session.close()

        # Mark this specific client as done
        self.submitted_clients.add(client_id)

        # Check if EVERYONE is done
        self._check_barrier_and_advance()

    def _check_barrier_and_advance(self):
        """
        The Core Dynamic Barrier.
        """
        current_count = len(self.registered_clients)

        # Do not advance if no one is connected
        if current_count == 0:
            return

        # If everyone who is CURRENTLY registered has submitted, advance.
        if len(self.submitted_clients) >= current_count:
            print(f"[Server] ✅ Day {self.day} Slot {self.slot} complete (Agents: {current_count}). Advancing...")

            self.submitted_clients.clear()
            self.slot += 1
            if self.slot > 24:
                self.slot = 1
                self.day += 1
