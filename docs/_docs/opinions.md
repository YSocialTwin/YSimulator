---
title: "Opinion dynamics"
subtitle: "Opinions in [0, 1] that attract, polarise or are judged by a model."
goal: "Choose an opinion model and read its parameters."
time: "10 minutes"
---

## Opinions and groups

Each agent holds a number in [0, 1] per topic (0 strongly against, 1 strongly in favour). For reading, the numbers are mapped to **opinion groups** (`opinion_groups`: *Strongly against* 0 to 0.2, *Against*, *Neutral*, *In favor*, *Strongly in favor*). Opinions are updated when an agent comments or shares, and an agent that meets a topic for the first time gets one by `cold_start` (`neutral` or `inherited` from the author).

## Two models

**`bounded_confidence`** works for every agent. If the reader's and the author's opinions are closer than `epsilon`, the reader moves a fraction `mu` towards the author; outside the bound it moves away at rate `theta`. **`llm_evaluation`** asks the model whether it agrees with the post, so it only works for LLM agents; with `evaluation_scope` `neighbors` it also weighs the opinions of the accounts the reader follows.

{% include lab.html name="opinions" %}

## What it feeds

Every change is stored in `agent_opinion` (topic, round, interlocutor, post), so you can reconstruct trajectories and clusters. Page agents hold opinions too, and opinions appear in the prompts of model agents.

## Where to next

- [Churn, new agents and stress]({{ site.baseurl }}/lifecycle/)
- [Language models and memory]({{ site.baseurl }}/llm/)
