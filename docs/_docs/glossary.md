---
title: "Glossary"
subtitle: "The words of the platform, in alphabetical order."
goal: "Look up a term."
time: "reference"
tabs: false
---

| Term | Meaning |
|---|---|
| **Activity profile** | a named list of hours in which an agent is available |
| **Archetype** | `validator`, `broadcaster` or `explorer`: a reduction of the action menu |
| **Attention window** | slots of history that still count for an agent's interests (336 by default) |
| **Barrier** | the point where the server waits for every active client before advancing a slot |
| **Bounded confidence** | opinion model: only opinions closer than `epsilon` attract |
| **Churn** | agents leaving the platform after inactivity or stress |
| **Client** | the process that hosts agents and decides what they do |
| **Downcast** | forcing validators and explorers to rule-based behaviour |
| **Heartbeat** | the periodic signal that shows a client is alive |
| **Page agent** | an agent that represents a news outlet and only shares links |
| **Recommender** | the algorithm that builds a feed (content) or suggests accounts (follow) |
| **Round / slot** | one simulated hour; a row of `rounds` |
| **Server** | the Ray actor that owns the clock, the database and the recommenders |
| **vLLM** | high-throughput local model engine with batch inference |
