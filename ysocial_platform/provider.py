"""The microblogging platform on the Ray runtime ("HPC"): what YSocial needs to run, show and manage an HPC experiment.

The provider is declared in ``meta/registry.json`` (``platform`` section) and loaded by YSocial at startup. It talks to
the core through ``y_web.sdk`` only; the pages of the platform (``routes/``, ``templates/``, ``static/``) are part of this
repository and work without any other microblogging repository installed.
"""

from __future__ import annotations

import importlib
from typing import Any, Mapping, Optional

from y_web.sdk import (
    HPC,
    N_,
    CreationRules,
    FederationTraits,
    PlatformProvider,
)
from y_web.sdk import gettext as _


class Microblogging(PlatformProvider):
    key = "microblogging"
    label = N_("Microblogging")
    icon = "message-circle"
    order = 10

    @property
    def human_gateway(self):
        """How a person of a World Simulation gets an account here and acts (``gateway.py``)."""
        return importlib.import_module(f"{__package__}.gateway").HUMAN_GATEWAY

    server_label = "YSimulator"
    embedding_in_details = True
    plugin_agents = True
    stress_reward_page = True
    stress_reward_in_form = True
    tag_runtime_sets = (("hpc_simulator",),)
    federation_traits = FederationTraits(
        mdi_icon="mdi-message-text-outline",
        local_kind="post",
        author_sql="SELECT p.id, u.username, p.user_id FROM post p LEFT JOIN user_mgmt u ON u.id = p.user_id WHERE p.id IN ({q})",
        content_path="/{exp}/thread/{id}",
        profile_path="/{exp}/profile/{account}/recent/1",
        account_sql="SELECT id, username FROM user_mgmt WHERE id = ?",
        text_limit=280,
        decision_triggers=("publish",),
        simulators=(HPC,),
        topic_migration_key="create_topics",
    )
    default_platform = True
    simulator_types = (HPC,)

    prompt_pack = ("prompts.json", "prompts.json")
    profile_template = "@microblogging/microblogging/profile.html"
    has_interview = True

    def attach_routes(self) -> None:
        importlib.import_module(f"{__package__}.routes")

    def entry_url(self, exp_id: int, user_id: int) -> Optional[str]:
        return f"/{exp_id}/feed/{user_id}/feed/rf/1"

    def creation_rules(self, simulator_type: str) -> CreationRules:
        return CreationRules(database="server", copies_clean_database=False)

    def resolve_simulator(self, simulator_type: str, available: Mapping[str, bool]):
        if available["hpc"]:
            return HPC, None
        return HPC, _(
            "HPC microblogging experiments are unavailable because YMicroblogging is not present."
        )

    def render_interview(self, exp_id: int, context: dict) -> Any:
        from flask import render_template
        from flask_login import current_user
        from sqlalchemy import select
        from y_web.sdk.models import Admin_users, Agent, db

        profile_pic = ""
        try:
            agent = db.session.scalars(
                select(Agent).filter_by(name=current_user.username)
            ).first()
            if agent is not None and agent.profile_pic is not None:
                profile_pic = agent.profile_pic
            else:
                admin = db.session.scalars(
                    select(Admin_users).filter_by(username=current_user.username)
                ).first()
                profile_pic = admin.profile_pic if admin else ""
        except Exception:
            profile_pic = ""
        return render_template(
            "@microblogging/microblogging/interview.html",
            profile_pic=profile_pic,
            experiment_memory_enabled=True,
            len=len,
            **context,
        )
