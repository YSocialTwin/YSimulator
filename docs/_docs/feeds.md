---
title: "Feeds and recommenders"
subtitle: "Fifteen ways to build a feed, twelve to suggest accounts, and what an interaction does to the graph."
goal: "Choose a content and a follow recommender, know what each one favours and how reading feeds back into who an agent follows."
time: "20 minutes"
---

## Two recommenders per agent

Each agent has a **content recommender** (`recsys_type`, which posts it reads) and a **follow recommender** (`frecsys_type`, which accounts it is offered). A recommender is a property of the **agent**, so one run can compare feeds: give half the population one mode and half another. Posts are candidates while they are inside the visibility window (`posts.visibility_rounds`, 36 slots), the agent's own posts are excluded, and the client asks for `recommendations.default_limit` posts per call. `reading_from_follower_ratio` fixes the share of the page that must come from followed users in the modes that use followers.

## Content recommenders

Every mode returns the best posts in the visibility window; most of them break ties with the newest post, and the ones that depend on history fall back to a random page (the *cold start*) when the agent has no history yet.

| Mode | What it favours | How it ranks |
|---|---|---|
| `random` | nothing: the control group | random order of the visible posts |
| `ReverseChrono` | the newest | newest first, a transparent timeline |
| `ReverseChronoPopularity` | the most reacted | reactions first, newest on ties; completed with the newest if the page is not full |
| `ReverseChronoFollowers` | followed authors | a share `reading_from_follower_ratio` of the page from followed authors, newest first; the rest is newest first from everyone |
| `ReverseChronoFollowersPopularity` | followed authors, then the most reacted | the same split, each part ordered by reactions (newest on ties), with a last fill by newest |
| `ReverseChronoComments` | conversation | top-level posts with the most comments first, newest on ties |
| `CommonInterests` | the agent's topics | posts whose topics match the agent's interests, those of followed authors first (more matching topics first), then anyone; random if nothing matches |
| `common_user_interests` | what like-minded people react to | posts that users with interests in common with the agent reacted to, followed users first, by number of reactions |
| `SimilarUsersReactions` | what similar people like | posts liked by users who share the agent's age group, gender or political leaning, newest first |
| `SimilarUsersPosts` | similar authors | posts written by users who share the agent's age group, gender or political leaning, newest first |
| `CollaborativeUserUser` | the taste of the nearest users | finds the 50 users whose likes overlap most with the agent's and recommends what they liked, by number of such users |
| `CollaborativeItemItem` | posts liked together | posts liked by the same people who liked what the agent liked (co-occurrence), excluding posts already liked |
| `ContentBasedFeatures` | topics of what the agent liked | counts how many topics of a post match the topics of the posts the agent liked; skips posts already reacted to |
| `ContentBasedVector` | the same, weighted | like the previous one, but each matching topic weighs as many times as the agent liked it |
| `HybridLinearRanker` | a blend | candidates from followers, popularity and collaborative filtering, then a score: 0.28 recency + 0.25 followed author + 0.15 affinity with the author + 0.08 recent affinity + 0.16 topic similarity + 0.08 similar author |

Reading the table by family: the **time** modes (`random`, `ReverseChrono`, `ReverseChronoPopularity`) need no history; the **social** modes (`...Followers`, `...Comments`) use the graph and the conversation; the **interest**, **similar users** and **content-based** modes need topics, demographics or a history of reactions, and so work better after the first days; `HybridLinearRanker` is the only one that mixes them, with a recency term that decays as `exp(-age / 10)` rounds.

{% include lab.html name="recsys" %}

> Control groups: `random` removes any ordering, `ReverseChrono` keeps only recency. Comparing a mode with one of them isolates what its ranking adds.
{: .ys-tip}

## Follow recommenders

The follow recommender returns the ten best candidates for an agent that does not follow them yet. The agent then picks one: a rule-based agent at random, a language-model agent by reading the suggestions. It is used by the **daily follow** (with probability `probability_of_daily_follow`, at the end of the day) and by explicit `FOLLOW` actions. When it has nothing to score (an agent that follows nobody, for example) most modes complete the list with random accounts.

