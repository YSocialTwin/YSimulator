#!/usr/bin/env python3
"""Write docs/assets/data/schema.json (the data of the page "Database schema") from the models of the runtime.

``python scripts/make_schema_data.py``           rewrite the file
``python scripts/make_schema_data.py --check``   exit 1 when the file is not up to date

Tables, columns, types, keys, foreign keys and constraints are read from the SQLAlchemy models, so they cannot drift.
The descriptions are in this file: ``NOTES`` for tables, ``COLUMNS`` (by name, for every table) and ``TABLE_COLUMNS``
(one table only).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import CheckConstraint, UniqueConstraint

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from YSimulator.YServer.classes import models  # noqa: E402

OUTPUT = ROOT / "docs" / "assets" / "data" / "schema.json"

GROUPS = [('run', 'The run and its clock', 'La run e il suo orologio', ['rounds']),
 ('people', 'Accounts and the follow graph', 'Account e grafo dei follow', ['user_mgmt', 'follow', 'agent_custom_features']),
 ('content', 'Posts, comments and media', 'Post, commenti e media', ['post', 'mentions', 'images']),
 ('reactions', 'Reactions', 'Reazioni', ['reactions', 'voting']),
 ('feeds',
  'Feeds, hashtags and topics',
  'Feed, hashtag e argomenti',
  ['recommendations', 'hashtags', 'post_hashtags', 'post_topics', 'interests', 'user_interest']),
 ('news', 'News', 'Notizie', ['websites', 'articles', 'article_topics']),
 ('annotations', 'Annotations', 'Annotazioni', ['emotions', 'post_emotions', 'post_sentiment', 'post_toxicity']),
 ('moderation', 'Reports and messages', 'Segnalazioni e messaggi', ['reported', 'sys_messages']),
 ('opinions', 'Opinions', 'Opinioni', ['agent_opinion']),
 ('behaviour', 'Stress and reward', 'Stress e ricompensa', ['stress_reward']),
 ('memory',
  'Agent memory',
  'Memoria degli agenti',
  ['memory_interaction_events', 'memory_social_cards', 'memory_thread_cards', 'memory_community_digests', 'memory_items'])]

#: page of the site that explains the table (id of a file in _docs/)
DOCS = {'rounds': 'how-it-works',
 'user_mgmt': 'agents',
 'follow': 'network',
 'agent_custom_features': 'agents',
 'post': 'actions',
 'mentions': 'actions',
 'images': 'actions',
 'reactions': 'actions',
 'recommendations': 'feeds',
 'hashtags': 'actions',
 'post_hashtags': 'actions',
 'post_topics': 'actions',
 'interests': 'agents',
 'user_interest': 'agents',
 'websites': 'actions',
 'articles': 'actions',
 'article_topics': 'actions',
 'emotions': 'llm',
 'post_emotions': 'llm',
 'post_sentiment': 'llm',
 'post_toxicity': 'llm',
 'reported': 'actions',
 'sys_messages': 'actions',
 'agent_opinion': 'opinions',
 'stress_reward': 'lifecycle',
 'memory_interaction_events': 'llm',
 'memory_social_cards': 'llm',
 'memory_thread_cards': 'llm',
 'memory_community_digests': 'llm',
 'memory_items': 'llm',
 'voting': 'actions'}

PAGES = {'how-it-works': ('How it works', 'Come funziona'),
 'agents': ('Agents and archetypes', 'Agenti e archetipi'),
 'actions': ('What agents do', 'Che cosa fanno gli agenti'),
 'network': ('Follow dynamics', 'Dinamica dei follow'),
 'feeds': ('Feeds and recommenders', 'Feed e raccomandatori'),
 'opinions': ('Opinion dynamics', 'Dinamica delle opinioni'),
 'lifecycle': ('Churn, new agents and stress', 'Abbandono, nuovi agenti e stress'),
 'llm': ('Language models and memory', 'Modelli linguistici e memoria')}

NOTES = {
    "rounds": "The time axis: one row per round (a simulated hour), with day and hour; every `round` column points here.",
    "user_mgmt": "One row per account (agent, page or human): persona, Big Five traits, archetype, recommenders, activity settings, joined and left rounds.",
    "follow": "Every follow and unfollow as an event: one row per pair and action, with the round of the change.",
    "post": "Every post and every comment (a comment has `comment_to`): text, author, thread, round, the news or image it shares, reaction counter and moderation flags.",
    "reactions": "The reaction of an account to a post (like, love, laugh, angry, sad), one row each.",
    "recommendations": "The list of posts the recommender offered to an account in a round.",
    "hashtags": "Distinct hashtags of the run.",
    "post_hashtags": "Links a post to its hashtags.",
    "mentions": "Accounts mentioned in a post, with the round and whether the mention was answered.",
    "emotions": "Catalogue of the emotion labels (28 of the GoEmotions taxonomy in the forum).",
    "post_emotions": "Emotions attached to a post by the annotation.",
    "post_sentiment": "Sentiment (VADER: negative, neutral, positive, compound) of posts, comments and reactions.",
    "post_toxicity": "Toxicity scores of a post (Perspective API or the local model).",
    "post_topics": "Topic of a post.",
    "interests": "Catalogue of interests and topics.",
    "user_interest": "Interests of an account, with the round in which they were recorded.",
    "agent_opinion": "Opinion of an agent on a topic in a round, with the interlocutor and the post that caused the change.",
    "agent_custom_features": "Free key-value features attached to an agent.",
    "stress_reward": "Variations of stress and reward of each account, with the event that caused them and the round.",
    "websites": "News sources (RSS feeds) the platform reads from.",
    "articles": "News articles fetched from the websites.",
    "article_topics": "Topics assigned to an article.",
    "images": "Images (with their description from the vision model) attached to posts.",
    "image_posts": "Images fetched from image feeds, shareable as posts.",
    "reported": "Reports filed by an account against another account or a post.",
    "sys_messages": "System messages to an account (for example a moderation notice), with their duration.",
    "voting": "Votes of an account on a content item.",
    "simulation_client": "The clients registered with the server: status, last heartbeat and last round submitted (the barrier reads it).",
    "memory_interaction_events": "Events recorded for the agent memory: what the agent did or saw, with importance and tone (only with memory on).",
    "memory_social_cards": "Running summary of the relation between two agents: affinity, conflict, humour and trust (only with memory on).",
    "memory_thread_cards": "Running summary of a thread for an agent: gist, its role, main participants (only with memory on).",
    "memory_community_digests": "Periodic digest of the community: top topics, norms, memes, polarising issues (only with memory on).",
    "memory_items": "Searchable memory items (events, reflections, cards) with their embeddings (only with memory on).",
}

COLUMNS = {
    "id": "Primary key.", "iid": "Primary key.", "vid": "Primary key.", "user_id": "Account concerned (user_mgmt.id).", "uid": "Account concerned (user_mgmt.id).",
    "agent_id": "Agent concerned (user_mgmt.id).", "post_id": "Post concerned (post.id).", "round": "Round in which it happened (rounds.id).",
    "round_id": "Round concerned (rounds.id).", "tid": "Round concerned (rounds.id).", "seq": "Insertion order assigned by the server; sort by this, not by the id.",
    "follower_id": "Account that follows (user_mgmt.id).", "emotion_id": "Emotion (emotions.id).", "topic_id": "Topic (interests.iid).",
    "hashtag_id": "Hashtag (hashtags.id).", "interest_id": "Interest (interests.iid).", "article_id": "News article (articles.id).",
    "website_id": "News source (websites.id).", "run_id": "Run the memory belongs to.", "created_at": "When the row was written.",
    "updated_at": "When the row was last updated.", "type": "Kind of the item.", "language": "Language.",
    "link": "Address of the item.", "title": "Title.", "summary": "Summary.", "description": "Description.", "url": "Address of the image.",
}

TABLE_COLUMNS = {
    "rounds": {"day": "Simulated day.", "hour": "Hour of the day (0-23)."},
    "user_mgmt": {"username": "Unique name.", "email": "Address of the account.", "password": "Password of a human account (hashed).", "user_type": "Kind of model that drives the agent.", "leaning": "Political leaning.", "age": "Age.",
                  "oe": "Big Five: openness.", "co": "Big Five: conscientiousness.", "ex": "Big Five: extraversion.", "ag": "Big Five: agreeableness.", "ne": "Big Five: neuroticism.",
                  "recsys_type": "Content recommender of the agent.", "frecsys_type": "Follow recommender of the agent.", "owner": "Experiment owner.", "education_level": "Education level.", "joined_on": "Round of arrival.", "left_on": "Round of departure; empty while active.",
                  "gender": "Gender.", "nationality": "Nationality.", "round_actions": "Actions per slot.", "toxicity": "Toxicity level of the persona.", "is_page": "1 for a page agent (news publisher).", "daily_activity_level": "Daily activity level.", "profession": "Profession.",
                  "activity_profile": "Named activity profile.", "archetype": "Archetype (validator, broadcaster, explorer).", "cover_image": "Cover image.", "last_active_day": "Last day the account acted."},
    "follow": {"user_id": "Account that is followed.", "follower_id": "Account that follows.", "action": "follow or unfollow (the last action of the pair).", "round": "Round of the action."},
    "post": {"tweet": "Text of the post or comment.", "post_img": "Image of the post.", "user_id": "Author.", "comment_to": "Post a comment answers; -1 for a post.", "thread_id": "Thread the item belongs to.", "news_id": "News article it shares.",
             "shared_from": "Post it re-shares.", "image_id": "Image attached.", "image_post_id": "Image-feed item attached.", "dedupe_key": "Key that makes a retry idempotent.", "client_action_id": "Client-side id of the action.",
             "reaction_count": "Reactions received.", "moderated": "1 if moderated.", "is_moderation_comment": "1 if the comment is a moderation notice."},
    "reactions": {"type": "Kind of reaction (like, love, laugh, angry, sad).", "post_id": "Post reacted to."},
    "recommendations": {"post_ids": "Posts offered, in order."},
    "hashtags": {"hashtag": "The hashtag."}, "emotions": {"emotion": "Name.", "icon": "Icon."},
    "mentions": {"post_id": "Post containing the mention.", "answered": "1 once the mentioned account answered."},
    "interests": {"interest": "Name."},
    "post_sentiment": {"neg": "Negative.", "neu": "Neutral.", "pos": "Positive.", "compound": "Compound score.", "sentiment_parent": "Sentiment of the parent.", "is_post": "1 for a post.", "is_comment": "1 for a comment.", "is_reaction": "1 for a reaction."},
    "post_toxicity": {"toxicity": "Toxicity.", "severe_toxicity": "Severe toxicity.", "identity_attack": "Identity attack.", "insult": "Insult.", "profanity": "Profanity.", "threat": "Threat.", "sexually_explicit": "Sexually explicit.", "flirtation": "Flirtation."},
    "agent_opinion": {"opinion": "Opinion in [0, 1].", "stubborn": "1 if the agent does not change its mind.", "id_interacted_with": "Account whose content changed the opinion.", "id_post": "Post that caused the change."},
    "agent_custom_features": {"feature_type": "Kind of feature.", "key": "Name.", "value": "Value."},
    "stress_reward": {"variable": "stress or reward.", "value": "Variation.", "type": "Kind of event.", "action": "Event that caused it."},
    "websites": {"name": "Name.", "rss": "Feed address.", "leaning": "Political leaning.", "category": "Category.", "last_fetched": "Last fetch.", "country": "Country.", "fetch_images_from_url": "Fetch images from the page.", "fetch_images_timeout": "Timeout of the image fetch."},
    "articles": {"fetched_on": "Round of the fetch."},
    "images": {"remote_article_id": "Article id on the remote platform."},
    "image_posts": {"source_url": "Original address.", "subreddit": "Community it came from.", "used": "1 once shared.", "local_path": "Local copy.", "high_res_url": "High-resolution address."},
    "reported": {"type": "Kind of report.", "to_uid": "Account reported.", "to_post": "Post reported.", "from_uid": "Account that reported."},
    "sys_messages": {"type": "Kind of message.", "to_uid": "Receiver.", "message": "Text.", "from_round": "Round it starts.", "duration": "Rounds it lasts."},
    "voting": {"preference": "Vote.", "content_type": "Kind of content.", "content_id": "Content voted."},
    "simulation_client": {"client_id": "Name of the client.", "status": "State of the client.", "last_heartbeat": "Last heartbeat received.", "submitted_round_id": "Last round whose actions it submitted."},
    "memory_interaction_events": {"actor_user_id": "Who acted.", "target_user_id": "Who was addressed.", "thread_root_id": "Thread concerned.", "target_post_id": "Post addressed.", "actor_post_id": "Post of the actor.", "event_type": "Kind of event.", "relation_label": "Relationship label.", "tone_label": "Tone.", "topics_json": "Topics (JSON).", "salient_claim": "Main claim.", "event_text": "Text of the event.", "weight": "Weight.", "importance": "Importance.", "last_accessed_round": "Last round read.", "access_count": "Times read."},
    "memory_social_cards": {"agent_user_id": "Owner of the card.", "other_user_id": "Other agent.", "affinity": "Affinity.", "conflict": "Conflict.", "humor": "Humour.", "trust": "Trust.", "last_relation_label": "Last label.", "last_thread_root_id": "Last thread.", "last_updated_round": "Last update.", "event_count": "Events summarised.", "summary_text": "Summary.", "evidence_tail_json": "Latest evidence (JSON)."},
    "memory_thread_cards": {"agent_user_id": "Owner of the card.", "thread_root_id": "Thread.", "gist_text": "Gist.", "my_role": "Role of the agent in the thread.", "participants_top_json": "Main participants (JSON).", "entry_points_json": "Entry points (JSON).", "last_seen_round_id": "Last round seen."},
    "memory_community_digests": {"digest_text": "Digest.", "top_topics_json": "Top topics (JSON).", "norms_json": "Norms (JSON).", "memes_json": "Memes (JSON).", "polarizing_issues_json": "Polarising issues (JSON)."},
    "memory_items": {"agent_user_id": "Owner.", "item_type": "Kind of item.", "text": "Text.", "metadata_json": "Metadata (JSON).", "source_event_id": "Event it comes from.", "thread_root_id": "Thread.", "other_user_id": "Other agent.", "topic_tags_json": "Topic tags (JSON).", "importance": "Importance.", "recency_anchor_round": "Round used for recency.", "last_accessed_round": "Last round read.", "access_count": "Times read.", "embedding_json": "Embedding (JSON).", "embedding_model": "Embedding model.", "embedding_dim": "Embedding size.", "embedding_status": "State of the embedding."},
}


def rules(table) -> list:
    out = []
    for c in table.constraints:
        if isinstance(c, CheckConstraint):
            out.append(f"check {c.name}: {c.sqltext}")
        elif isinstance(c, UniqueConstraint):
            out.append(f"unique {c.name}: ({', '.join(col.name for col in c.columns)})")
    for idx in sorted(table.indexes, key=lambda i: i.name or ""):
        if idx.unique:
            out.append(f"unique index {idx.name}: ({', '.join(c.name for c in idx.columns)})")
    return sorted(out)


def build() -> dict:
    tables = {}
    for name, t in sorted(models.Base.metadata.tables.items()):
        cols = []
        for col in t.columns:
            fks = sorted(f.target_fullname for f in col.foreign_keys)
            default = None
            if col.default is not None and getattr(col.default, "arg", None) is not None and not callable(col.default.arg):
                default = str(col.default.arg)
            desc = TABLE_COLUMNS.get(name, {}).get(col.name) or COLUMNS.get(col.name, "")
            cols.append({"name": col.name, "type": str(col.type), "pk": bool(col.primary_key), "null": bool(col.nullable) and not col.primary_key,
                         "default": default, "fk": fks[0] if fks else None, "desc": desc})
        tables[name] = {"note": NOTES.get(name, ""), "doc": DOCS.get(name), "columns": cols, "rules": rules(t)}
    placed = {t for _, _, _, ts in GROUPS for t in ts}
    groups = [{"id": g, "title": en, "title_it": it, "tables": [t for t in ts if t in tables]} for g, en, it, ts in GROUPS]
    rest = [t for t in tables if t not in placed]
    if rest:
        groups[-1]["tables"] += rest
    docs = {k: {"en": v[0], "it": v[1]} for k, v in PAGES.items()}
    return {"schema_version": None, "groups": groups, "docs": docs, "tables": tables}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = json.dumps(build(), indent=1, ensure_ascii=False) + "\n"
    if args.check:
        return 0 if OUTPUT.is_file() and OUTPUT.read_text(encoding="utf-8") == text else 1
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
