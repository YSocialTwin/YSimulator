# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

Changes made since the last published state of `main`, newest first:

- Topic sampling: weight = count, only topics with count > 0 in the moving window
- Topic sampling: weight = count + 1 over the moving window
- Hashtags: canonical form without '#', apostrophes and accents kept in the tag, case-insensitive identity
- Microblogging post prompt no longer mentions simulation day and slot
- protocol_tokens: define NEWS (legacy alias of SHARE_LINK read by the forum client)
- M2: log which yclient_memory is loaded (path, version, language)
- M2: memory errors name the Agent Memory plugin; warn when the package ignores the language
- M5: memory engine renders its texts in the simulation prompt language
- Prompts i18n step 5: localize the follow action and the reciprocal-follow verb
- Prompts i18n step 5: move the remaining English persona fragments into the packs
- Prompts i18n step 5: run_client activates the prompt language (Ray workers too); persona values localized
- Prompts i18n step 4: Italian internal prompt pack
- Prompts i18n step 3: prompt_store language support
- Prompts i18n step 2: reactions read as whole words
- Prompts i18n step 2: tolerant opinion parsing, protocol tokens
- Prompts i18n step 1: move in-code prompts to prompts_internal.json
- i18n: shorter, purpose-oriented plugin descriptions
- Make gpu_utils, Perspective and VADER tests independent of optional dependencies
- Align stale tests with the hardened vLLM/batch code paths
- Format the Ray guard in the test modules with black
- Tests: stop replacing the real Ray with a MagicMock at import time
- Sort imports with isort (CI check)
- Format schema migration code with black 24
- Fix flake8 failures: misplaced vLLM init tail, misplaced test body, unused globals
- Align requirements with the library versions shipped by YWeb
- update .gitignore
- deps: bump SQLAlchemy>=2.0, langchain>=0.3
