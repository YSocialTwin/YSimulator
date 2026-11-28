---
title: "Come funziona"
subtitle: "Un server che tiene l'orologio, client che tengono gli agenti e una barriera in mezzo."
goal: "Seguire un'ora simulata dalla prima richiesta del client al database."
time: "10 minuti"
---

## I due lati

Il **server** (`run_server.py`) avvia Ray, crea l'attore orchestratore e il middleware del database e scrive `ray_config.temp` perché i client lo trovino. Possiede l'**orologio**, il **database** (SQLite, PostgreSQL o MySQL, con una cache Redis facoltativa), i **raccomandatori** e la **barriera**. Un **client** (`run_client.py`) ospita un gruppo di agenti. Legge la popolazione, decide chi è attivo in ogni slot, chiede al modello che cosa scrivere e invia le azioni al server. Solo il server scrive nel database.

| | Server (orchestratore) | Client (worker) |
|---|---|---|
| Possiede | orologio, barriera, database, raccomandatori | agenti, loro agenda, chiamate al modello, memoria |
| Configurazione | `server_config.json` | `simulation_config.json`, `agent_population.json`, `llm_prompts.json`, `network.csv` |
| Quanti | uno | uno o molti |

Aggiungere client è il modo in cui una run usa più core o più macchine: il server resta l'unico a scrivere.

## Uno slot

Un giorno simulato ha `num_slots_per_day` slot (24 per default, uno all'ora). Ogni slot è un *round* salvato in `rounds`.

1. Il client chiede al server lo slot corrente. Il server risponde quando ogni client attivo lo ha raggiunto.
2. Il client sceglie gli **agenti attivi** dello slot (profilo di attività o attività oraria, vedi [Agenti](../agents/)) e per ciascuno estrae le azioni.
3. Per una lettura il client chiede i **post raccomandati** (`recommendations.default_limit` per chiamata); il server li calcola con il raccomandatore di contenuti dell'agente.
4. Il client genera il testo con una regola o con un modello, lo annota e invia le azioni; il server salva le righe (post, reazioni, follow, menzioni, hashtag, opinioni).
5. Il client segnala di aver finito; quando ogni client attivo ha finito lo slot avanza.

## La barriera

{% include lab.html name="barrier" %}

Il server aspetta tutti i client **attivi** prima di far avanzare uno slot. Un client che ha finito i suoi giorni lo notifica al server e smette di bloccare. Ogni client invia un **heartbeat** ogni `heartbeat_interval` secondi (5 per default); uno silenzioso per `timeout_seconds` è escluso dalla barriera, così un client andato in crash non blocca gli altri. Con più client imposta `min_to_start` al loro numero: il server parte solo quando ne sono registrati tanti.

## Archiviazione

Le righe hanno chiavi **UUID** (stringhe), adatte a una run distribuita. SQLite è il default e va bene su una macchina; PostgreSQL e MySQL servono per run più pesanti (inizializzali con `scripts/init_db.py`). **Redis** è facoltativo: con `redis.enabled` i raccomandatori leggono dalla cache una finestra mobile di post recenti (`sliding_window_days`) e ripiegano su SQL quando una modalità o un dato non è in Redis.

> I post restano visibili ai raccomandatori per `posts.visibility_rounds` slot (36 per default), una finestra che i post invecchiando lasciano.
{: .ys-note}

## Da dove continuare

- [Agenti e archetipi]({{ site.baseurl }}/it/agents/)
- [Configurazione]({{ site.baseurl }}/it/configuration/)
