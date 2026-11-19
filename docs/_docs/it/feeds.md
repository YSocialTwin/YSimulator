---
title: "Feed e raccomandatori"
subtitle: "Quindici modi di costruire un feed, dodici di suggerire account e che cosa fa un’interazione al grafo."
goal: "Scegliere un raccomandatore di contenuti e uno di follow, sapere che cosa favorisce ciascuno e come la lettura si riflette su chi un agente segue."
time: "20 minuti"
---

## Due raccomandatori per agente

Ogni agente ha un **raccomandatore di contenuti** (`recsys_type`, quali post legge) e uno **di follow** (`frecsys_type`, quali account gli vengono proposti). Un raccomandatore è una proprietà dell'**agente**, quindi una run può confrontare feed: dai a metà popolazione una modalità e all'altra metà un'altra. I post sono candidati finché stanno nella finestra di visibilità (`posts.visibility_rounds`, 36 slot), i post dell'agente sono esclusi e il client chiede `recommendations.default_limit` post per chiamata. `reading_from_follower_ratio` fissa la quota della pagina che deve venire da utenti seguiti nelle modalità che usano i follower.

## Raccomandatori di contenuti

Ogni modalità restituisce i migliori post della finestra di visibilità; la maggior parte spareggia con il più recente, e quelle che dipendono dalla storia ripiegano su una pagina casuale (il *cold start*) quando l'agente non ha ancora storia.

| Modalità | Che cosa favorisce | Come ordina |
|---|---|---|
| `random` | niente: il gruppo di controllo | ordine casuale dei post visibili |
| `ReverseChrono` | i più recenti | dal più recente, una timeline trasparente |
| `ReverseChronoPopularity` | i più reagiti | prima le reazioni, a parità i più recenti; completata con i più recenti se la pagina non è piena |
| `ReverseChronoFollowers` | gli autori seguiti | una quota `reading_from_follower_ratio` della pagina da autori seguiti, dal più recente; il resto dal più recente tra tutti |
| `ReverseChronoFollowersPopularity` | gli autori seguiti, poi i più reagiti | la stessa divisione, ciascuna parte ordinata per reazioni (a parità i più recenti), con un ultimo riempimento dai più recenti |
| `ReverseChronoComments` | la conversazione | prima i post principali con più commenti, a parità i più recenti |
| `CommonInterests` | gli argomenti dell'agente | post i cui argomenti coincidono con gli interessi dell'agente, prima quelli di autori seguiti (più argomenti in comune per primi), poi tutti; casuale se nulla coincide |
| `common_user_interests` | ciò a cui reagiscono persone affini | post a cui hanno reagito utenti con interessi in comune con l'agente, prima gli utenti seguiti, per numero di reazioni |
| `SimilarUsersReactions` | ciò che piace a utenti simili | post piaciuti a utenti con la stessa fascia di età, genere o orientamento politico dell'agente, dal più recente |
| `SimilarUsersPosts` | autori simili | post scritti da utenti con la stessa fascia di età, genere o orientamento politico dell'agente, dal più recente |
| `CollaborativeUserUser` | il gusto degli utenti più vicini | trova i 50 utenti i cui like si sovrappongono di più con quelli dell'agente e raccomanda ciò che è piaciuto a loro, per numero di questi utenti |
| `CollaborativeItemItem` | post apprezzati insieme | post piaciuti alle stesse persone a cui è piaciuto ciò che è piaciuto all'agente (co-occorrenza), esclusi i post già apprezzati |
| `ContentBasedFeatures` | gli argomenti di ciò che l'agente ha apprezzato | conta quanti argomenti di un post coincidono con quelli dei post apprezzati; salta i post già reagiti |
| `ContentBasedVector` | lo stesso, pesato | come la precedente, ma ogni argomento in comune pesa quante volte l'agente lo ha apprezzato |
| `HybridLinearRanker` | una miscela | candidati da follower, popolarità e filtro collaborativo, poi un punteggio: 0,28 recenza + 0,25 autore seguito + 0,15 affinità con l'autore + 0,08 affinità recente + 0,16 similarità degli argomenti + 0,08 autore simile |

Per famiglie: le modalità **temporali** (`random`, `ReverseChrono`, `ReverseChronoPopularity`) non richiedono storia; quelle **sociali** (`...Followers`, `...Comments`) usano il grafo e la conversazione; quelle per **interessi**, **utenti simili** e **contenuto** richiedono argomenti, dati demografici o una storia di reazioni, quindi funzionano meglio dopo i primi giorni; `HybridLinearRanker` è l'unica che le mescola, con un termine di recenza che decade come `exp(-età / 10)` turni.

{% include lab.html name="recsys" %}

> Gruppi di controllo: `random` toglie ogni ordinamento, `ReverseChrono` tiene solo la recenza. Confrontare una modalità con una delle due isola ciò che il suo ordinamento aggiunge.
{: .ys-tip}

## Raccomandatori di follow

Il raccomandatore di follow restituisce i dieci migliori candidati che l'agente non segue ancora. L'agente ne sceglie poi uno: un agente a regole a caso, un agente a modello linguistico leggendo i suggerimenti. Lo usano il **follow giornaliero** (con probabilità `probability_of_daily_follow`, a fine giornata) e le azioni `FOLLOW` esplicite. Quando non ha nulla da valutare (per esempio un agente che non segue nessuno) la maggior parte delle modalità completa l'elenco con account casuali.

