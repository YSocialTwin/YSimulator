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
    FrontendSetting,
    PlatformProvider,
)
from y_web.sdk import gettext as _
from .scenario_design import build_driver


class Microblogging(PlatformProvider):
    key = "microblogging"
    #: Scenario Design plugin: the driver that serves this platform (None when the plugin is absent)
    scenario_design_driver = staticmethod(build_driver)
    #: texts of the plugin catalogue / repository metadata that the core translation catalogue carries
    catalog_texts = (
        N_("Ray-based runtime for microblogging experiments (posts, timelines, follows) built for large-scale simulations, on a single machine or on HPC clusters."),
    )
    label = N_("Microblogging")
    icon = "message-circle"
    order = 10
    standard_feed = True
    infinite_scroll = True
    menu_label = N_("Microblogging (i.e., X/BlueSky)")
    hpc_redis = True
    client_form_fields = frozenset({"image", "news", "vote"})

    crosspost_on_share = (
        True  # a shared post can also go out through the World Simulation gateway
    )

    reads_server_config = (
        True  # pages read the memory and stress/reward settings of its server config
    )

    @property
    def recsys_catalog(self):
        """The recommenders this platform adds to the catalogue (``catalog.py``)."""
        return importlib.import_module(f"{__package__}.catalog").RECSYS_CATALOG

    # what the admin "frontend settings" page offers for this platform (the boxes are in templates/slots/)
    frontend_settings = (
        # entries of the left menu, the theme switch and the log-out link (all shown by default)
        FrontendSetting("nav_home", True),
        FrontendSetting("nav_explore", True),
        FrontendSetting("nav_chat", True),
        FrontendSetting("nav_friends", True),
        FrontendSetting("nav_profile", True),
        FrontendSetting("nav_interview", True),
        FrontendSetting("nav_admin", True),
        FrontendSetting("nav_theme_switch", True),
        FrontendSetting("nav_logout", True),
        FrontendSetting("thread_links", True),  # links to the /thread pages (False = removed everywhere)
        FrontendSetting("show_search", True),  # the search boxes (header, explore page) and the search endpoint
        FrontendSetting("show_profile_links", True),  # links to the profiles of the other users (False = plain names)
        # tabs next to "Home" in the feed (each one forces a chronological recommender for that view)
        FrontendSetting("feed_tab_recent", True),  # Recent  -> ReverseChrono
        FrontendSetting("feed_tab_friends", True),  # Friends -> ReverseChronoFollowers
        FrontendSetting("feed_tab_popular", True),  # Popular -> ReverseChronoPopularity
        FrontendSetting(
            "filter_bubble_alpha", 2.0
        ),  # opinion similarity width (Gaussian)
        FrontendSetting("filter_bubble_beta", 0.0),  # recency decay (0 = disabled)
        FrontendSetting(
            "filter_bubble_gamma", 0.0
        ),  # engagement amplification (0 = disabled)
        FrontendSetting(
            "filter_bubble_lr", 0.05
        ),  # EMA learning rate of the real-time interest update
        FrontendSetting(
            "filter_bubble_sort",
            "score",
            choices=(
                {"name": "score", "label": N_("Score only")},
                {"name": "recency", "label": N_("Recency first")},
                {"name": "engagement", "label": N_("Engagement first")},
                {"name": "hybrid", "label": N_("Hybrid (score × recency)")},
            ),
        ),
        FrontendSetting(
            "filter_bubble_wr", 1.0
        ),  # weight of reactions in the engagement score
        FrontendSetting("filter_bubble_wc", 1.5),  # weight of comments
        FrontendSetting("filter_bubble_ws", 2.0),  # weight of shares
    )

    @property
    def human_gateway(self):
        """How a person of a World Simulation gets an account here and acts (``gateway.py``)."""
        return importlib.import_module(f"{__package__}.gateway").HUMAN_GATEWAY

    @property
    def human_recsys(self):
        """The recommender systems of the people who use the frontend (``recsys/``)."""
        return importlib.import_module(f"{__package__}.recsys").RECSYS

    server_label = "YSimulator"
    embedding_in_details = True
    plugin_agents = True
    stress_reward_page = True
    stress_reward_in_form = True
    hpc_launch = {
        "runtime_repo": "YSimulator",
        "server_dir_repo": "YServer",
        "supports_federation": True,
    }
    runtime_keys = ("hpc_simulator",)
    availability_key = "hpc"
    catalog_names_win = True
    page_resources = True
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
    edit_profile_template = "@microblogging/microblogging/edit_profile.html"
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
        from y_web.sdk.web import load_ui_settings

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
            **{"ui": load_ui_settings(exp_id), **context},
        )
