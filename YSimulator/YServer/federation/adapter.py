"""PlatformAdapter of YSimulator (microblogging, HPC backend).

Clock (F2.3): canonical time of the server (day, slot), base 1 (day 1, slot 1 is the first round; F0.4).
Bus and membership (F3.4c), same design as YServer:
- apply_membership stores the state of each account in federation_membership; accounts that are not active are
  left out of recommendations, follow suggestions and topic search (filter_posts / filter_users, called by the server) and the
  clients ask which they are (server.get_federation_inactive_agents) so they do not act.
- export_outbox turns the root posts that the agents marked for cross-post (attribute `crosspost` of the POST action), or
  all root posts of active authors with export_policy = "all", into content.v1 for the coordinator.
- ingest_inbox materialises crosspost.v1 as a post of the author, once per fed_msg_id (INV-05), with a federation_ref row.
Affective report (F4.1): native stress/reward read from the stress_reward table. Attention (F4.3): multipliers stored per account, read by the client.

`host` is the object that owns the database: it needs `engine`, `post_service`, `current_round_id`, `recent_posts_cache` and, to
create accounts on request (INV-19), `register_agents` (the OrchestratorServer; a small stand-in in tests).
"""

import logging
import threading
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session
from ysocial_federation import content_policy
from ysocial_federation.adapter import IngestReport, PlatformAdapter
from ysocial_federation.bindings import BoundAccountsMixin
from ysocial_federation.envelope import COORDINATOR, Envelope
from ysocial_federation.schemas import LINK_MAX, TEXT_EXCERPT_MAX
from ysocial_federation.timebase import ONE_BASED

log = logging.getLogger("ysimulator.federation")


