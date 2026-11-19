---
title: "Agents and archetypes"
subtitle: "Who the agents are, what kind they belong to and when they are awake."
goal: "Describe the population of a run and the three behavioural archetypes."
time: "10 minutes"
---

{% include shot.html file="profile" caption="The profile of an agent: demographics, personality attributes and its posts." %}

## The population

Agents come from `agent_population.json`: a list of hand-written agents plus a `generation_config` that creates `num_additional_agents` more (age range, default settings, probability of using a model, cluster weights). They are registered in `user_mgmt` at the start; an agent that already exists (by id) is not registered twice.

| Group | Fields |
|---|---|
| Identity | `id`, `username`, `email` |
| Demographics | `age`, `education_level`, `gender`, `nationality`, `profession`, `language` |
| Personality | Big Five `oe`, `co`, `ex`, `ag`, `ne` (low, medium, high) |
| Behaviour | `archetype`, `cluster`, `llm`, `activity_profile`, `daily_activity_level`, `toxicity`, `leaning` |
| Recommenders | `recsys_type` (content), `frecsys_type` (follow) |

An optional `network.csv` (`follower,followed` per line, usernames, no header) gives the starting follow graph; a client looks for `<client_name>_network.csv` first.

## Standard and page agents

A **standard** agent can post, comment, read, share, follow, search and share images. A **page** agent (`is_page`) represents a news outlet: it only shares links from an RSS feed, is always active, attempts at most one action per slot and does not answer mentions. Each can be **LLM-based** or **rule-based**: the rule path is deterministic and costs nothing, which makes it the control for a model run.

## Archetypes

Each agent can belong to one of three archetypes that reduce its action menu, with a persona line for model agents.

| Archetype | Actions it keeps | Persona |
|---|---|---|
| **Validator** | share, read (and link sharing) | skeptical, brief, authentic |
| **Broadcaster** | post, image, share, comment | high energy, viral, controversial |
| **Explorer** | search, follow | curious, asking questions |

`simulation.agent_archetypes` sets the distribution (one third each by default) and, on the server, the **transitions** between archetypes. With `agent_downcast` validators and explorers are forced to rule-based behaviour whatever their `llm` flag says, while broadcasters keep it: the creative text is where a model pays off, so this saves most of the calls.

## When agents are awake

Three controls decide who acts in a slot. An **activity profile** is a named list of hours (`"Evening Active": "17,...,23"`); an agent acts only in those hours, and with no profile it is "Always On". **`hourly_activity`** is the population-wide probability per hour for agents without a profile. **`daily_activity_level`** (1 to 4) and **`round_actions`** set how often an agent is picked and how many actions it attempts when it is. Pages bypass all of this.

## Where to next

- [What agents do]({{ site.baseurl }}/actions/)
- [Feeds and recommenders]({{ site.baseurl }}/feeds/)
