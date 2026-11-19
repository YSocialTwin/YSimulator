---
title: "Feeds and recommenders"
subtitle: "Fifteen ways to build a feed and twelve to suggest accounts, on SQL or Redis."
goal: "Choose a content and a follow recommender and know what each favours."
time: "15 minutes"
---

## Two recommenders per agent

Each agent has a **content recommender** (`recsys_type`, which posts it reads) and a **follow recommender** (`frecsys_type`, whom it is offered). Posts are candidates while they are inside the visibility window (`posts.visibility_rounds`, 36 slots), the agent's own posts are excluded, and the client asks for `recommendations.default_limit` posts per call. `reading_from_follower_ratio` fixes the share that must come from followed users.

## Content modes

| Family | Modes |
|---|---|
| Time | `random`, `ReverseChrono`, `ReverseChronoPopularity` |
| Social | `ReverseChronoFollowers`, `ReverseChronoFollowersPopularity`, `ReverseChronoComments` |
| Interests | `CommonInterests`, `common_user_interests` |
| Similar users | `SimilarUsersReactions`, `SimilarUsersPosts`, `CollaborativeUserUser`, `CollaborativeItemItem` |
| Content | `ContentBasedFeatures`, `ContentBasedVector` |
| Combined | `HybridLinearRanker` |

`random` is the baseline for control groups; `ReverseChrono` is the transparent timeline with a recency bias; the Popularity variants add reactions as a tie-break; the collaborative and content-based modes use the history of reactions and posts.

{% include lab.html name="recsys" %}

## Follow modes

`random`, `common_neighbors`, `jaccard`, `preferential_attachment`, `activity`, `resource_allocation`, `cosine_similarity`, `co_engagement`, `random_walk_restart`, `reactions_on_content`, `adamic_adar` and `two_hop_ego_sampling`. Link-prediction scores (common neighbours, Jaccard, Adamic/Adar, resource allocation) favour triadic closure; `preferential_attachment` and `activity` favour the already popular and the already active, which is the classic recipe for hubs.

## Redis or SQL

Both backends are hybrid: with `redis.enabled` the recommenders use a sliding window of recent data and fall back to SQL when Redis lacks what a mode needs, so a run is correct either way and Redis only changes speed.

> A recommender is a property of the **agent**, so one run can compare feeds: give half the population one mode and half another.
{: .ys-tip}

## Where to next

- [Opinion dynamics]({{ site.baseurl }}/opinions/)
- [Parameters]({{ site.baseurl }}/parameters/)
