"""The microblogging platform: what YSocial needs to know to run, show and manage a microblogging experiment.

One provider answers for both runtimes: the Flask pair (YServer/YClient, "Standard") and the Ray runtime (this
repository, "HPC"). The provider is declared in ``meta/registry.json`` (``platform`` section) and loaded by YSocial at
startup. It talks to the core through ``y_web.sdk`` only; the pages of the platform (``routes/``, ``templates/``,
``static/``) are part of this repository.
"""

from __future__ import annotations

import importlib
from typing import Any, Mapping, Optional

from y_web.sdk import (
    HPC,
    N_,
    STANDARD,
    CreationRules,
    PlatformProvider,
    StandardRuntime,
)
from y_web.sdk import gettext as _


class Microblogging(PlatformProvider):
    key = "microblogging"
    label = N_("Microblogging")
    icon = "message-circle"
    order = 10
    default_platform = True

    prompt_pack = ("prompts.json", "prompts.json")
    standard_runtime = StandardRuntime(
        server_repo="YServer",
        client_repo="YClient",
        fake_agent_module="y_client.classes",
        activity_profiles=True,
    )
    profile_template = "@microblogging/microblogging/profile.html"
    has_interview = True

    def attach_routes(self) -> None:
        importlib.import_module(f"{__package__}.routes")

    def entry_url(self, exp_id: int, user_id: int) -> Optional[str]:
        return f"/{exp_id}/feed/{user_id}/feed/rf/1"

    def creation_rules(self, simulator_type: str) -> CreationRules:
        return CreationRules(
            database="server", copies_clean_database=simulator_type == STANDARD
        )

    def resolve_simulator(self, simulator_type: str, available: Mapping[str, bool]):
        # either runtime will do: ask for the one that is installed
        if simulator_type == HPC:
            if available["hpc"]:
                return HPC, None
            if available["microblogging"]:
                return STANDARD, None
            return HPC, _(
                "HPC microblogging experiments are unavailable because YMicroblogging is not present."
            )
        if available["microblogging"]:
            return STANDARD, None
        if available["hpc"]:
            return HPC, None
        return STANDARD, _(
            "Microblogging experiments are unavailable because neither YServer/YClient nor YMicroblogging is present."
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
