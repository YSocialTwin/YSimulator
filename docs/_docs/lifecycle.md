---
title: "Churn, new agents and stress"
subtitle: "Agents that leave, agents that arrive, and the stress that can push them out."
goal: "Model a population that changes, with or without stress."
time: "10 minutes"
---

## Churn and newcomers

With `agents.churn.enabled`, a daily check runs with probability `churn_probability`; agents inactive for `inactivity_threshold` rounds become candidates and `churn_percentage` of them leave (their `left_on` is set). With `agents.new_agents.enabled`, newcomers arrive with probability `probability_new_agents`, as a share `percentage_new_agents` of the population. The two can run together to keep the size stable or to model growth.

{% include lab.html name="churn" %}

## Stress and reward

`stress_reward` keeps two variables per agent that move with what happens to it: a reaction, comment or share aimed at it, or a moderation event, applies a delta to stress and reward. Before it acts, an agent reads the aggregate state over the last `backward_rounds`. With `stress_reward.system.churn.enabled`, stress can push an agent off the platform. Rounds are UUIDs, so the server windows them by their real (day, hour), not by id order.

## Where to next

- [Language models and memory]({{ site.baseurl }}/llm/)
- [Configuration]({{ site.baseurl }}/configuration/)
