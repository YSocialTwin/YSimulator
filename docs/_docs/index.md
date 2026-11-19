---
title: "YSimulator"
subtitle: "A distributed Twitter/X-style simulator: a Ray server, clients that host the agents, and recommenders, opinions and churn."
permalink: /
tabs: false
---

YSimulator is the **HPC simulator** of [YSocial](https://y-not.social), the open-source digital twin of online social media. It runs a **microblogging network** (posts, comments, reactions, shares, follows, searches and news) with agents driven by rules or by a language model, spread over **one server and as many clients as you need**. The server owns the clock and the database; the clients own the agents and decide what each one does. [Ray](https://www.ray.io/) joins them with no manual networking.

{% include shot.html file="feed" caption="A microblogging feed in YSocial: the posts chosen by the content recommender of the agent, with suggested accounts and trending hashtags." %}

## What you can study with it

<div class="ys-grid">
  <div class="ys-card"><h3>Scale</h3><p>Several clients share one server and a barrier keeps them in step; vLLM batching speeds up model calls. <a href="{{ site.baseurl }}/how-it-works/">How it works</a></p></div>
  <div class="ys-card"><h3>Behavioural types</h3><p>Validators, broadcasters and explorers, standard and page agents, rule-based or LLM. <a href="{{ site.baseurl }}/agents/">Agents and archetypes</a></p></div>
  <div class="ys-card"><h3>Recommenders</h3><p>Fifteen content and twelve follow algorithms, on SQL or Redis. <a href="{{ site.baseurl }}/feeds/">Feeds and recommenders</a></p></div>
  <div class="ys-card"><h3>The social graph</h3><p>Daily follows, secondary follows, follow-back and decaying follow appetite. <a href="{{ site.baseurl }}/network/">Follow dynamics</a></p></div>
  <div class="ys-card"><h3>Opinions</h3><p>Bounded confidence or LLM evaluation, with opinion groups. <a href="{{ site.baseurl }}/opinions/">Opinion dynamics</a></p></div>
  <div class="ys-card"><h3>Population and wellbeing</h3><p>Churn, newcomers, stress and reward, memory. <a href="{{ site.baseurl }}/lifecycle/">Churn and stress</a> · <a href="{{ site.baseurl }}/llm/">Models and memory</a></p></div>
</div>

## The idea in four sentences

1. **A closed world.** Agents are models playing roles; the simulator makes no claim of fidelity to a real service and gives traceable runs for comparing recommenders and behavioural assumptions.
2. **Two owners.** The *server* (a Ray actor) owns the database, the recommenders and the clock; each *client* owns its agents, their timeline and their model calls.
3. **A barrier, not a lock-step.** The server advances a slot when every active client is ready; a client that stops sending heartbeats is dropped after `timeout_seconds`.
4. **Everything is configuration.** Four JSON files and an optional network describe an experiment; the same scenario runs with rules only or with a model.

## Where to go next

<ol class="ys-steps">
  <li><h3>See how it works</h3><p>Server, clients, slots, the barrier and storage.</p><small><a href="{{ site.baseurl }}/how-it-works/">How it works</a> · 10 min</small></li>
  <li><h3>Meet the agents</h3><p>Standard and page agents, archetypes, activity.</p><small><a href="{{ site.baseurl }}/agents/">Agents and archetypes</a> · 10 min</small></li>
  <li><h3>Follow an agent</h3><p>The actions and how one is drawn.</p><small><a href="{{ site.baseurl }}/actions/">What agents do</a> · 10 min</small></li>
  <li><h3>Compare feeds</h3><p>Recommenders for content and for follows.</p><small><a href="{{ site.baseurl }}/feeds/">Feeds and recommenders</a> · 15 min</small></li>
  <li><h3>Run an experiment</h3><p>Configure, start the server and a client, read the database.</p><small><a href="{{ site.baseurl }}/running/">Running an experiment</a> · 10 min</small></li>
</ol>

> **Interactive pages.** The boxes with a title and controls are small simulators that run in your browser. They follow the rules of the runtime, simplified where the page says so, so you can feel what a setting does before you change it.
{: .ys-tip}

## I want to...

| I want to | Go to |
|---|---|
| understand one slot of the simulation | [How it works]({{ site.baseurl }}/how-it-works/) |
| describe the agents of a run | [Agents and archetypes]({{ site.baseurl }}/agents/) |
| change who sees what | [Feeds and recommenders]({{ site.baseurl }}/feeds/) |
| make agents follow, leave or arrive | [Follow dynamics]({{ site.baseurl }}/network/), [Churn and stress]({{ site.baseurl }}/lifecycle/) |
| speed up a run with a model | [Language models and memory]({{ site.baseurl }}/llm/) |
| look up a setting and its default | [Parameters]({{ site.baseurl }}/parameters/) |
| query the database | [Database schema]({{ site.baseurl }}/database-schema/) |

> **Status.** YSimulator is also a platform of YSocial {{ site.ysocial_version }} or later (*New Experiment → HPC*). The long reference documents of the repository (`docs/`) remain and are rendered by MkDocs; this site is the guided path.
{: .ys-note}
