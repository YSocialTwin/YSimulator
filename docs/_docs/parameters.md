---
title: "Parameters"
subtitle: "Every setting of a run, with its meaning, its values and its default."
goal: "Find a setting, know what it does and which file holds it."
time: "reference"
tabs: false
---

A run is configured by two JSON files in the experiment folder, plus the population.

<div class="ys-cols2">
<div><h3>1 · Server</h3><p><code>server_config.json</code>: name, minimum clients, timeout, database, Redis, archetypes and logs.</p></div>
<div><h3>2 · Client</h3><p><code>simulation_config.json</code>: time, activity, action weights, agents, churn, opinions, models, memory and logs.</p></div>
<div><h3>3 · Population</h3><p><code>agent_population.json</code>: who the agents are. See <a href="{{ site.baseurl }}/agents/">Agents and archetypes</a>.</p></div>
</div>

Anything not written takes its default, so a file lists only what you change.

<div class="ys-params" data-src="{{ site.baseurl }}/assets/data/parameters.json"><noscript>Enable JavaScript to browse the parameters, or read <a href="https://github.com/YSocialTwin/YSimulator/blob/main/docs/configuration/CONFIG.md">docs/configuration/CONFIG.md</a>.</noscript></div>

## Where to next

- [Configuration]({{ site.baseurl }}/configuration/)
- [Database schema]({{ site.baseurl }}/database-schema/)
