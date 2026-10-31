"""PlatformAdapter of YSimulator (microblogging, HPC backend).

Clock (F2.3): canonical time of the server (day, slot), base 1 (day 1, slot 1 is the first round; F0.4).
Bus and membership (F3.4c), same design as YServer:
- apply_membership stores the state of each account in federation_membership; accounts that are not active are
  left out of recommendations, follow suggestions and topic search (filter_posts / filter_users, called by the server) and the
  clients ask which they are (server.get_federation_inactive_agents) so they do not act.
- export_outbox turns the root posts that the agents marked for cross-post (attribute `crosspost` of the POST action), or
  all root posts of active authors with export_policy = "all", into content.v1 for the coordinator.
- ingest_inbox materialises crosspost.v1 as a post of the author, once per fed_msg_id (INV-05), with a federation_ref row.
Attention and affective reports are filled in by F4.

`host` is the object that owns the database: it needs `engine`, `post_service`, `current_round_id` and `recent_posts_cache`
(the OrchestratorServer; a small stand-in in tests)."""

import logging
import threading
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ysocial_federation.adapter import IngestReport, PlatformAdapter
from ysocial_federation.envelope import COORDINATOR, Envelope
from ysocial_federation.schemas import TEXT_EXCERPT_MAX
from ysocial_federation.timebase import ONE_BASED

log = logging.getLogger("ysimulator.federation")


