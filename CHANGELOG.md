# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

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
