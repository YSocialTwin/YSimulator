---
title: "Feed e raccomandatori"
subtitle: "Quindici modi di costruire un feed e dodici di suggerire account, su SQL o Redis."
goal: "Scegliere un raccomandatore di contenuti e uno di follow e sapere che cosa favorisce ciascuno."
time: "15 minuti"
---

## Due raccomandatori per agente

Ogni agente ha un **raccomandatore di contenuti** (`recsys_type`, quali post legge) e uno di **follow** (`frecsys_type`, chi gli viene proposto). I post sono candidati finché stanno dentro la finestra di visibilità (`posts.visibility_rounds`, 36 slot), i post dell'agente sono esclusi e il client chiede `recommendations.default_limit` post per chiamata. `reading_from_follower_ratio` fissa la quota che deve venire da utenti seguiti.

## Modalità per i contenuti

| Famiglia | Modalità |
|---|---|
| Tempo | `random`, `ReverseChrono`, `ReverseChronoPopularity` |
| Sociali | `ReverseChronoFollowers`, `ReverseChronoFollowersPopularity`, `ReverseChronoComments` |
| Interessi | `CommonInterests`, `common_user_interests` |
| Utenti simili | `SimilarUsersReactions`, `SimilarUsersPosts`, `CollaborativeUserUser`, `CollaborativeItemItem` |
| Contenuto | `ContentBasedFeatures`, `ContentBasedVector` |
| Combinata | `HybridLinearRanker` |

`random` è la base per i gruppi di controllo; `ReverseChrono` è la timeline trasparente con un bias di freschezza; le varianti Popularity aggiungono le reazioni come spareggio; le modalità collaborative e basate sul contenuto usano lo storico di reazioni e post.

{% include lab.html name="recsys" %}

## Modalità per i follow

`random`, `common_neighbors`, `jaccard`, `preferential_attachment`, `activity`, `resource_allocation`, `cosine_similarity`, `co_engagement`, `random_walk_restart`, `reactions_on_content`, `adamic_adar` e `two_hop_ego_sampling`. I punteggi di predizione dei link (vicini comuni, Jaccard, Adamic/Adar, resource allocation) favoriscono la chiusura triadica; `preferential_attachment` e `activity` favoriscono i già popolari e i già attivi, la ricetta classica degli hub.

## Redis o SQL

Entrambi i backend sono ibridi: con `redis.enabled` i raccomandatori usano una finestra mobile di dati recenti e ripiegano su SQL quando Redis non ha ciò che una modalità richiede, quindi una run è corretta in entrambi i casi e Redis cambia solo la velocità.

> Un raccomandatore è una proprietà dell'**agente**, quindi una run può confrontare feed: dai a metà popolazione una modalità e all'altra metà un'altra.
{: .ys-tip}

## Da dove continuare

- [Dinamica delle opinioni]({{ site.baseurl }}/it/opinions/)
- [Parametri]({{ site.baseurl }}/it/parameters/)