class YSimulatorAdapter(BoundAccountsMixin, PlatformAdapter):
    platform = "microblogging"

    def __init__(
        self,
        member,
        federation_id=1,
        host=None,
        accounts=None,
        export_policy="marked",
        emit_exposures=False,
        crosspost_mode="coordinator_rule",
        create_topics=False,
        bindings_file=None,
        crosspost_content=None,
    ):
        """accounts: {global_agent_id: local agent id}; without an entry the global id is the local agent id.

        bindings_file (INV-17): agents are bound by username; the accounts are reported to the coordinator, whose answer is kept in
        this file. Then the local id is never the global id: an account that is not bound acts as usual and is not exported.
        """
        if export_policy not in ("marked", "all"):
            raise ValueError("export_policy must be 'marked' or 'all'")
        self.member = member
        self.federation_id = federation_id
        self.host = host
        self.export_policy = export_policy
        self.emit_exposures = bool(emit_exposures)
        if crosspost_mode not in ("coordinator_rule", "agent_action"):
            raise ValueError("crosspost_mode must be 'coordinator_rule' or 'agent_action'")
        self.crosspost_mode = crosspost_mode
        self.crosspost_content = content_policy.normalize(
            crosspost_content
        )  # P13: with "news" the article link travels
        self.create_topics = bool(
            create_topics
        )  # topic migration: create the topics a cross-post carries and the platform lacks
        self._destinations = (
            {}
        )  # {global_agent_id: [{"member", "local_account_id"}]}, set by the gate before each export
        self._accounts = {str(k): str(v) for k, v in (accounts or {}).items()}
        self._by_user = {v: k for k, v in self._accounts.items()}
        self._lock = threading.RLock()
        self._inactive = (
            None  # cache of the ids that are not active; loaded from the table on first use
        )
        self._init_bindings(bindings_file, self._enumerate_accounts, cast=str)

    def _enumerate_accounts(self, after):
        """Ids are UUIDs (no order): the marker is the number of accounts, so a round without new accounts costs one COUNT."""
        from sqlalchemy import func

        from YSimulator.YServer.classes.models import User_mgmt

        with Session(self.host.engine) as s:
            count = s.scalar(select(func.count()).select_from(User_mgmt))
            if after is not None and int(after) == int(count):
                return [], after
            humans = self._human_uids()
            rows = s.execute(select(User_mgmt.username, User_mgmt.id).order_by(User_mgmt.id)).all()
        return [(u, i) for u, i in rows if i not in humans and i not in self._by_user], count

    # -- clock -------------------------------------------------------------------------
    def to_tick(self, local_round):
        day, slot = local_round
        return ONE_BASED.to_tick(int(day), int(slot))

    def from_tick(self, tick):
        return ONE_BASED.from_tick(tick)

    # -- identity and database ---------------------------------------------------------
    def _humans(self):
        """{local user id: identity "human:<id>"} of the accounts of people: the identity map entries with the reserved
        prefix and the accounts the human gateway enrolled (table ``federation_human``)."""
        out = {uid: gid for uid, gid in self._by_user.items() if gid.startswith("human:")}
        try:
            from sqlalchemy import inspect

            from .tables import FederationHuman

            if inspect(self.host.engine).has_table(FederationHuman.__tablename__):
                with Session(self.host.engine) as s:
                    out.update(
                        {
                            r.user_id: r.human_id
                            for r in s.scalars(select(FederationHuman)).all()
                            if r.human_id
                        }
                    )
        except Exception:  # noqa: BLE001 - no database yet: no people
            pass
        return out

    def user_of(self, global_agent_id):
        gid = str(global_agent_id)
        if gid in self._accounts:
            return self._accounts[gid]
        if gid.startswith("human:"):
            return next((uid for uid, hid in self._humans().items() if hid == gid), gid)
        if (
            self._is_bound_mode
        ):  # INV-17: the global id comes from the coordinator, never from the local id
            return None
        return gid

    def agent_of(self, user_id):
        uid = str(user_id)
        if uid in self._by_user:
            return self._by_user[uid]
        human = self._humans().get(uid)
        if human is not None:
            return human
        return (
            self._unbound_id(uid) if self._is_bound_mode else uid
        )  # a person has no fallback to the local id (it could be an agent's)

    def _human_uids(self):
        return set(self._humans())

    def _session(self):
        from .tables import ensure_tables

        engine = self.host.engine
        ensure_tables(engine)
        return Session(engine)

    # -- accounts created on request (protocol 1.2, INV-19) ------------------------------------
    PROVISION_FIELDS = (
        "leaning",
        "age",
        "oe",
        "co",
        "ex",
        "ag",
        "ne",
        "language",
        "education_level",
        "gender",
        "nationality",
        "toxicity",
        "profession",
        "archetype",
        "cluster",
        "llm",
        "daily_activity_level",
        "round_actions",
        "activity_profile",
        "recsys_type",
        "frecsys_type",
    )
    PROVISION_NAMESPACE = uuid.UUID("5c3c7f0e-6a41-4c0e-9d57-0f3d1b8a2e11")

    @classmethod
    def provisioned_user_id(cls, username):
        """Deterministic UUID of the account created for `username` (the same name always gives the same id)."""
        return str(uuid.uuid5(cls.PROVISION_NAMESPACE, f"ysimulator:federation:{username}"))

    def _provision_profile(self, req, name):
        """AgentProfile of the agent that joins: harmless defaults for the platform's fields (profile traits, leaning, age, gender,
        nationality, toxicity, profession, language) and the interests of the request; what the request carries (the fields
        at the top level or under `extras`) wins."""
        from YSimulator.YClient.classes.ray_models import AgentProfile

        extras = req.get("extras") if isinstance(req.get("extras"), dict) else {}
        fields = {
            "leaning": "neutral",
            "age": 30,
            "oe": "medium",
            "co": "medium",
            "ex": "medium",
            "ag": "medium",
            "ne": "medium",
            "language": "en",
            "education_level": "",
            "gender": "non-binary",
            "nationality": "",
            "toxicity": "no",
            "profession": "",
            "llm": False,
            "cluster": 0,
        }
        for key in self.PROVISION_FIELDS:
            value = req.get(key, extras.get(key))
            if value is not None and value != "":
                fields[key] = value
        topics = [str(t) for t in (req.get("interests") or [])]
        return AgentProfile(
            id=self.provisioned_user_id(name),
            username=name,
            email=f"{name}@federation.local",
            password="federation",
            user_type="user",
            joined_on=self.host.current_round_id,
            is_page=0,
            left_on=None,
            interests=(topics, [1] * len(topics)) if topics else None,
            **fields,
        )

    def provision_accounts(self, requests):
        """Create the account of each agent that decided to join this platform (username = the agent's name; UUID id, profile
        defaults, interests and any profile field from the request) through the server's own registration, and report which were
        created. A name that is already an account is bound as it is, never created twice; one that cannot be a username
        (1-50 characters) is skipped."""
        import dataclasses
        import json

        from YSimulator.YServer.classes.models import User_mgmt

        from .tables import FederationProvisioned

        done = []
        for req in requests:
            gid, name = str(req["global_agent_id"]), str(req["username"])
            with self._lock:
                with Session(self.host.engine) as s:
                    uid = s.scalar(select(User_mgmt.id).where(User_mgmt.username == name))
                if uid is None:
                    if not name.strip() or len(name) > 50:
                        log.warning(
                            "federation: cannot create an account named %r (1-50 characters)", name
                        )
                        continue
                    profile = self._provision_profile(req, name)
                    self.host.register_agents([profile])
                    uid = profile.id
                    with self._session() as s:
                        s.add(
                            FederationProvisioned(
                                user_id=uid,
                                global_agent_id=gid,
                                username=name,
                                profile_json=json.dumps(dataclasses.asdict(profile)),
                            )
                        )
                        s.commit()
                self.record_provisioned(gid, uid, name)
            done.append({"global_agent_id": gid, "local_account_id": str(uid)})
        return done

    def provisioned_accounts(self, client_id, known=()):
        """Profiles of the accounts created here that `client_id` has to give an agent, except the ids in `known` (the ones it plays
        already): the ones nobody adopted that it claims (the first client to ask) and the ones it adopted (offered again so that
        a restarted client gets its agents back)."""
        import json

        from YSimulator.YClient.classes.ray_models import AgentProfile

        from .tables import FederationProvisioned

        out, known = [], {str(k) for k in known}
        with self._lock, self._session() as s:
            for row in s.scalars(
                select(FederationProvisioned).order_by(FederationProvisioned.user_id)
            ).all():
                if row.claimed_by not in (None, client_id) or row.user_id in known:
                    continue
                if row.claimed_by is None:
                    row.claimed_by = client_id
                data = json.loads(row.profile_json)
                if data.get("interests"):
                    data["interests"] = (list(data["interests"][0]), list(data["interests"][1]))
                out.append(AgentProfile(**data))
            s.commit()
        return out

    def mark_adopted(self, client_id, user_ids):
        from .tables import FederationProvisioned

        with self._lock, self._session() as s:
            for uid in user_ids:
                row = s.get(FederationProvisioned, str(uid))
                if row is not None and row.claimed_by in (None, client_id):
                    row.adopted, row.claimed_by = True, client_id
            s.commit()

    # -- membership --------------------------------------------------------------------
    def apply_membership(self, changes):
        from .tables import FederationMembership

        with self._lock, self._session() as s:
            for ch in changes:
                uid = self.user_of(ch.global_agent_id)
                if uid is None:
                    log.warning(
                        "federation: membership change for unknown agent %s ignored",
                        ch.global_agent_id,
                    )
                    continue
                row = s.get(FederationMembership, uid)
                if row is None:
                    s.add(
                        FederationMembership(
                            user_id=uid,
                            global_agent_id=str(ch.global_agent_id),
                            state=ch.state,
                            since_tick=ch.tick,
                            reason=ch.reason,
                        )
                    )
                else:
                    row.state, row.since_tick, row.reason = ch.state, ch.tick, ch.reason
            s.commit()
            self._inactive = None

    def inactive_agent_ids(self):
        """Local agent ids whose state is dormant or left (cached; refreshed by apply_membership)."""
        from .tables import FederationMembership

        with self._lock:
            if self._inactive is None:
                with self._session() as s:
                    self._inactive = set(
                        s.scalars(
                            select(FederationMembership.user_id).where(
                                FederationMembership.state != "active"
                            )
                        ).all()
                    )
            return set(self._inactive)

    def _active(self, s, user_id):
        from .tables import FederationMembership

        row = s.get(FederationMembership, str(user_id))
        return row is None or row.state == "active"

    # -- invisibility of the accounts that are not active (guide 4.10.1) --------------------
    def filter_posts(self, post_ids):
        """post_ids without the posts of accounts that are not active, same order."""
        hidden = self.inactive_agent_ids()
        if not hidden or not post_ids:
            return post_ids
        from YSimulator.YServer.classes.models import Post

        with Session(self.host.engine) as s:
            authors = dict(
                s.execute(select(Post.id, Post.user_id).where(Post.id.in_(list(post_ids)))).all()
            )
        return [p for p in post_ids if authors.get(p) not in hidden]

    def filter_users(self, user_ids):
        """user_ids without the accounts that are not active, same order."""
        hidden = self.inactive_agent_ids()
        return [u for u in user_ids if u not in hidden] if hidden else user_ids

    # -- bus: export -------------------------------------------------------------------
    def _content(self, s, post):
        from YSimulator.YServer.classes.models import Image, Interest, PostTopic, User_mgmt

        user = s.get(User_mgmt, post.user_id)
        topics = [
            i.interest
            for i in s.scalars(
                select(Interest)
                .join(PostTopic, PostTopic.topic_id == Interest.iid)
                .where(PostTopic.post_id == post.id)
                .order_by(Interest.interest)
            ).all()
        ]
        image = s.get(Image, post.image_id) if post.image_id else None
        content = {
            "global_agent_id": self.agent_of(post.user_id),
            "source_ref": f"ysocial://{self.federation_id}/{self.member}/post/{post.id}",
            "kind": "post",
            "text_excerpt": (post.tweet or "")[:TEXT_EXCERPT_MAX],
            "image_ref": image.url if image is not None and image.url else None,
            "topics": topics,
            "lang": (user.language if user is not None and user.language else "en"),
        }
        link = self._news_link(s, post) if "news" in self.crosspost_content else None
        if link:
            content["link"] = (
                link  # P13: written only when the policy asks for news (otherwise the message is unchanged)
            )
        return content

    def _news_link(self, s, post):
        """Link of the article the post is about (or, for a share, of the post it shares); None when there is none."""
        from YSimulator.YServer.classes.models import Article, Post

        for p in (
            post,
            s.get(Post, post.shared_from) if post.shared_from not in (None, -1, "-1") else None,
        ):
            if p is not None and p.news_id not in (None, "", "-1", -1):
                art = s.get(Article, str(p.news_id))
                if art is not None and art.link:
                    return art.link[:LINK_MAX]
        return None

    def export_outbox(self, tick):
        """content.v1 for the posts chosen at this barrier: the ones marked by the agents and, with export_policy
        "all", every root post of the current round. A second call for the same tick gives the same messages.
        """
        from YSimulator.YServer.classes.models import Post

        from .tables import FederationExport, FederationRef

        with self._lock, self._session() as s:
            already = s.scalars(
                select(FederationExport)
                .where(FederationExport.tick == tick)
                .order_by(FederationExport.seq)
            ).all()
            if (
                not already
            ):  # first call for this tick: choose the posts and fix their sequence numbers
                done = set(
                    s.scalars(
                        select(FederationExport.post_id).where(FederationExport.tick.is_not(None))
                    ).all()
                )
                made = set(
                    s.scalars(
                        select(FederationRef.local_id).where(FederationRef.local_kind == "post")
                    ).all()
                )
                candidates = set(
                    s.scalars(
                        select(FederationExport.post_id).where(FederationExport.tick.is_(None))
                    ).all()
                )
                if self.export_policy == "all":
                    candidates |= set(
                        s.scalars(
                            select(Post.id).where(Post.round == self.host.current_round_id)
                        ).all()
                    )
                posts = [s.get(Post, pid) for pid in candidates - done - made]
                pending = sorted(
                    (
                        p
                        for p in posts
                        if p is not None
                        and p.moderated == 0
                        and p.comment_to in (None, "-1", -1)
                        and p.shared_from in (None, "-1", -1)
                        and self._active(s, p.user_id)
                        and self._federated(p.user_id)
                    ),
                    key=lambda p: (p.tweet or "", p.id),
                )  # UUIDs carry no order: the text keeps it stable
                for seq, post in enumerate(pending):
                    s.merge(FederationExport(post_id=post.id, tick=tick, seq=seq))
                s.commit()
                if self.crosspost_mode == "agent_action":
                    self._fix_crossposts(s, tick, pending, len(pending))
                already = s.scalars(
                    select(FederationExport)
                    .where(FederationExport.tick == tick)
                    .order_by(FederationExport.seq)
                ).all()
            out = []
            asked = self._crossposts_of(s, tick) if self.crosspost_mode == "agent_action" else []
            by_post = {r.post_id for r in asked}
            for row in already:
                if (
                    row.post_id in by_post
                ):  # the agent chose where to post it: the cross-posts are the message
                    continue
                post = s.get(Post, row.post_id)
                out.append(
                    Envelope.create(
                        self.federation_id,
                        self.member,
                        COORDINATOR,
                        tick,
                        row.seq,
                        "content.v1",
                        self._content(s, post),
                    )
                )
            for req in asked:
                content = self._content(s, s.get(Post, req.post_id))
                if req.text:
                    content["text_excerpt"] = req.text[:TEXT_EXCERPT_MAX]
                out.append(
                    Envelope.create(
                        self.federation_id,
                        self.member,
                        req.member,
                        tick,
                        req.seq,
                        "crosspost.v1",
                        dict(content, target_account_id=req.account_id),
                    )
                )
            if self.emit_exposures:
                for row in self._exposure_rows(s, tick):
                    if not self._federated(row.viewer_uid):
                        continue
                    out.append(
                        Envelope.create(
                            self.federation_id,
                            self.member,
                            COORDINATOR,
                            tick,
                            max((e.seq for e in out), default=-1) + 1,
                            "exposure.v1",
                            {
                                "viewer_global_agent_id": self.agent_of(row.viewer_uid),
                                "source_ref": row.source_ref,
                                "tick": tick,
                                "exact": bool(row.exact),
                                "kind": row.kind,
                                "tie": row.tie,
                            },
                        )
                    )
            return out

    def _tie(self, s, viewer, author):
        """none / follow / mutual between a viewer and the author of a post, from the latest follow rows."""
        from YSimulator.YServer.classes.models import Follow, Round

        def follows(a, b):
            row = s.execute(
                select(Follow, Round)
                .outerjoin(Round, Round.id == Follow.round)
                .where(Follow.user_id == a, Follow.follower_id == b)
                .order_by(Round.day.desc(), Round.hour.desc())
            ).first()
            return row is not None and row[0].action == "follow"

        if not follows(viewer, author):
            return "none"
        return "mutual" if follows(author, viewer) else "follow"

    def _exposure_rows(self, s, tick):
        """Views (posts recommended in the round: approximate, exact = false) and interactions (reaction, comment or share:
        exact) of active accounts with the materialised cross-posts of the round of the tick, in a stable order.
        """
        from YSimulator.YServer.classes.models import Post, Reaction, Recommendation, Round

        from .tables import FederationExposure, FederationRef, FederationState

        def stored():
            return list(
                s.scalars(
                    select(FederationExposure)
                    .where(FederationExposure.tick == tick)
                    .order_by(FederationExposure.seq)
                ).all()
            )

        done = s.get(FederationState, "exposure_tick")
        if done is not None and int(done.value) >= tick:
            return stored()
        day, hour = self.from_tick(tick)
        rnd = s.scalars(select(Round).where(Round.day == day, Round.hour == hour)).first()
        refs = (
            {
                r.local_id: r.source_ref
                for r in s.scalars(
                    select(FederationRef).where(FederationRef.local_kind == "post")
                ).all()
            }
            if rnd
            else {}
        )
        if refs:
            author = {
                pid: uid
                for pid, uid in s.execute(
                    select(Post.id, Post.user_id).where(Post.id.in_(list(refs)))
                ).all()
            }
            found = {}
            humans = self._human_uids()  # people are not part of the group mechanisms (INV-15)

            def add(viewer, pid, kind, exact):
                if (
                    viewer is None
                    or viewer == author.get(pid)
                    or viewer in humans
                    or not self._active(s, viewer)
                ):
                    return
                found.setdefault((str(viewer), refs[pid], kind), (pid, exact))

            for rec in s.scalars(
                select(Recommendation).where(Recommendation.round == rnd.id)
            ).all():
                for raw in (
                    (rec.post_ids or "")
                    .replace("[", "")
                    .replace("]", "")
                    .replace('"', "")
                    .split(",")
                ):
                    if raw.strip() in refs:
                        add(rec.user_id, raw.strip(), "view", False)
            for r in s.scalars(
                select(Reaction).where(Reaction.round == rnd.id, Reaction.post_id.in_(list(refs)))
            ).all():
                add(r.user_id, r.post_id, "interact", True)
            for c in s.scalars(
                select(Post).where(
                    Post.round == rnd.id,
                    Post.comment_to.in_(list(refs)) | Post.shared_from.in_(list(refs)),
                )
            ).all():
                add(
                    c.user_id,
                    c.comment_to if c.comment_to in refs else c.shared_from,
                    "interact",
                    True,
                )
            for seq, ((viewer, ref, kind), (pid, exact)) in enumerate(sorted(found.items())):
                s.add(
                    FederationExposure(
                        tick=tick,
                        seq=seq,
                        viewer_uid=viewer,
                        source_ref=ref,
                        kind=kind,
                        tie=self._tie(s, viewer, author[pid]),
                        exact=int(exact),
                    )
                )
        if done is None:
            s.add(FederationState(key="exposure_tick", value=str(tick)))
        else:
            done.value = str(tick)
        s.commit()
        return stored()

    def mark_for_export(self, post_id, targets=None):
        """The agent chose to cross-post this post (D-07): it will be exported at the next barrier.

        targets (crosspost.mode = agent_action): [{"member", "text"}], where the agent wants it and with which text.
        """
        from .tables import FederationCrosspost, FederationExport

        with self._lock, self._session() as s:
            if s.get(FederationExport, str(post_id)) is None:
                s.add(FederationExport(post_id=str(post_id), tick=None, seq=None))
            if self.crosspost_mode == "agent_action":
                for target in targets or []:
                    member = str(target.get("member") or "")
                    if (
                        member
                        and member != self.member
                        and s.get(FederationCrosspost, (str(post_id), member)) is None
                    ):
                        s.add(
                            FederationCrosspost(
                                post_id=str(post_id),
                                member=member,
                                text=str(target.get("text") or ""),
                            )
                        )
            s.commit()

    # -- agent-action cross-posts (F6.2) -------------------------------------------------
    def set_destinations(self, destinations):
        self._destinations = {str(k): list(v) for k, v in (destinations or {}).items()}

    def destination_members(self, user_id):
        """Members where this account's agent could cross-post now (as of the last barrier)."""
        return sorted(d["member"] for d in self._destinations.get(self.agent_of(user_id), []))

    def destination_info(self, user_id):
        """P15: the same destinations with the platform type and the label of each: [{member, platform, name}], sorted by member.
        Several members may share a platform type, so a client cannot read the type from the member name.
        """
        return sorted(
            (
                {
                    "member": d["member"],
                    "platform": d.get("platform") or d["member"],
                    "name": d.get("name") or d["member"],
                }
                for d in self._destinations.get(self.agent_of(user_id), [])
            ),
            key=lambda i: i["member"],
        )

    def _fix_crossposts(self, s, tick, posts, first_seq):
        """First export of the tick: give each requested cross-post its account, tick and sequence number (a request
        for a platform where the author has no active account is dropped)."""
        from sqlalchemy import select as _select

        from .tables import FederationCrosspost

        seq = first_seq
        for post in posts:
            wanted = self._destinations.get(self.agent_of(post.user_id), [])
            rows = s.scalars(
                _select(FederationCrosspost)
                .where(FederationCrosspost.post_id == post.id, FederationCrosspost.tick.is_(None))
                .order_by(FederationCrosspost.member)
            ).all()
            for row in rows:
                account = next(
                    (d["local_account_id"] for d in wanted if d["member"] == row.member), None
                )
                row.tick = tick
                if account is None:
                    log.info(
                        "federation: cross-post of post %s to %s dropped: no active account",
                        post.id,
                        row.member,
                    )
                    continue
                row.account_id, row.seq = str(account), seq
                seq += 1
        s.commit()

    def _crossposts_of(self, s, tick):
        from .tables import FederationCrosspost

        return list(
            s.scalars(
                select(FederationCrosspost)
                .where(FederationCrosspost.tick == tick, FederationCrosspost.seq.is_not(None))
                .order_by(FederationCrosspost.seq)
            ).all()
        )

    # -- bus: ingest -------------------------------------------------------------------
    def _topic_ids(self, s, names, tick, source_member):
        """Topic migration: ids of the platform's topics for the names a cross-post carries, matched ignoring case; the
        ones the platform does not have are created (and recorded in federation_topic). Payload order, no duplicates.
        """
        from sqlalchemy import func

        from YSimulator.YServer.classes.models import Interest

        from .tables import FederationTopic

        ids, seen = [], set()
        for name in names or []:
            name = " ".join(str(name).split())
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            iid = s.scalars(
                select(Interest.iid)
                .where(func.lower(Interest.interest) == name.lower())
                .order_by(Interest.iid)
            ).first()
            if iid is None and not self.create_topics:
                continue
            if iid is None:
                iid = str(uuid.uuid4())
                s.add(Interest(iid=iid, interest=name))
                s.add(
                    FederationTopic(
                        name=name,
                        interest_id=iid,
                        created_tick=int(tick),
                        source_member=source_member,
                    )
                )
                s.flush()
            ids.append(iid)
        return ids

    def ingest_inbox(self, tick, envelopes):
        from YSimulator.YServer.classes.models import Post, PostTopic, User_mgmt

        from .tables import FederationRef

        report = IngestReport()

        def skip(reason):
            report.skipped[reason] = report.skipped.get(reason, 0) + 1

        with self._lock, self._session() as s:
            for env in envelopes:
                if env.payload_type != "crosspost.v1":
                    skip("skipped_unsupported")
                    continue
                if (
                    s.scalar(
                        select(FederationRef.local_id).where(
                            FederationRef.fed_msg_id == env.fed_msg_id
                        )
                    )
                    is not None
                ):
                    report.duplicates += 1  # INV-05: already materialised
                    continue
                payload = env.payload
                uid = str(payload["target_account_id"])
                if s.get(User_mgmt, uid) is None or not self._active(s, uid):
                    skip("skipped_ineligible")
                    continue
                post_id = str(uuid.uuid4())
                s.add(
                    Post(
                        id=post_id,
                        tweet=payload["text_excerpt"],
                        user_id=uid,
                        comment_to="-1",
                        thread_id=post_id,
                        round=self.host.current_round_id,
                    )
                )
                for topic_id in self._topic_ids(s, payload.get("topics"), tick, env.source_member):
                    s.add(PostTopic(id=str(uuid.uuid4()), post_id=post_id, topic_id=topic_id))
                s.add(
                    FederationRef(
                        local_kind="post",
                        local_id=post_id,
                        source_ref=payload["source_ref"],
                        fed_msg_id=env.fed_msg_id,
                    )
                )
                s.commit()  # post, topics and reference together: a crash leaves nothing, the message comes again
                self.host.recent_posts_cache.append(post_id)
                self.host.recent_posts_cache[:] = self.host.recent_posts_cache[-50:]
                report.materialized += 1
        return report

    def affective_report(self, day):
        """Native stress/reward of the active accounts at the last round of the canonical day (F4.1): the value that
        server.get_stress_reward computes (latest aggregate + later variations in the 24-round window, clamped), read
        without writing; actions = posts and reactions of the account in the day, exposures = posts recommended to it.
        """
        from sqlalchemy import and_, func, or_
        from ysocial_federation.schemas import AffectiveSample

        from YSimulator.YServer.classes.models import (
            Post,
            Reaction,
            Recommendation,
            Round,
            StressReward,
        )

        from .tables import FederationMembership

        with self._lock, self._session() as s:
            rounds = s.scalars(
                select(Round).where(Round.day == int(day)).order_by(Round.hour)
            ).all()
            if not rounds:
                return []
            last = rounds[-1]
            ids = [r.id for r in rounds]
            td, th = int(last.day or 0), int(last.hour or 0)

            def before(d, h):
                return or_(Round.day < d, and_(Round.day == d, Round.hour < h))

            def at_or_before(d, h):
                return or_(Round.day < d, and_(Round.day == d, Round.hour <= h))

            def at_or_after(d, h):
                return or_(Round.day > d, and_(Round.day == d, Round.hour >= h))

            window = s.scalars(
                select(Round)
                .where(at_or_before(td, th))
                .order_by(Round.day.desc(), Round.hour.desc())
                .limit(25)
            ).all()
            first = window[-1] if window else last

            def value(uid, variable):
                row = s.execute(
                    select(StressReward, Round)
                    .join(Round, Round.id == StressReward.tid)
                    .where(
                        StressReward.uid == uid,
                        StressReward.variable == variable,
                        StressReward.type == "aggregate",
                        before(td, th),
                    )
                    .order_by(Round.day.desc(), Round.hour.desc())
                ).first()
                base, lower = 0.0, at_or_after(int(first.day or 0), int(first.hour or 0))
                if row is not None:
                    base, lower = float(row[0].value), at_or_after(
                        int(row[1].day or 0), int(row[1].hour or 0)
                    )
                total = s.scalar(
                    select(func.coalesce(func.sum(StressReward.value), 0.0))
                    .join(Round, Round.id == StressReward.tid)
                    .where(
                        StressReward.uid == uid,
                        StressReward.variable == variable,
                        StressReward.type == "variation",
                        lower,
                        at_or_before(td, th),
                    )
                )
                return max(0.0, min(1.0, base + float(total or 0.0)))

            out = []
            humans = self._human_uids()  # people are not part of the group mechanisms (INV-15)
            for m in s.scalars(
                select(FederationMembership)
                .where(FederationMembership.state == "active")
                .order_by(FederationMembership.user_id)
            ).all():
                uid = m.user_id
                if uid in humans:
                    continue
                posts = s.scalar(
                    select(func.count(Post.id)).where(Post.user_id == uid, Post.round.in_(ids))
                )
                reacts = s.scalar(
                    select(func.count(Reaction.id)).where(
                        Reaction.user_id == uid, Reaction.round.in_(ids)
                    )
                )
                exposures = 0
                for rec in s.scalars(
                    select(Recommendation).where(
                        Recommendation.user_id == uid, Recommendation.round.in_(ids)
                    )
                ).all():
                    exposures += len(
                        [
                            p
                            for p in (rec.post_ids or "").strip("[]").split(",")
                            if p.strip().strip("\"'")
                        ]
                    )
                out.append(
                    AffectiveSample(
                        self.agent_of(uid),
                        int(day),
                        value(uid, "stress"),
                        value(uid, "reward"),
                        int(posts or 0) + int(reacts or 0),
                        exposures,
                    )
                )
            return out

    def churned_agents(self, day):
        """Agents of this platform that left on their own (users.left_on set at a round up to the end of the day, F4.5): the
        coordinator records them as left with reason churn. Only accounts the federation still sees as active.
        """
        from YSimulator.YServer.classes.models import Round, User_mgmt

        from .tables import FederationMembership

        with self._lock, self._session() as s:
            rounds = set(s.scalars(select(Round.id).where(Round.day <= int(day))).all())
            out = []
            humans = self._human_uids()  # people never churn (INV-15)
            for row in s.scalars(
                select(FederationMembership).where(FederationMembership.state == "active")
            ).all():
                if row.user_id in humans:
                    continue
                user = s.get(User_mgmt, row.user_id)
                if user is not None and user.left_on is not None and user.left_on in rounds:
                    out.append(row.global_agent_id)
            return sorted(out)

    def apply_attention(self, day, multipliers):
        """Store the multipliers of the day (F4.3): accounts that are not in the dictionary go back to 1; unknown agents are
        ignored. The client reads them with server.get_federation_attention and applies them to how many actions an agent
        takes in a slot."""
        from YSimulator.YServer.classes.models import User_mgmt

        from .tables import FederationAttention

        with self._lock, self._session() as s:
            known = (
                set(s.scalars(select(User_mgmt.id)).all()) - self._human_uids()
            )  # people have no attention multiplier
            s.query(FederationAttention).delete()
            for gid, value in sorted((multipliers or {}).items()):
                uid = self.user_of(gid)
                if uid in known and float(value) != 1.0:
                    s.add(FederationAttention(user_id=uid, day=int(day), multiplier=float(value)))
            s.commit()

    def attention_multipliers(self):
        """{local agent id: multiplier} of the current day (accounts not listed: 1)."""
        from .tables import FederationAttention

        with self._lock, self._session() as s:
            return {r.user_id: r.multiplier for r in s.scalars(select(FederationAttention)).all()}
