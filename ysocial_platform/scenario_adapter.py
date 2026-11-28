"""HPC materialization adapter (piano tecnico §19): same 21-step shape as
``adapters/standard.py``, but every id is a generated UUID string instead
of a database autoincrement, and every real-table write goes through a
*separate*, independent SQLAlchemy session (``hpc_session.py``) bound
directly to the experiment's physical sqlite file using YSimulator's own
ORM models -- not the Flask-SQLAlchemy ``db_exp`` bind, whose core models
are Integer-typed and do not match HPC's real schema (see
``hpc_session.py``'s module docstring for the full reasoning, verified by
reading ``external/YSimulator`` riga per riga).

**Atomicity, and where it differs from Standard (decisions.md §F7.2)**:
Standard gets a true single transaction for free, because core and
``sd_*`` tables share one Flask-SQLAlchemy session/connection. HPC cannot:
the real content (``Post`` and satellites, YSimulator's models) and this
plugin's own bookkeeping (``sd_publication``/``sd_id_mapping``, this
plugin's models) would otherwise live on two *different* SQLAlchemy
engines pointed at the same physical file, which cannot share one
transaction. This adapter avoids that split by doing **every** write of
a publish -- real content *and* ``sd_*`` bookkeeping alike -- through the
*same* ``hpc_session(exp)`` object: a plain (non-Flask) ``sqlalchemy.orm.Session``
happily accepts ORM instances of this plugin's own classes
(``ScenarioDesignPublication``, ``ScenarioDesignIdMapping``) alongside
YSimulator's, regardless of their Flask-specific ``__bind_key__``
attribute, as long as they are instances added to that one session. One
commit (step 19) persists both halves together; any exception before that
commit discards everything, same guarantee as Standard. Only the
scenario's own Flask-SQLAlchemy-tracked object (loaded by the caller
before this adapter runs) is stale afterwards -- ``db.session.expire_all()``
is called once the write session commits so any later read in the same
request re-fetches current data, never silently serving the pre-publish
row.
"""
from __future__ import annotations

import uuid
from datetime import datetime

# Publication adapter of this platform. It started as a copy of the plugin's own adapter and keeps its body
# unchanged (a test of the core compares both); what comes from the plugin arrives through ``S``, the plugin's
# ``kits.support`` handed over to the driver (SCENARIO_API 1.3), because a platform cannot import the plugin.
from . import scenario_design as _scenario_design

S = _scenario_design.support()
MaterializationAdapter = S.MaterializationAdapter
MaterializationAdapterError = S.MaterializationAdapterError
PreviewResult = S.PreviewResult
PublishResult = S.PublishResult
ValidationResult = S.ValidationResult
post_attributes = S.post_attributes
_generation_constraints = S._generation_constraints
_hashtags_from_constraints = S._hashtags_from_constraints
_load_scenario_graph = S._load_scenario_graph
compute_experiment_fingerprint = S.compute_experiment_fingerprint
_h = S.hpc_session
hpc_emotion_ids = _h.hpc_emotion_ids
hpc_latest_round = _h.hpc_latest_round
hpc_session = _h.hpc_session
hpc_user_exists = _h.hpc_user_exists
MetadataMappingError = S.MetadataMappingError
build_satellite_row = S.build_satellite_row
parse_metadata_value = S.parse_metadata_value
ThreadInvariantError = S.ThreadInvariantError
topological_order = S.topological_order
validate_whole_thread = S.validate_whole_thread
_ = S._

_LOCK_STALE_AFTER_SECONDS = 600


