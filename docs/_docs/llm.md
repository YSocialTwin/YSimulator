---
title: "Language models and memory"
subtitle: "Ollama or vLLM, batching, a vision model, annotations and agent memory."
goal: "Pick a model backend and know what each optional layer costs."
time: "10 minutes"
---

## The backends

`llm` configures the text model and `llm_v` an optional vision model (without it image actions are skipped). `llm.backend` is `ollama` (the remote path; it can upgrade to a batched adapter) or `vllm` (an embedded local engine). For a remote backend `api_format` is `auto`, `openai` or `ollama`, and `batching_policy` is `auto` (probe and batch if possible), `off` or `force` (fail at start if batching does not work).

## Batching

With a batch-capable backend the client groups the calls of a slot instead of making them one by one: posts, comments, replies, shares, read reactions, searches, emotion extraction and opinion evaluation. The repository reports speed-ups of one to two orders of magnitude on the vLLM path, depending on the workload; the Ollama path is unchanged.

## Annotations

Text can be annotated for hashtags, mentions, sentiment (VADER), toxicity and emotions (`simulation.emotion_annotation`, a model call per text). They fill `post_hashtags`, `mentions`, `post_sentiment`, `post_toxicity`, `emotions` and `post_emotions`.

## Memory

With `agents.memory_enabled` each LLM agent keeps run-scoped memory: events, thread cards, social cards (affinity, conflict, humour, trust), reflections and a community digest, retrieved by semantic search (`memory_embedding_model`, default `embeddinggemma`) and injected into prompts for posts, replies, shares and browsing. It lives entirely in the client: the server never calls the memory or the embedding model. Rule-based agents have none.

> Memory and emotion annotation add model calls and longer prompts; for a first experiment turn them off and compare.
{: .ys-tip}

## Where to next

- [Configuration]({{ site.baseurl }}/configuration/)
- [Running an experiment]({{ site.baseurl }}/running/)