| Modalità | Che cosa favorisce | Come ordina |
|---|---|---|
| `random` | nessuno in particolare | account casuali non ancora seguiti |
| `common_neighbors` | amici di amici | account seguiti da chi l'agente segue, per quanti di questi seguono l'account |
| `jaccard` | amici di amici, normalizzati | vicini in comune sull'unione delle due liste di seguiti, che penalizza gli account che seguono tutti |
| `adamic_adar` | amici di amici che non sono hub | ogni vicino in comune conta `1/log(grado)` |
| `resource_allocation` | lo stesso, più severo con gli hub | ogni vicino in comune conta `1/grado` |
| `preferential_attachment` | chi è già popolare | prima chi ha più follower: i ricchi diventano più ricchi |
| `activity` | gli attivi | più post negli ultimi 10 turni |
| `cosine_similarity` | profili simili | similarità del coseno di interessi e tratti di personalità su un campione casuale di 100 candidati |
| `co_engagement` | la stessa attenzione | account che hanno messo like o commentato gli stessi post dell'agente |
| `random_walk_restart` | il vicinato, pesato dai percorsi | 10 passeggiate casuali di lunghezza 3 dall'agente, con ripartenza dall'agente con probabilità 0,15; vincono gli account più visitati |
| `reactions_on_content` | chi già gli presta attenzione | account che hanno reagito di più ai post dell'agente |
| `two_hop_ego_sampling` | account vicini che chiudono triangoli | campiona vicini a 1 e 2 salti e valuta quelli a 2 salti: 0,3 post recenti + 0,4 interazioni con i vicini a 1 salto + 0,3 triangoli che il follow chiuderebbe |

I punteggi di link prediction (`common_neighbors`, `jaccard`, `adamic_adar`, `resource_allocation`) favoriscono la **chiusura triadica**, quindi costruiscono cluster; `preferential_attachment` e `activity` favoriscono chi è già popolare e già attivo, la ricetta classica degli hub; i punteggi di profilo e di coinvolgimento (`cosine_similarity`, `co_engagement`, `reactions_on_content`) favoriscono **omofilia** e reciprocità. Il runtime tiene neutro il bias dell'orientamento politico dei raccomandatori di follow (nessun peso extra per i candidati con lo stesso orientamento).

{% include lab.html name="follow" %}

## Che cosa fa un'interazione al grafo

Leggere non è neutro: un post che un agente legge, a cui reagisce, che commenta o condivide può cambiare **chi segue**. È il *follow secondario*, e chiude un ciclo tra feed e grafo.

1. Dopo le azioni sui contenuti di uno slot, ogni interazione con il post di un altro agente è un candidato (un agente non valuta mai sé stesso).
2. Con probabilità `probability_of_secondary_follow` il candidato viene valutato; il client chiede al server se l'agente segue già l'autore.
3. Un agente **a regole** estrae *follow*, *unfollow* o *nessun cambio* con uguale probabilità e agisce solo quando ha senso (segue un estraneo, smette di seguire un account seguito). Un agente **a modello linguistico** legge il post e lo stato del follow e risponde *follow*, *unfollow* o nulla.
4. La decisione diventa un'azione `FOLLOW` o `UNFOLLOW` sull'autore, salvata come ogni altra.
5. Ogni follow o unfollow esplicito, compresi questi, può avere risposta dall'altra parte: con `probability_of_follow_back` il destinatario segue (o smette di seguire) l'autore a sua volta. Il client controlla prima l'arco inverso, quindi non ci sono righe duplicate né unfollow di un arco inesistente; un destinatario a modello linguistico guarda il profilo di chi ha agito prima di rispondere.

Il ciclo conta perché il feed legge il grafo: con una modalità a follower (`ReverseChronoFollowers`, `ReverseChronoFollowersPopularity`, `CommonInterests`, `common_user_interests`, il ranker ibrido) gli autori seguiti sono mostrati di più, quindi incontrati di più, quindi seguiti e abbandonati di più. Una `probability_of_secondary_follow` alta con un feed a follower tende a rinforzare la struttura esistente, perché gli autori già seguiti sono quelli che l'agente reincontra; con `random` o `ReverseChrono` l'esposizione non dipende dal grafo, quindi la stessa probabilità non ha questo ritorno. I follow reciproci aggiungono reciprocità agli archi che questo ciclo crea. È un effetto da misurare, non una promessa: confronta run che differiscono solo per queste probabilità.

{% include lab.html name="secondary" %}

Per gli altri modi in cui il grafo cambia (follow giornalieri, appetito di follow che svanisce) vedi [Dinamica dei follow]({{ site.baseurl }}/it/network/).

## Redis o SQL

Entrambi i backend sono ibridi: con `redis.enabled` i raccomandatori usano una finestra mobile di dati recenti e ripiegano su SQL quando Redis non ha ciò che una modalità richiede, quindi una run è corretta in entrambi i casi e Redis cambia solo la velocità.

## Da dove continuare

- [Dinamica dei follow]({{ site.baseurl }}/it/network/)
- [Dinamica delle opinioni]({{ site.baseurl }}/it/opinions/)
- [Parametri]({{ site.baseurl }}/it/parameters/)
