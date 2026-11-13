"""Tables of the federation inside the YSimulator database (all new, additive; created only when federation is on).

federation_membership: state of each local account as the coordinator told it (dormant, active, left).
federation_ref:        every content materialised from a cross-post (origin = federation) with its source.
federation_export:     posts handed to the bus, with tick and sequence number, so that exporting the same tick again
                       gives the same messages (INV-05); tick NULL = marked by the agent, not exported yet.
federation_provisioned: accounts created on the coordinator's request (INV-19), the profile each was built from and the client that
                       adopted it.
federation_state:      small key/value store (watermark of the posts that existed before the federation started).
They live in a metadata of their own: the existing tables and their creation do not change."""

from sqlalchemy import Boolean, Column, Float, Integer, String, Text
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class FederationMembership(Base):
    __tablename__ = "federation_membership"

    user_id = Column(String(36), primary_key=True)
    global_agent_id = Column(String(64), nullable=False, unique=True)
    state = Column(String(10), nullable=False)
    since_tick = Column(Integer, nullable=False, default=0)
    reason = Column(String(16), nullable=False, default="initial")


class FederationRef(Base):
    __tablename__ = "federation_ref"

    local_kind = Column(String(16), primary_key=True)
    local_id = Column(String(36), primary_key=True)
    source_ref = Column(Text, nullable=False)
    fed_msg_id = Column(String(200), nullable=False, unique=True)


class FederationTopic(Base):
    """A topic created on this platform because content that came from another platform carried it."""

    __tablename__ = "federation_topic"

    name = Column(String(200), primary_key=True)
    interest_id = Column(String(36), nullable=False)
    created_tick = Column(Integer, nullable=False)
    source_member = Column(String(64), nullable=False)


class FederationHuman(Base):
    """A person on this platform (human gateway): ``human_key`` is the key YWeb gives (stable per person and experiment),
    ``human_id`` the federation identity ``human:<id>`` once the person is enrolled in a World Simulation.
    """

    __tablename__ = "federation_human"

    human_key = Column(String(64), primary_key=True)
    user_id = Column(String(36), nullable=False, unique=True)
    human_id = Column(String(80), nullable=True)


class FederationExport(Base):
    __tablename__ = "federation_export"

    post_id = Column(String(36), primary_key=True)
    tick = Column(Integer, nullable=True)
    seq = Column(Integer, nullable=True)


class FederationCrosspost(Base):
    """The agent chose to cross-post a post to another platform with this text (F6.2, crosspost.mode = agent_action).

    account_id, tick and seq are fixed at the first export of the post, so that a retry sends the same message.
    """

    __tablename__ = "federation_crosspost"

    post_id = Column(String(36), primary_key=True)
    member = Column(String(64), primary_key=True)
    text = Column(Text, nullable=False, default="")
    account_id = Column(String(64), nullable=True)
    tick = Column(Integer, nullable=True)
    seq = Column(Integer, nullable=True)


class FederationProvisioned(Base):
    """INV-19: an account created here because the coordinator asked for it (the agent of a client of another platform decided to
    join). A client of this platform adopts it (gives it an agent that acts); `claimed_by` is the first client that was offered it
    (two clients never adopt the same account), `adopted` tells it is in play. `profile_json` is the profile the account was
    built from, so that a restarted client gets the same agent back."""

    __tablename__ = "federation_provisioned"

    user_id = Column(String(36), primary_key=True)
    global_agent_id = Column(String(64), nullable=False, unique=True)
    username = Column(String(50), nullable=False)
    profile_json = Column(Text, nullable=False, default="{}")
    claimed_by = Column(String(64), nullable=True)
    adopted = Column(Boolean, nullable=False, default=False)


class FederationAttention(Base):
    """Attention multiplier of the day for each account (F4.3); an account without a row has multiplier 1."""

    __tablename__ = "federation_attention"

    user_id = Column(String(36), primary_key=True)
    day = Column(Integer, nullable=False)
    multiplier = Column(Float, nullable=False)


class FederationExposure(Base):
    """exposure.v1 handed to the bus for a tick (F4.4b), fixed on the first export so that a retry sends the same messages."""

    __tablename__ = "federation_exposure_log"

    tick = Column(Integer, primary_key=True)
    seq = Column(Integer, primary_key=True)
    viewer_uid = Column(String(36), nullable=False)
    source_ref = Column(Text, nullable=False)
    kind = Column(String(10), nullable=False)
    tie = Column(String(10), nullable=False)
    exact = Column(Integer, nullable=False)


class FederationState(Base):
    __tablename__ = "federation_state"

    key = Column(String(32), primary_key=True)
    value = Column(String(64), nullable=False)


def ensure_tables(engine):
    """CREATE TABLE IF NOT EXISTS for the tables."""
    Base.metadata.create_all(engine, checkfirst=True)