| Mode | What it favours | How it ranks |
|---|---|---|
| `random` | nobody in particular | random accounts not yet followed |
| `common_neighbors` | friends of friends | accounts followed by the people the agent follows, by how many of them follow the account |
| `jaccard` | friends of friends, normalised | common neighbours over the union of the two lists of followed accounts, which penalises accounts that follow everybody |
| `adamic_adar` | friends of friends who are not hubs | each common neighbour counts `1/log(degree)` |
| `resource_allocation` | the same, harsher on hubs | each common neighbour counts `1/degree` |
| `preferential_attachment` | the already popular | most followers first: the rich get richer |
| `activity` | the active | most posts in the last 10 rounds |
| `cosine_similarity` | similar profiles | cosine similarity of interests and personality traits over a random sample of 100 candidates |
| `co_engagement` | the same attention | accounts that liked or commented on the same posts as the agent |
| `random_walk_restart` | the neighbourhood, weighted by paths | 10 random walks of length 3 from the agent, restarting at the agent with probability 0.15; the most visited accounts win |
| `reactions_on_content` | who already pays attention | accounts that reacted most to the agent's own posts |
| `two_hop_ego_sampling` | nearby accounts that close triangles | samples 1-hop and 2-hop neighbours and scores the 2-hop ones: 0.3 recent posts + 0.4 interactions with the 1-hop neighbours + 0.3 triangles that following would close |

The link-prediction scores (`common_neighbors`, `jaccard`, `adamic_adar`, `resource_allocation`) favour **triadic closure**, so they build clusters; `preferential_attachment` and `activity` favour the already popular and the already active, which is the classic recipe for hubs; the profile and engagement scores (`cosine_similarity`, `co_engagement`, `reactions_on_content`) favour **homophily** and reciprocity. The runtime keeps the political-leaning bias of the follow recommenders neutral (no extra weight for same-leaning candidates).

{% include lab.html name="follow" %}

## What an interaction does to the graph

Reading is not neutral: a post that an agent reads, reacts to, comments on or shares can change **whom it follows**. This is the *secondary follow*, and it closes a loop between the feed and the graph.

1. After the content actions of a slot, every interaction with another agent's post is a candidate (an agent never evaluates itself).
2. With probability `probability_of_secondary_follow` the candidate is evaluated; the client asks the server whether the agent already follows the author.
3. A **rule-based** agent draws *follow*, *unfollow* or *no change* with equal chance, and acts only when it makes sense (it follows a stranger, unfollows a followed account). A **language-model** agent reads the post and the follow status and answers *follow*, *unfollow* or nothing.
4. The decision becomes a `FOLLOW` or `UNFOLLOW` action on the author, stored like any other.
5. Every explicit follow or unfollow, including these, can be answered by the other side: with `probability_of_follow_back` the target follows (or unfollows) the actor in return. The client checks the reverse edge first, so there are no duplicate rows and no unfollow of an edge that does not exist; a language-model target looks at the actor's profile before answering.

The loop matters because the feed reads the graph: with a followers mode (`ReverseChronoFollowers`, `ReverseChronoFollowersPopularity`, `CommonInterests`, `common_user_interests`, the hybrid ranker) the followed authors are shown more, so they are met more, so they are followed and unfollowed more. A high `probability_of_secondary_follow` with a followers feed tends to reinforce the existing structure, since the authors an agent already follows are the ones it meets again; with `random` or `ReverseChrono` exposure does not depend on the graph, so the same probability has no such feedback. Reciprocal follows add reciprocity to the edges that this loop creates. It is an effect to measure, not a promise: compare runs that differ only in these probabilities.

{% include lab.html name="secondary" %}

For the other ways in which the graph changes (daily follows, the fading follow appetite) see [Follow dynamics]({{ site.baseurl }}/network/).

## Redis or SQL

Both backends are hybrid: with `redis.enabled` the recommenders use a sliding window of recent data and fall back to SQL when Redis lacks what a mode needs, so a run is correct either way and Redis only changes speed.

## Where to next

- [Follow dynamics]({{ site.baseurl }}/network/)
- [Opinion dynamics]({{ site.baseurl }}/opinions/)
- [Parameters]({{ site.baseurl }}/parameters/)
