# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- `ysocial_platform/` integrates microblogging with YSocial as a platform (provider, feed/hashtag/interest/emotion/friends/thread/profile pages, publishing action, templates and static files moved from YSocial; `meta/registry.json`)

### Fixed
- LLM endpoints that need an API key (OpenAI, DeepSeek, authenticated Ollama): the standard `LLMService` kept only the native Ollama protocol over plain `http` and ignored `llm_api_key`. `llm_utils/chat_model.py` now keeps the scheme and path of `address`, sends the key as a bearer token and speaks the OpenAI-compatible protocol (`langchain-openai`) to hosted providers (`llm.api_format`: `auto`, `openai`, `ollama`); the batch probes send the key too and skip Ollama's API on OpenAI-style endpoints.

### Added
- Federation topic migration (opt-in, `federation.create_topics`, default on in the runtime): topics carried by a cross-post are matched ignoring case with the platform's interests, missing ones are created (`federation_topic` records name, tick and source platform) and attached to the post; idempotent per message.
- Cross-post as an agent action (opt-in, `federation.crosspost_mode: agent_action`): the client draws once per platform where the agent is also active (`get_federation_destinations`) with `crosspost_propensity` and sets `crosspost_to` ([{member, text}]) on the POST action, with the model's version of the text (prompts `crosspost_adapt_<platform>`, EN and IT; `LLMService.adapt_crosspost`) or the rule text; the server adapter sends one `crosspost.v1` per chosen destination instead of `content.v1`. Default mode unchanged.
- Federation local churn (F4.5, opt-in): `churned_agents(day)` gives the accounts whose `left_on` round is in the days up to the given one and that the federation still sees as active, so the coordinator records them as left with reason churn.
- Federation exposures (F4.4b, opt-in `federation.exposures`): with `federation.exposures` the adapter also hands `exposure.v1` to the bus: recommended posts that are materialised cross-posts are views (approximate), reactions, comments and shares are interactions (exact); tie from the follow table; table `federation_exposure_log`, fixed per tick.
- Federation attention (opt-in): `apply_attention` stores the multiplier of the day per account (table `federation_attention`); `get_federation_attention` serves it and the client scales the actions of each agent in the slot; with the federation off or multiplier 1 nothing changes.
- Federation affective report (opt-in): `affective_report(day)` of the adapter gives the native stress/reward of the active accounts at the end of the day, read from the runtime's own tables without writing.
- Federation bus and membership (opt-in): tables `federation_membership`, `federation_ref`, `federation_export`, `federation_state` (own metadata, created only with the federation on); `export_outbox` (posts the agents marked with the `crosspost` attribute of the POST action, or every root post of the round with `federation.export_policy = "all"`), `ingest_inbox` (cross-posts become posts of the author with the topics already known, once per message), `apply_membership`; accounts that are not active are left out of `get_recommended_posts`, `get_follow_suggestions` and `search_posts_by_topic`, and `get_federation_inactive_agents` tells the clients, whose scheduler does not let them act (`YClient/federation.py`; `federation.crosspost_propensity` makes an agent mark a post for cross-post). `federation.accounts` maps global agent ids to local ids (default: the same).
- `simulation.barrier_poll_seconds` (client config, default 1.0): sleep between polls while the server answers WAIT; the default keeps standalone behaviour, federated runs can lower it.
- Federation (opt-in): `YSimulator/YServer/federation/` (adapter, gate wrapper) and a clock gate in `_check_barrier_and_advance`, retried from `get_instruction` while the coordinator holds the round back; enabled by the `federation` section of the server configuration, otherwise standalone behaviour is unchanged.

## [2.1.0] - 2026-10-20

### Added
- Topic sampling weighted by frequency in the moving window (only topics with count > 0); exactly one topic per generated post.
- Hashtags in canonical form: no leading `#`, apostrophes and accents kept, case-insensitive identity.
- Prompts i18n: prompts moved out of the code into `prompts_internal.json`, read through `prompt_store` with language support.
- Prompts i18n: protocol tokens and tolerant parsers (no `eval`); Italian internal prompt pack.
- Prompts i18n: localized follow action and reciprocal-follow verb; persona fragments moved into the packs.
- Prompts i18n: `run_client` activates the prompt language (Ray workers too) and persona values are localized.
- Memory M5: the memory engine renders its texts in the simulation prompt language.
- Memory M2: the log shows which `yclient_memory` is loaded (path, version, language); errors name the Agent Memory plugin and warn when the package ignores the language.
- `NEWS` defined in `protocol_tokens` as a legacy alias of `SHARE_LINK`.

### Changed
- Dependencies aligned with YWeb (SQLAlchemy >= 2.0, langchain >= 0.3).
- Shorter, purpose-oriented plugin description in `meta/info.json`.
- License: GPL-3.0-only (`LICENSE` added, `meta/info.json`, README).
- README restructured on the common layout; citation updated to the published YSocial reference (Big Data & Society, 2026).
- Code style: imports sorted with isort, schema migration code formatted with black 24.

### Fixed
- The microblogging post prompt no longer mentions the simulation day and slot.
- Tests independent of `gpu_utils` and of the optional Perspective and VADER packages; tests use the real Ray instead of a `MagicMock`; stale tests aligned with the hardened vLLM/batch code paths.
- flake8 failures: misplaced vLLM init tail, misplaced test body, unused globals.

[Unreleased]: https://github.com/YSocialTwin/YSimulator/compare/v2.1.0...HEAD
[2.1.0]: https://github.com/YSocialTwin/YSimulator/releases/tag/v2.1.0
