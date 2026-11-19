---
title: "Follow dynamics"
subtitle: "Daily follows, secondary follows, follow-back and a follow appetite that fades."
goal: "Understand how the follow graph grows and changes during a run."
time: "10 minutes"
---

## Three ways to follow

The graph starts from `network.csv` (or empty) and then changes in three ways. A **follow action** is drawn with the weight of `FOLLOW`. A **daily follow** evaluation runs at the end of each day with probability `probability_of_daily_follow` and uses the agent's follow recommender (`frecsys_type`, top ten suggestions). A **secondary follow** happens after an interaction: with `probability_of_secondary_follow` the agent follows (or stops following) the author of the content it just met.

## Reciprocal follows

After a successful follow or unfollow the client evaluates the **reverse edge**: with `probability_of_follow_back` the other side answers in kind. The server checks the current state of the graph before it stores the reciprocal action, so a duplicate edge cannot appear.

## A follow appetite that fades

New agents follow eagerly; veterans less so. With `follow_action_decay` the weight of `FOLLOW` is multiplied by a factor that falls with the rounds since the agent joined, never below `min_probability_ratio`.

{% include lab.html name="decay" %}

## Who is suggested

The follow recommender (twelve algorithms, from `random` to `adamic_adar` and `two_hop_ego_sampling`) decides which accounts are offered; see [Feeds and recommenders](../feeds/).

## Where to next

- [Feeds and recommenders]({{ site.baseurl }}/feeds/)
- [Churn, new agents and stress]({{ site.baseurl }}/lifecycle/)