class YSimulatorAdapter(PlatformAdapter):
    platform = "microblogging"

    def __init__(self, member, federation_id=1, host=None, accounts=None, export_policy="marked"):
        """accounts: {global_agent_id: local agent id}; without an entry the global id is the local agent id."""
        if export_policy not in ("marked", "all"):
            raise ValueError("export_policy must be 'marked' or 'all'")
        self.member = member
        self.federation_id = federation_id
        self.host = host
        self.export_policy = export_policy
        self._accounts = {str(k): str(v) for k, v in (accounts or {}).items()}
        self._by_user = {v: k for k, v in self._accounts.items()}
        self._lock = threading.RLock()
        self._inactive = None  # cache of the ids that are not active; loaded from the table on first use

    # -- clock -------------------------------------------------------------------------
    def to_tick(self, local_round):
        day, slot = local_round
        return ONE_BASED.to_tick(int(day), int(slot))

    def from_tick(self, tick):
        return ONE_BASED.from_tick(tick)

    # -- identity and database ---------------------------------------------------------
    def user_of(self, global_agent_id):
        return self._accounts.get(str(global_agent_id), str(global_agent_id))

    def agent_of(self, user_id):
        return self._by_user.get(str(user_id), str(user_id))

    def _session(self):
        from .tables import ensure_tables

        engine = self.host.engine
        ensure_tables(engine)
        return Session(engine)

    # -- membership --------------------------------------------------------------------
    def apply_membership(self, changes):
        from .tables import FederationMembership

        with self._lock, self._session() as s:
            for ch in changes:
                uid = self.user_of(ch.global_agent_id)
                row = s.get(FederationMembership, uid)
                if row is None:
                    s.add(FederationMembership(user_id=uid, global_agent_id=str(ch.global_agent_id), state=ch.state,
                                               since_tick=ch.tick, reason=ch.reason))
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
                    self._inactive = set(s.scalars(select(FederationMembership.user_id)
                                                   .where(FederationMembership.state != "active")).all())
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
            authors = dict(s.execute(select(Post.id, Post.user_id).where(Post.id.in_(list(post_ids)))).all())
        return [p for p in post_ids if authors.get(p) not in hidden]

    def filter_users(self, user_ids):
        """user_ids without the accounts that are not active, same order."""
        hidden = self.inactive_agent_ids()
        return [u for u in user_ids if u not in hidden] if hidden else user_ids

    # -- bus: export -------------------------------------------------------------------
    def _content(self, s, post):
        from YSimulator.YServer.classes.models import Image, Interest, PostTopic, User_mgmt

        user = s.get(User_mgmt, post.user_id)
        topics = [i.interest for i in s.scalars(select(Interest).join(PostTopic, PostTopic.topic_id == Interest.iid)
                                                .where(PostTopic.post_id == post.id).order_by(Interest.interest)).all()]
        image = s.get(Image, post.image_id) if post.image_id else None
        return {"global_agent_id": self.agent_of(post.user_id),
                "source_ref": f"ysocial://{self.federation_id}/{self.member}/post/{post.id}",
                "kind": "post", "text_excerpt": (post.tweet or "")[:TEXT_EXCERPT_MAX],
                "image_ref": image.url if image is not None and image.url else None,
                "topics": topics, "lang": (user.language if user is not None and user.language else "en")}

    def export_outbox(self, tick):
        """content.v1 for the posts chosen at this barrier: the ones marked by the agents and, with export_policy
        "all", every root post of the current round. A second call for the same tick gives the same messages."""
        from YSimulator.YServer.classes.models import Post
        from .tables import FederationExport, FederationRef

        with self._lock, self._session() as s:
            already = s.scalars(select(FederationExport).where(FederationExport.tick == tick)
                                .order_by(FederationExport.seq)).all()
            if not already:  # first call for this tick: choose the posts and fix their sequence numbers
                done = set(s.scalars(select(FederationExport.post_id).where(FederationExport.tick.is_not(None))).all())
                made = set(s.scalars(select(FederationRef.local_id).where(FederationRef.local_kind == "post")).all())
                candidates = set(s.scalars(select(FederationExport.post_id).where(FederationExport.tick.is_(None))).all())
                if self.export_policy == "all":
                    candidates |= set(s.scalars(select(Post.id).where(Post.round == self.host.current_round_id)).all())
                posts = [s.get(Post, pid) for pid in candidates - done - made]
                pending = sorted((p for p in posts if p is not None and p.moderated == 0
                                  and p.comment_to in (None, "-1", -1) and p.shared_from in (None, "-1", -1)
                                  and self._active(s, p.user_id)),
                                 key=lambda p: (p.tweet or "", p.id))  # UUIDs carry no order: the text keeps it stable
                for seq, post in enumerate(pending):
                    s.merge(FederationExport(post_id=post.id, tick=tick, seq=seq))
                s.commit()
                already = s.scalars(select(FederationExport).where(FederationExport.tick == tick)
                                    .order_by(FederationExport.seq)).all()
            out = []
            for row in already:
                post = s.get(Post, row.post_id)
                out.append(Envelope.create(self.federation_id, self.member, COORDINATOR, tick, row.seq, "content.v1",
                                           self._content(s, post)))
            return out

    def mark_for_export(self, post_id):
        """The agent chose to cross-post this post (D-07): it will be exported at the next barrier."""
        from .tables import FederationExport

        with self._lock, self._session() as s:
            if s.get(FederationExport, str(post_id)) is None:
                s.add(FederationExport(post_id=str(post_id), tick=None, seq=None))
                s.commit()

    # -- bus: ingest -------------------------------------------------------------------
    def _topic_ids(self, names):
        ids = []
        for name in names or []:
            tid = self.host.post_service.get_topic_by_name(str(name))
            if tid and tid not in ids:
                ids.append(tid)
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
                if s.scalar(select(FederationRef.local_id).where(FederationRef.fed_msg_id == env.fed_msg_id)) is not None:
                    report.duplicates += 1  # INV-05: already materialised
                    continue
                payload = env.payload
                uid = str(payload["target_account_id"])
                if s.get(User_mgmt, uid) is None or not self._active(s, uid):
                    skip("skipped_ineligible")
                    continue
                post_id = str(uuid.uuid4())
                s.add(Post(id=post_id, tweet=payload["text_excerpt"], user_id=uid, comment_to="-1", thread_id=post_id,
                           round=self.host.current_round_id))
                for topic_id in self._topic_ids(payload.get("topics")):
                    s.add(PostTopic(id=str(uuid.uuid4()), post_id=post_id, topic_id=topic_id))
                s.add(FederationRef(local_kind="post", local_id=post_id, source_ref=payload["source_ref"],
                                    fed_msg_id=env.fed_msg_id))
                s.commit()  # post, topics and reference together: a crash leaves nothing, the message comes again
                self.host.recent_posts_cache.append(post_id)
                self.host.recent_posts_cache[:] = self.host.recent_posts_cache[-50:]
                report.materialized += 1
        return report

    def affective_report(self, day):
        return []  # F4

    def apply_attention(self, day, multipliers):
        return None  # F4
