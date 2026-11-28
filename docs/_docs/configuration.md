---
title: "Configuration"
subtitle: "Four files and an optional network describe a whole experiment."
goal: "Know which file holds what and start from an example."
time: "10 minutes"
---

## The files

All files live in one folder, passed with `--config`; with no `--config` the current folder is used.

| File | Read by | Holds |
|---|---|---|
| `server_config.json` | server | name, namespace, minimum clients, timeout, database, Redis, archetype transitions, logs |
| `simulation_config.json` | client | days and slots, activity, action weights, agents, churn, opinions, models, logs |
| `agent_population.json` | client | the agents and the rule that generates more |
| `llm_prompts.json` | client | prompt templates and personas |
| `network.csv` | client | initial follow edges (optional) |

Anything not written takes its default, so a file lists only what you change.

## Examples

`example/` holds ready scenarios such as `rule_population_100` (rules only, no model needed), `llm_population_100`, `llm_4clients` and `content_recsys`. Copy one into a new folder and edit.

```bash
mkdir my_config
cp example/rule_population_100/*.json my_config/
```

## The shape of `simulation_config.json`

```json
{
  "client_name": "client_1", "namespace": "social_sim",
  "simulation": { "num_days": 30, "num_slots_per_day": 24,
    "actions_likelihood": { "post": 3.0, "comment": 5.0, "read": 2.0, "share": 1.0, "search": 5.0, "follow": 0.1 } },
  "agents": { "reading_from_follower_ratio": 0.6, "churn": { "enabled": true }, "new_agents": { "enabled": true } },
  "opinion_dynamics": { "enabled": true, "model_name": "bounded_confidence", "parameters": { "epsilon": 0.25, "mu": 0.5 } }
}
```

`server_config.json` and `simulation_config.json` must agree on `namespace`. With several clients each has its own `client_name`.

## Where to next

- [Parameters]({{ site.baseurl }}/parameters/)
- [Running an experiment]({{ site.baseurl }}/running/)
