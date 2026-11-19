---
title: "How it works"
subtitle: "A server that keeps the clock, clients that keep the agents, and a barrier between them."
goal: "Follow one simulated hour from the first client request to the database."
time: "10 minutes"
---

## The two sides

The **server** (`run_server.py`) starts Ray, creates the orchestrator actor and the database middleware, and writes `ray_config.temp` so that clients find it. It owns the **clock**, the **database** (SQLite, PostgreSQL or MySQL, with an optional Redis cache), the **recommenders** and the **barrier**. A **client** (`run_client.py`) hosts a group of agents. It reads the population, decides who is active in each slot, asks the model what to write, and sends the resulting actions to the server. Nothing but the server writes to the database.

| | Server (orchestrator) | Client (worker) |
|---|---|---|
| Owns | clock, barrier, database, recommenders | agents, their schedule, model calls, memory |
| Config | `server_config.json` | `simulation_config.json`, `agent_population.json`, `llm_prompts.json`, `network.csv` |
| Count | one | one or many |

Adding clients is how a run uses more CPU cores or machines: the server stays the single writer.

## One slot

A simulated day has `num_slots_per_day` slots (24 by default, one per hour). Each slot is a *round* stored in `rounds`.

1. The client asks the server for the current slot. The server answers when every active client has reached it.
2. The client chooses the **active agents** of the slot (activity profile or hourly activity, see [Agents](../agents/)) and, for each, draws actions.
3. For a read, the client asks for **recommended posts** (`recommendations.default_limit` per call); the server computes them with the agent's content recommender.
4. The client generates text with a rule or a model, annotates it and submits the actions; the server stores rows (posts, reactions, follows, mentions, hashtags, opinions).
5. The client reports it is done; when every active client is done the slot advances.

## The barrier

{% include lab.html name="barrier" %}

The server waits for all **active** clients before it advances a slot. A client that has finished its days notifies the server and stops blocking. Every client sends a **heartbeat** every `heartbeat_interval` seconds (5 by default); one that is silent for `timeout_seconds` is dropped from the barrier, so a crashed client does not stall the others. With several clients set `min_to_start` to their number: the server begins only when that many are registered.

## Storage

Rows are keyed by **UUID** strings, which suit a distributed run. SQLite is the default and fits a single machine; PostgreSQL and MySQL are for heavier runs (initialise them with `scripts/init_db.py`). **Redis** is optional: with `redis.enabled` the recommenders read a sliding window of recent posts (`sliding_window_days`) from the cache and fall back to SQL when a mode or datum is not in Redis.

> Posts stay visible to the recommenders for `posts.visibility_rounds` slots (36 by default), a window that ageing posts leave.
{: .ys-note}

## Where to next

- [Agents and archetypes]({{ site.baseurl }}/agents/)
- [Configuration]({{ site.baseurl }}/configuration/)
