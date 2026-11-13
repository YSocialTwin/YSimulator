"""The human gateway of YSimulator (microblogging, HPC backend): one person, one account, the actions of the platform.

YSimulator's server is a Ray actor with no HTTP surface, so this gateway works on the database of the experiment, the
same way YWeb always did for people on this backend, with two differences that the federation needs: the person has an
identity ``human:<id>`` (table ``federation_human``) that never falls back to the local id, and a post that asks for
``crosspost_to`` is marked for the coordinator exactly like the post of an agent (``federation_export`` and, with
``crosspost.mode = agent_action``, ``federation_crosspost``). It works with the server running or stopped: the rows it
writes are plain inserts and the server reads them at its next barrier. Requests are serialised by a file lock
(``handle``) so that two requests never write at once.

Used by ``run_human_gateway.py`` (one JSON request on stdin, one answer on stdout)."""

from __future__ import annotations

import fcntl
import re
import uuid
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

MAX_ACTIONS = 20
MAX_TEXT = 2000
USERNAME = re.compile(r"^[A-Za-z0-9_]{1,15}$")
HUMAN_ID = re.compile(r"^human:[A-Za-z0-9_.:-]{1,70}$")
REACTIONS = ("like", "dislike")
OPS = ("ensure", "state", "actions")


class HumanGateway:
    def __init__(
        self, engine, crosspost_mode: str = "coordinator_rule", member: Optional[str] = None
    ):
        self.engine = engine
        self.crosspost_mode = crosspost_mode
        self.member = member

    # -- helpers ---------------------------------------------------------------------------------
    def _session(self) -> Session:
        from .tables import ensure_tables

        ensure_tables(self.engine)
        return Session(self.engine)

    @staticmethod
    def _round(s) -> Optional[str]:
        from YSimulator.YServer.classes.models import Round

        row = s.scalars(select(Round).order_by(Round.day.desc(), Round.hour.desc())).first()
        return row.id if row is not None else None

    @staticmethod
    def _human(s, human_key=None, user_id=None):
        from .tables import FederationHuman

        if human_key is not None:
            return s.get(FederationHuman, human_key)
        return s.scalars(
            select(FederationHuman).where(FederationHuman.user_id == str(user_id))
        ).first()

    # -- account ---------------------------------------------------------------------------------
    def ensure(
        self, human_key: Any, username: Any, language: Any = None, human_id: Any = None
    ) -> tuple:
        """Create the account of a person (idempotent); a name used by an account that is not theirs is refused."""
        from YSimulator.YServer.classes.models import User_mgmt

        from .tables import FederationHuman

        if not isinstance(human_key, str) or not 1 <= len(human_key) <= 64:
            raise ValueError("human_key")
        if not isinstance(username, str) or not USERNAME.match(username):
            raise ValueError("username")
        if human_id is not None and (not isinstance(human_id, str) or not HUMAN_ID.match(human_id)):
            raise ValueError("human_id")
        with self._session() as s:
            row, created = self._human(s, human_key), False
            if row is None:
                if (
                    s.scalars(select(User_mgmt).where(User_mgmt.username == username)).first()
                    is not None
                ):
                    return 409, {"ok": False, "code": "username_taken"}
                uid = str(uuid.uuid4())
                s.add(
                    User_mgmt(
                        id=uid,
                        username=username,
                        email=f"{username}@human.local",
                        password="",
                        user_type="human",
                        leaning="neutral",
                        age=30,
                        language=str(language or "en"),
                        owner="human",
                        joined_on=self._round(s),
                        round_actions=1,
                        daily_activity_level=1,
                        is_page=0,
                    )
                )
                row = FederationHuman(human_key=human_key, user_id=uid, human_id=human_id)
                s.add(row)
                created = True
            elif human_id is not None:
                if row.human_id not in (None, human_id):
                    return 409, {"ok": False, "code": "human_id_conflict"}
                row.human_id = human_id
            s.commit()
            user = s.get(User_mgmt, row.user_id)
            return 200, {
                "ok": True,
                "account_id": row.user_id,
                "username": user.username if user else username,
                "human_id": row.human_id,
                "created": created,
            }

    def state(self, account_id: Any) -> tuple:
        with self._session() as s:
            row = self._human(s, user_id=account_id)
            if row is None:
                return 403, {"ok": False, "code": "not_a_human_account"}
            return 200, {
                "ok": True,
                "account_id": row.user_id,
                "human_id": row.human_id,
                "round": self._round(s),
            }

    # -- actions ---------------------------------------------------------------------------------
    def actions(self, account_id: Any, actions: Any) -> tuple:
        if not isinstance(actions, list) or not 0 < len(actions) <= MAX_ACTIONS:
            raise ValueError("actions")
        with self._session() as s:
            if self._human(s, user_id=account_id) is None:
                return 403, {"ok": False, "code": "not_a_human_account"}
            rnd = self._round(s)
            if rnd is None:
                return 503, {"ok": False, "code": "no_round"}
            results = [self._one(s, str(account_id), rnd, act) for act in actions]
        return 200, {"ok": all(r["ok"] for r in results), "results": results}

    def _one(self, s, uid: str, rnd: str, act: Any) -> dict:
        kind = act.get("type") if isinstance(act, dict) else None
        try:
            if kind in ("post", "share"):
                out = self._publish(s, uid, rnd, kind, act)
            elif kind == "comment":
                out = self._publish(s, uid, rnd, "comment", act)
            elif kind == "reaction":
                out = self._reaction(s, uid, rnd, act)
            elif kind in ("follow", "unfollow"):
                out = self._follow(s, uid, rnd, kind, act)
            else:
                raise ValueError("type")
            s.commit()
        except ValueError as exc:
            s.rollback()
            return {"type": kind, "ok": False, "status": 400, "code": f"invalid_{exc}"}
        except LookupError as exc:
            s.rollback()
            return {"type": kind, "ok": False, "status": 404, "code": f"unknown_{exc}"}
        return {"type": kind, "ok": True, "status": 200, **out}

    @staticmethod
    def _text(act, required=True) -> str:
        text = act.get("text")
        if text is None and not required:
            return ""
        if not isinstance(text, str) or (required and not text.strip()) or len(text) > MAX_TEXT:
            raise ValueError("text")
        return text.strip()

    @staticmethod
    def _ref(act, key) -> str:
        v = act.get(key)
        if not isinstance(v, str) or not v:
            raise ValueError(key)
        return v

    @staticmethod
    def _targets(act):
        targets = act.get("crosspost_to")
        if targets is None:
            return None
        if (
            not isinstance(targets, list)
            or not targets
            or not all(
                isinstance(t, dict)
                and isinstance(t.get("member"), str)
                and t["member"]
                and isinstance(t.get("text"), str)
                for t in targets
            )
        ):
            raise ValueError("crosspost_to")
        return [{"member": t["member"], "text": t["text"]} for t in targets]

    def _publish(self, s, uid, rnd, kind, act) -> dict:
        from YSimulator.YServer.classes.models import (
            Hashtag,
            Interest,
            Mention,
            Post,
            PostHashtag,
            PostTopic,
            User_mgmt,
        )

        text = self._text(act, required=kind != "share")
        if kind == "share" and not text:
            text = ""
        parent = None
        if kind in ("comment", "share"):
            parent = s.get(Post, self._ref(act, "post_id"))
            if parent is None:
                raise LookupError("post")
        topics = act.get("topics", []) if kind == "post" else []
        if not isinstance(topics, list) or not all(isinstance(t, str) for t in topics):
            raise ValueError("topics")
        targets = self._targets(act) if kind in ("post", "share") else None
        pid = str(uuid.uuid4())
        post = Post(id=pid, tweet=text, user_id=uid, round=rnd, comment_to="-1", shared_from="-1")
        if kind == "comment":
            post.comment_to, post.thread_id = parent.id, parent.thread_id or parent.id
        else:
            post.thread_id = pid
            if kind == "share":
                post.shared_from = parent.id
        s.add(post)
        s.flush()
        for tag in dict.fromkeys(re.findall(r"#(\w+)", text)):
            h = s.scalars(select(Hashtag).where(Hashtag.hashtag == "#" + tag)).first()
            if h is None:
                h = Hashtag(id=str(uuid.uuid4()), hashtag="#" + tag)
                s.add(h)
                s.flush()
            s.add(PostHashtag(id=str(uuid.uuid4()), post_id=pid, hashtag_id=h.id))
        for name in dict.fromkeys(re.findall(r"@(\w+)", text)):
            u = s.scalars(select(User_mgmt).where(User_mgmt.username == name)).first()
            if u is not None:
                s.add(
                    Mention(id=str(uuid.uuid4()), user_id=u.id, post_id=pid, round=rnd, answered=0)
                )
        for name in dict.fromkeys(" ".join(t.split()) for t in topics if t.strip()):
            iid = s.scalars(select(Interest.iid).where(Interest.interest == name)).first()
            if iid is None:
                iid = str(uuid.uuid4())
                s.add(Interest(iid=iid, interest=name))
                s.flush()
            s.add(PostTopic(id=str(uuid.uuid4()), post_id=pid, topic_id=iid))
        if targets:
            self._mark(s, pid, targets)
        return {"post_id": pid}

    def _mark(self, s, post_id, targets) -> None:
        """The same rows ``YSimulatorAdapter.mark_for_export`` writes for the post of an agent."""
        from .tables import FederationCrosspost, FederationExport

        if s.get(FederationExport, post_id) is None:
            s.add(FederationExport(post_id=post_id, tick=None, seq=None))
        if self.crosspost_mode == "agent_action":
            for t in targets:
                if (
                    t["member"] != self.member
                    and s.get(FederationCrosspost, (post_id, t["member"])) is None
                ):
                    s.add(FederationCrosspost(post_id=post_id, member=t["member"], text=t["text"]))

    def _reaction(self, s, uid, rnd, act) -> dict:
        from YSimulator.YServer.classes.models import Post, Reaction

        if act.get("reaction") not in REACTIONS:
            raise ValueError("reaction")
        pid = self._ref(act, "post_id")
        if s.get(Post, pid) is None:
            raise LookupError("post")
        s.add(
            Reaction(
                id=str(uuid.uuid4()), post_id=pid, user_id=uid, type=act["reaction"], round=rnd
            )
        )
        return {}

    def _follow(self, s, uid, rnd, kind, act) -> dict:
        from YSimulator.YServer.classes.models import Follow, User_mgmt

        target = self._ref(act, "target")
        if target == uid:
            raise ValueError("target")
        if s.get(User_mgmt, target) is None:
            raise LookupError("user")
        # same convention as the follow processor: user_id is the followed account, follower_id the one who acts
        s.add(Follow(id=str(uuid.uuid4()), user_id=target, follower_id=uid, action=kind, round=rnd))
        return {}


def dispatch(gw: HumanGateway, op: str, body: Any) -> tuple:
    """One request: ``(status, answer)``; malformed input is a 400, never an exception."""
    if op not in OPS or not isinstance(body, dict):
        return 400, {"ok": False, "code": "invalid_request"}
    try:
        if op == "ensure":
            return gw.ensure(
                body.get("human_key"),
                body.get("username"),
                body.get("language"),
                body.get("human_id"),
            )
        if op == "state":
            return gw.state(body.get("account_id"))
        return gw.actions(body.get("account_id"), body.get("actions"))
    except ValueError as exc:
        return 400, {"ok": False, "code": f"invalid_{exc}"}


def handle(lock_path, gw: HumanGateway, op: str, body: Any) -> tuple:
    """``dispatch`` under an exclusive file lock (two gateway processes never write at once)."""
    with open(lock_path, "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            return dispatch(gw, op, body)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