class HpcMaterializationAdapter(MaterializationAdapter):
    def validate(self, scenario) -> ValidationResult:
        from y_web.sdk.models import db
        from y_web.sdk.models import Exps

        errors = []
        threads, posts_by_thread, metadata_by_draft_post_id = _load_scenario_graph(scenario.id)

        if not threads:
            errors.append(
                {"code": "empty_scenario", "message": _("Scenario has no threads to publish.")}
            )
            return ValidationResult(errors=errors)

        exp = db.session.get(Exps, scenario.exp_id)

        _h = S.hpc_session
        hpc_database_exists = _h.hpc_database_exists
        hpc_topic_ids = _h.hpc_topic_ids
        ysimulator_available = _h.ysimulator_available

        if not ysimulator_available():
            errors.append(
                {
                    "code": "hpc_unavailable",
                    "message": _("external/YSimulator is not installed in this environment -- cannot validate against an HPC experiment's physical schema."),
                }
            )
            return ValidationResult(errors=errors)
        if not hpc_database_exists(exp):
            errors.append(
                {
                    "code": "hpc_database_not_found",
                    "message": _("Experiment %(experiment)r has no HPC database yet -- it must be started at least once before scenarios can be validated/published against it.", experiment=getattr(exp, 'idexp', scenario.exp_id)),
                }
            )
            return ValidationResult(errors=errors)

        valid_topic_ids = hpc_topic_ids(exp)
        valid_emotion_ids = hpc_emotion_ids(exp)
        _h = S.hpc_session
        hpc_user_ids = _h.hpc_user_ids

        all_user_ids = {str(uid) for uid in hpc_user_ids(exp)}

        for thread in threads:
            posts = posts_by_thread.get(thread.id, [])
            if not posts:
                errors.append(
                    {
                        "code": "empty_thread",
                        "message": _("Thread %(tmp_id)r has no posts.", tmp_id=thread.tmp_id),
                        "thread_tmp_id": thread.tmp_id,
                    }
                )
                continue

            edges = {p.tmp_id: p.parent_tmp_id for p in posts}
            try:
                validate_whole_thread(edges)
            except ThreadInvariantError as exc:
                errors.append(
                    {"code": exc.code, "message": exc.message, "thread_tmp_id": thread.tmp_id}
                )

            for post in posts:
                if not hpc_user_exists(exp, post.author_user_id):
                    errors.append(
                        {
                            "code": "unknown_author",
                            "message": _("Post %(tmp_id)r: author_user_id=%(author_user_id)r does not exist.", tmp_id=post.tmp_id, author_user_id=post.author_user_id),
                            "thread_tmp_id": thread.tmp_id,
                        }
                    )

                attribute_constraints = _generation_constraints(post) or {}
                for code, message in post_attributes.problems(attribute_constraints):
                    errors.append({
                        "code": code,
                        "message": _("Post %(tmp_id)r: %(message)s", tmp_id=post.tmp_id, message=message),
                        "thread_tmp_id": thread.tmp_id,
                    })
                likes, dislikes = post_attributes.reaction_counts(attribute_constraints)
                others = all_user_ids - {str(post.author_user_id)}
                if likes + dislikes > len(others):
                    errors.append({
                        "code": "not_enough_reactors",
                        "message": _("Post %(tmp_id)r: %(count)s reactions are requested but the experiment has only %(available)s other agents.", tmp_id=post.tmp_id, count=likes + dislikes, available=len(others)),
                        "thread_tmp_id": thread.tmp_id,
                    })

                for meta in metadata_by_draft_post_id.get(post.id, []):
                    try:
                        payload = parse_metadata_value(meta.metadata_value)
                        _table_name, kwargs = build_satellite_row(
                            meta.metadata_type,
                            payload,
                            post_id="00000000-0000-0000-0000-000000000000",
                            author_user_id=post.author_user_id,
                            parent_post_id=None,
                            round_number=None,
                            is_root=post.parent_tmp_id is None,
                        )
                    except MetadataMappingError as exc:
                        errors.append(
                            {
                                "code": exc.code,
                                "message": _("Post %(tmp_id)r, metadata %(metadata_type)r: %(message)s", tmp_id=post.tmp_id, metadata_type=meta.metadata_type, message=exc.message),
                                "thread_tmp_id": thread.tmp_id,
                            }
                        )
                        continue

                    if "topic_id" in kwargs and kwargs["topic_id"] not in valid_topic_ids:
                        errors.append(
                            {
                                "code": "unknown_topic",
                                "message": _("Post %(tmp_id)r: topic_id=%(topic_id)r does not exist.", tmp_id=post.tmp_id, topic_id=kwargs['topic_id']),
                                "thread_tmp_id": thread.tmp_id,
                            }
                        )
                    if "emotion_id" in kwargs and kwargs["emotion_id"] not in valid_emotion_ids:
                        errors.append(
                            {
                                "code": "unknown_emotion",
                                "message": _("Post %(tmp_id)r: emotion_id=%(emotion_id)r does not exist.", tmp_id=post.tmp_id, emotion_id=kwargs['emotion_id']),
                                "thread_tmp_id": thread.tmp_id,
                            }
                        )

        return ValidationResult(errors=errors)

    def preview(self, scenario) -> PreviewResult:
        threads, posts_by_thread, metadata_by_draft_post_id = _load_scenario_graph(scenario.id)
        post_count = sum(len(posts) for posts in posts_by_thread.values())
        metadata_count = sum(len(rows) for rows in metadata_by_draft_post_id.values())
        for posts in posts_by_thread.values():
            for post in posts:
                constraints = _generation_constraints(post) or {}
                metadata_count += int(bool(constraints.get("topic")))
                metadata_count += len({str(item).strip().lower() for item in constraints.get("emotions") or []})
                metadata_count += len(_hashtags_from_constraints(constraints, post.content))
                metadata_count += int(post.parent_tmp_id is not None and constraints.get("mentioned_user_id") is not None)
                metadata_count += int(bool(constraints.get("topic")) and constraints.get("opinion") not in (None, ""))
                metadata_count += post_attributes.metadata_units(constraints)
        return PreviewResult(
            post_count=post_count, metadata_count=metadata_count, thread_count=len(threads)
        )

    def publish(
        self,
        scenario,
        *,
        requested_by_user_id,
        idempotency_key=None,
        replace_thread_id=None,
        _fail_after_step=None,
    ) -> PublishResult:
        from y_web.sdk.models import db
        from y_web.sdk.models import Exps

        _m = S.models()
        PUBLICATION_STATUS_RUNNING = _m.PUBLICATION_STATUS_RUNNING
        PUBLICATION_STATUS_SUCCEEDED = _m.PUBLICATION_STATUS_SUCCEEDED
        STATUS_PUBLISHED = _m.STATUS_PUBLISHED
        ScenarioDesignIdMapping = _m.ScenarioDesignIdMapping
        ScenarioDesignPublication = _m.ScenarioDesignPublication

        def _fault(step_number):
            if _fail_after_step == step_number:
                raise RuntimeError(f"injected test failure after step {step_number}")

        if idempotency_key:
            existing = (
                db.session.query(ScenarioDesignPublication)
                .filter_by(scenario_id=scenario.id, idempotency_key=idempotency_key)
                .first()
            )
            if existing is not None and existing.status == PUBLICATION_STATUS_SUCCEEDED:
                mapping_rows = (
                    db.session.query(ScenarioDesignIdMapping)
                    .filter_by(publication_id=existing.id)
                    .all()
                )
                return PublishResult(
                    publication_id=existing.id,
                    post_count_created=existing.post_count_created or 0,
                    metadata_count_created=existing.metadata_count_created or 0,
                    id_mapping={m.tmp_id: m.real_id for m in mapping_rows},
                    idempotent_replay=True,
                )
            if existing is not None and existing.status == PUBLICATION_STATUS_RUNNING:
                raise MaterializationAdapterError(
                    "publish_in_progress",
                    _("A publication with this idempotency key is already running."),
                )

        exp = db.session.get(Exps, scenario.exp_id)
        if exp is None:
            raise MaterializationAdapterError(
                "experiment_not_found", _("Experiment not found."), http_status=404
            )
        if (exp.simulator_type or "Standard") != "HPC":
            raise MaterializationAdapterError(
                "unsupported_simulator_type",
                _("This adapter only publishes HPC experiments, got %(simulator_type)r.", simulator_type=exp.simulator_type),
            )

        _h = S.hpc_session
        hpc_database_exists = _h.hpc_database_exists
        ysimulator_available = _h.ysimulator_available

        if not ysimulator_available():
            raise MaterializationAdapterError(
                "hpc_unavailable",
                _("external/YSimulator is not installed in this environment -- cannot publish to an HPC experiment's physical schema."),
            )
        if not hpc_database_exists(exp):
            raise MaterializationAdapterError(
                "hpc_database_not_found",
                _("Experiment %(experiment)r has no HPC database yet -- it must be started at least once (even if since stopped) before scenarios can be published to it.", experiment=getattr(exp, 'idexp', scenario.exp_id)),
            )
        if exp.running:
            raise MaterializationAdapterError(
                "experiment_running", _("Cannot publish while the experiment is running.")
            )

        now = datetime.utcnow()
        if (
            scenario.lock_token
            and scenario.locked_at
            and (now - scenario.locked_at).total_seconds() < _LOCK_STALE_AFTER_SECONDS
            and scenario.locked_by != requested_by_user_id
        ):
            raise MaterializationAdapterError(
                "scenario_locked",
                _("Scenario is currently being published by user %(locked_by)r.", locked_by=scenario.locked_by),
            )

        current_fingerprint = compute_experiment_fingerprint(exp)
        if scenario.base_fingerprint and scenario.base_fingerprint != current_fingerprint:
            raise MaterializationAdapterError(
                "fingerprint_mismatch",
                _("The base experiment changed since this scenario was last opened; reload the scenario before publishing."),
            )

        validation = self.validate(scenario)
        if not validation.is_valid:
            raise MaterializationAdapterError(
                "validation_failed",
                "Scenario failed structural validation: "
                + "; ".join(e["message"] for e in validation.errors),
            )

        preview = self.preview(scenario)
        threads, posts_by_thread, metadata_by_draft_post_id = _load_scenario_graph(scenario.id)
        round_id, _day, _hour = hpc_latest_round(exp)

        try:
            with hpc_session(exp) as hsession:
                from YSimulator.YServer.classes.models import Post as HpcPost

                _m = S.models()
                IdMappingModel = _m.ScenarioDesignIdMapping
                _m = S.models()
                PublicationModel = _m.ScenarioDesignPublication
                _m = S.models()
                ScenarioDesignScenario = _m.ScenarioDesignScenario

                hpc_scenario = hsession.get(ScenarioDesignScenario, scenario.id)
                hpc_scenario.lock_token = uuid.uuid4().hex
                hpc_scenario.locked_by = requested_by_user_id
                hpc_scenario.locked_at = now

                publication = PublicationModel(
                    scenario_id=scenario.id,
                    exp_id=scenario.exp_id,
                    status=PUBLICATION_STATUS_RUNNING,
                    idempotency_key=idempotency_key,
                    requested_by_user_id=requested_by_user_id,
                    started_at=now,
                    fingerprint_at_publish=current_fingerprint,
                )
                hsession.add(publication)
                hsession.flush()  # obtain publication.id (sd_publication keeps an autoincrement int id, both families)
                # SQLAlchemy expires ORM instances when the scoped HPC
                # session commits. Keep the scalar needed by the response
                # before the context manager detaches ``publication``.
                publication_id = publication.id

                if replace_thread_id is not None:
                    self._delete_existing_thread(hsession, replace_thread_id)
                _fault(9)

                tmp_to_real: dict = {}
                post_count_created = 0
                metadata_count_created = 0

                for thread in threads:
                    posts = posts_by_thread.get(thread.id, [])
                    edges = {p.tmp_id: p.parent_tmp_id for p in posts}
                    posts_by_tmp_id = {p.tmp_id: p for p in posts}
                    order = topological_order(edges)

                    real_thread_id = None
                    for tmp_id in order:
                        draft_post = posts_by_tmp_id[tmp_id]
                        is_root = draft_post.parent_tmp_id is None
                        real_parent_id = (
                            None if is_root else tmp_to_real.get(draft_post.parent_tmp_id)
                        )

                        real_id = str(uuid.uuid4())
                        if is_root:
                            real_thread_id = real_id

                        image_id, news_id = self._materialize_link_attachment(
                            hsession=hsession, hpc_scenario=hpc_scenario, draft_post=draft_post
                        )

                        post_round = self._resolve_round(hsession, round_id, _generation_constraints(draft_post) or {})
                        post = HpcPost(
                            id=real_id,
                            tweet=draft_post.content or "",
                            round=post_round,
                            user_id=draft_post.author_user_id,
                            comment_to=-1 if is_root else real_parent_id,
                            thread_id=real_thread_id,
                            image_id=image_id,
                            news_id=news_id,
                        )
                        hsession.add(post)

                        tmp_to_real[tmp_id] = real_id
                        post_count_created += 1

                        hsession.add(
                            IdMappingModel(
                                publication_id=publication.id, tmp_id=tmp_id, real_id=real_id
                            )
                        )

                        for meta in metadata_by_draft_post_id.get(draft_post.id, []):
                            payload = parse_metadata_value(meta.metadata_value)
                            table_name, kwargs = build_satellite_row(
                                meta.metadata_type,
                                payload,
                                post_id=real_id,
                                author_user_id=draft_post.author_user_id,
                                parent_post_id=real_parent_id,
                                round_number=post_round,
                                is_root=is_root,
                                default_tid=round_id,
                            )
                            hsession.add(
                                self._build_satellite_instance(table_name, kwargs)
                            )
                            metadata_count_created += 1

                        metadata_count_created += self._materialize_generation_constraints(
                            hsession=hsession,
                            draft_post=draft_post,
                            post=post,
                            round_id=post_round,
                        )

                    _fault(13)

                _fault(17)
                if post_count_created != preview.post_count:
                    raise RuntimeError(
                        f"post count mismatch: preview={preview.post_count} "
                        f"created={post_count_created}"
                    )
                if metadata_count_created != preview.metadata_count:
                    raise RuntimeError(
                        f"metadata count mismatch: preview={preview.metadata_count} "
                        f"created={metadata_count_created}"
                    )

                publication.status = PUBLICATION_STATUS_SUCCEEDED
                publication.finished_at = datetime.utcnow()
                publication.post_count_created = post_count_created
                publication.metadata_count_created = metadata_count_created
                hpc_scenario.status = STATUS_PUBLISHED
                hpc_scenario.lock_token = None
                hpc_scenario.locked_by = None
                hpc_scenario.locked_at = None
                hpc_scenario.base_fingerprint = current_fingerprint

                hsession.commit()
        except Exception:
            raise
        finally:
            db.session.expire_all()

        return PublishResult(
            publication_id=publication_id,
            post_count_created=post_count_created,
            metadata_count_created=metadata_count_created,
            id_mapping=tmp_to_real,
        )

    @staticmethod
    def _get_or_create_sentinel_website(hsession, hpc_scenario):
        """Fase 9 follow-up, HPC counterpart of
        ``StandardMaterializationAdapter._get_or_create_sentinel_website``
        -- same "one sentinel Website row per scenario" policy (docs/
        decisions.md), same reasoning, UUID id instead of an autoincrement
        int. ``hpc_scenario`` is the same ``ScenarioDesignScenario`` row
        fetched once at the top of ``publish()`` via ``hsession.get(...)``
        -- this method never re-fetches it, it only reads/writes
        ``news_sentinel_website_id`` on the instance already in hand."""
        from YSimulator.YServer.classes.models import Website

        if hpc_scenario.news_sentinel_website_id:
            existing = hsession.get(Website, hpc_scenario.news_sentinel_website_id)
            if existing is not None:
                return existing

        website = Website(
            id=str(uuid.uuid4()),
            name=f"Scenario Design — scenario #{hpc_scenario.id}",
            rss="",
            leaning="unknown",
            category="scenario_design_link",
            last_fetched="0",
            language="unknown",
            country="unknown",
        )
        hsession.add(website)
        hsession.flush()
        hpc_scenario.news_sentinel_website_id = website.id
        return website

    @classmethod
    def _materialize_link_attachment(cls, *, hsession, hpc_scenario, draft_post):
        """HPC counterpart of
        ``StandardMaterializationAdapter._materialize_link_attachment`` --
        same contract (returns ``(image_id, news_id)``, exactly one
        non-``None`` or both ``None``), UUID ids via ``hsession`` instead
        of the Flask-SQLAlchemy ``db.session``."""
        from YSimulator.YServer.classes.models import Article, Image

        if draft_post.link_kind == "image":
            image = Image(
                id=str(uuid.uuid4()),
                url=draft_post.link_url,
                description=draft_post.link_summary or "",
                article_id=None,
            )
            hsession.add(image)
            hsession.flush()
            return image.id, None

        if draft_post.link_kind == "news":
            website = cls._get_or_create_sentinel_website(hsession, hpc_scenario)
            article = Article(
                id=str(uuid.uuid4()),
                title=draft_post.link_title or draft_post.link_url or "",
                summary=draft_post.link_summary or "",
                website_id=website.id,
                link=draft_post.link_url,
                fetched_on="0",
            )
            hsession.add(article)
            hsession.flush()
            return None, article.id

        return None, None

    @staticmethod
    def _resolve_round(hsession, default_round, constraints):
        from YSimulator.YServer.classes.models import Round

        if constraints.get("round_day") in (None, ""):
            return default_round
        day = int(constraints["round_day"])
        hour = int(constraints["round_hour"])
        row = hsession.query(Round).filter_by(day=day, hour=hour).first()
        if row is None:
            row = Round(id=str(uuid.uuid4()), day=day, hour=hour)
            hsession.add(row)
            hsession.flush()
        return row.id

    @staticmethod
    def _materialize_generation_constraints(*, hsession, draft_post, post, round_id):
        from YSimulator.YServer.classes.models import (
            Agent_Opinion, Emotion, Hashtag, Interest, Mention, PostEmotion,
            PostHashtag, PostSentiment, PostToxicity, PostTopic, Reaction, User_mgmt,
        )

        constraints = _generation_constraints(draft_post) or {}
        count = 0
        topic_id = None
        topic = (constraints.get("topic") or "").strip()
        if topic:
            topic_row = next(
                (row for row in hsession.query(Interest).all()
                 if (row.interest or "").strip().lower() == topic.lower()), None
            )
            if topic_row is None:
                topic_row = Interest(iid=str(uuid.uuid4()), interest=topic)
                hsession.add(topic_row)
                hsession.flush()
            topic_id = topic_row.iid
            hsession.add(PostTopic(id=str(uuid.uuid4()), post_id=post.id, topic_id=topic_id))
            count += 1

        emotion_names = {str(name).strip().lower() for name in constraints.get("emotions") or []}
        for emotion in hsession.query(Emotion).all():
            if (emotion.emotion or "").strip().lower() in emotion_names:
                hsession.add(PostEmotion(id=str(uuid.uuid4()), post_id=post.id, emotion_id=emotion.id))
                count += 1

        for tag in _hashtags_from_constraints(constraints, draft_post.content):
            tag_row = next(
                (row for row in hsession.query(Hashtag).all()
                 if (row.hashtag or "").strip().lower() == tag.lower()), None
            )
            if tag_row is None:
                tag_row = Hashtag(id=str(uuid.uuid4()), hashtag=tag)
                hsession.add(tag_row)
                hsession.flush()
            hsession.add(PostHashtag(id=str(uuid.uuid4()), post_id=post.id, hashtag_id=tag_row.id))
            count += 1

        mentioned_user_id = constraints.get("mentioned_user_id")
        if draft_post.parent_tmp_id is not None and mentioned_user_id is not None:
            hsession.add(Mention(
                id=str(uuid.uuid4()), user_id=str(mentioned_user_id), post_id=post.id,
                round=round_id, answered=0,
            ))
            count += 1
        if topic_id is not None and constraints.get("opinion") not in (None, ""):
            hsession.add(Agent_Opinion(
                id=str(uuid.uuid4()), agent_id=str(draft_post.author_user_id), tid=round_id,
                topic_id=topic_id,
                id_interacted_with=str(mentioned_user_id or draft_post.author_user_id),
                id_post=post.id, opinion=float(constraints["opinion"]),
            ))
            count += 1

        # Hand-set attributes (see post_attributes.py): sentiment, toxicity, likes and dislikes.
        is_root = draft_post.parent_tmp_id is None
        sentiment = post_attributes.sentiment_row(constraints)
        if sentiment is not None and topic_id is not None:
            hsession.add(PostSentiment(
                id=str(uuid.uuid4()), post_id=post.id, user_id=str(draft_post.author_user_id), round=round_id,
                topic_id=topic_id, is_post=1 if is_root else 0, is_comment=0 if is_root else 1,
                **sentiment,
            ))
            count += 1
        toxicity = post_attributes.toxicity_row(constraints)
        if toxicity is not None:
            hsession.add(PostToxicity(id=str(uuid.uuid4()), post_id=post.id, **toxicity))
            count += 1
        likes, dislikes = post_attributes.reaction_counts(constraints)
        if likes + dislikes:
            picked = post_attributes.pick_reactors(
                [row[0] for row in hsession.query(User_mgmt.id).all()],
                draft_post.author_user_id, likes, dislikes, draft_post.tmp_id,
            )
            if picked is None:
                raise MaterializationAdapterError(
                    "not_enough_reactors",
                    _("Post %(tmp_id)r: not enough other agents to give it %(count)s reactions.", tmp_id=draft_post.tmp_id, count=likes + dislikes),
                    http_status=422,
                )
            for reaction_type, user_ids in (("like", picked[0]), ("dislike", picked[1])):
                for user_id in user_ids:
                    hsession.add(Reaction(id=str(uuid.uuid4()), post_id=post.id, user_id=user_id, type=reaction_type, round=round_id))
                    count += 1
            post.reaction_count = likes + dislikes
        return count

    @staticmethod
    def _build_satellite_instance(table_name: str, kwargs: dict):
        from YSimulator.YServer.classes.models import (
            Agent_Opinion,
            PostEmotion,
            PostSentiment,
            PostToxicity,
            PostTopic,
        )

        model_by_table = {
            "post_topics": PostTopic,
            "post_emotions": PostEmotion,
            "post_sentiment": PostSentiment,
            "post_toxicity": PostToxicity,
            "agent_opinion": Agent_Opinion,
        }
        model_cls = model_by_table[table_name]
        return model_cls(id=str(uuid.uuid4()), **kwargs)

    @staticmethod
    def _delete_existing_thread(hsession, real_thread_id) -> None:
        from YSimulator.YServer.classes.models import (
            Agent_Opinion,
            Mention,
            Post,
            PostEmotion,
            PostHashtag,
            PostSentiment,
            PostToxicity,
            PostTopic,
            Reaction,
        )

        post_ids = [
            row[0]
            for row in hsession.query(Post.id).filter(Post.thread_id == real_thread_id).all()
        ]
        if not post_ids:
            return

        for model_cls, column_name in (
            (PostEmotion, "post_id"),
            (PostHashtag, "post_id"),
            (PostTopic, "post_id"),
            (PostSentiment, "post_id"),
            (PostToxicity, "post_id"),
            (Agent_Opinion, "id_post"),
            (Reaction, "post_id"),
            (Mention, "post_id"),
        ):
            column = getattr(model_cls, column_name)
            hsession.query(model_cls).filter(column.in_(post_ids)).delete(
                synchronize_session=False
            )

        hsession.query(Post).filter(Post.id.in_(post_ids)).delete(synchronize_session=False)
