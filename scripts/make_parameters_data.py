#!/usr/bin/env python3
"""Write docs/assets/data/parameters.json (the data of the page "Parameters").

``python scripts/make_parameters_data.py``           rewrite the file
``python scripts/make_parameters_data.py --check``   exit 1 when the file is not up to date

YSimulator has no JSON Schema for its configuration, so the catalogue lives here: the settings of ``server_config.json`` and
``simulation_config.json`` with the default the runtime uses when the key is absent, described in English and Italian.
``--check`` also verifies that every setting of ``example/rule_population_100`` and ``example/llm_population_100`` is in the
catalogue, so a new key of the examples cannot go undocumented.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "docs" / "assets" / "data" / "parameters.json"

# (path, kind, default, basic, help_en, help_it[, extra])   kind: bool int float str choice list table kv ranges
SERVER = [
    ("run", "Run and connection", "Esecuzione e connessione", [
        ("server_name", "str", "orchestrator_server", True, "Name of the server Ray actor; clients find it by this name (used in the logs).", "Nome dell'attore Ray del server; i client lo trovano con questo nome (usato nei log)."),
        ("namespace", "str", "social_sim", True, "Ray namespace; it must be the same in the server and in every client.", "Namespace Ray; deve essere lo stesso nel server e in ogni client."),
        ("address", "str", "auto", False, "Address of the Ray cluster; auto starts or finds the local one.", "Indirizzo del cluster Ray; auto avvia o trova quello locale."),
        ("port", "int", None, False, "Reserved for future use.", "Riservato a usi futuri."),
        ("min_to_start", "int", 1, True, "Clients that must be registered before the simulation begins. With several clients set it to their number.", "Client che devono essere registrati prima che la simulazione cominci. Con più client impostalo al loro numero.", {"min": 1}),
        ("timeout_seconds", "int", 60, True, "Seconds without a heartbeat after which a client is marked stale and dropped from the barrier.", "Secondi senza heartbeat dopo i quali un client è considerato inattivo e tolto dalla barriera.", {"min": 1}),
    ]),
    ("database", "Database", "Database", [
        ("database.type", "choice", "sqlite", True, "SQL backend through SQLAlchemy.", "Backend SQL tramite SQLAlchemy.", {"choices": ["sqlite", "postgresql", "mysql"]}),
        ("database.sqlite.filename", "str", "simulation.db", False, "SQLite file (development and single-machine runs).", "File SQLite (sviluppo ed esecuzioni su una macchina)."),
        ("database.postgresql.host", "str", "localhost", False, "PostgreSQL host.", "Host PostgreSQL."),
        ("database.postgresql.port", "int", 5432, False, "PostgreSQL port.", "Porta PostgreSQL.", {"min": 1}),
        ("database.postgresql.database", "str", "ysimulator", False, "PostgreSQL database name.", "Nome del database PostgreSQL."),
        ("database.postgresql.username", "str", "postgres", False, "PostgreSQL user.", "Utente PostgreSQL."),
        ("database.postgresql.password", "str", "password", False, "PostgreSQL password.", "Password PostgreSQL."),
        ("database.mysql.host", "str", "localhost", False, "MySQL host.", "Host MySQL."),
        ("database.mysql.port", "int", 3306, False, "MySQL port.", "Porta MySQL.", {"min": 1}),
        ("database.mysql.database", "str", "ysimulator", False, "MySQL database name.", "Nome del database MySQL."),
        ("database.mysql.username", "str", "root", False, "MySQL user.", "Utente MySQL."),
        ("database.mysql.password", "str", "password", False, "MySQL password.", "Password MySQL."),
    ]),
    ("redis", "Redis cache", "Cache Redis", [
        ("redis.enabled", "bool", False, True, "Use Redis as a fast cache for the recommenders. With it off (or Redis unreachable) every recommender falls back to SQL.", "Usa Redis come cache veloce per i raccomandatori. Se è spento (o Redis non risponde) ogni raccomandatore ripiega su SQL."),
        ("redis.host", "str", "localhost", False, "Redis host.", "Host Redis."),
        ("redis.port", "int", 6379, False, "Redis port.", "Porta Redis.", {"min": 1}),
        ("redis.db", "int", 0, False, "Redis database number.", "Numero del database Redis.", {"min": 0}),
        ("redis.password", "str", None, False, "Redis password, null for none.", "Password Redis, null se assente."),
        ("redis.sliding_window_days", "int", 2, False, "Days of posts kept in the Redis window.", "Giorni di post tenuti nella finestra Redis.", {"min": 1}),
    ]),
    ("content", "Content and archetypes", "Contenuti e archetipi", [
        ("posts.visibility_rounds", "int", 36, True, "Time slots a post stays visible to the recommenders.", "Slot di tempo per cui un post resta visibile ai raccomandatori.", {"min": 1}),
        ("simulation.agent_archetypes.enabled", "bool", True, True, "Server side: use the archetype distribution and transitions.", "Lato server: usa distribuzione e transizioni degli archetipi."),
        ("simulation.agent_archetypes.distribution", "kv", {"validator": 0.33, "broadcaster": 0.33, "explorer": 0.34}, False, "Share of each archetype among the agents.", "Quota di ciascun archetipo tra gli agenti."),
        ("simulation.agent_archetypes.transitions", "table", None, False, "Probability that an agent of one archetype passes to another (a row per archetype, rows sum to 1).", "Probabilità che un agente di un archetipo passi a un altro (una riga per archetipo, le righe sommano a 1)."),
    ]),
    ("logging", "Logs", "Log", [
        ("logging.enable_server_log", "bool", True, False, "Write the server log.", "Scrive il log del server."),
        ("logging.enable_actor_log", "bool", True, False, "Write the structured actor log.", "Scrive il log strutturato degli attori."),
        ("logging.enable_request_log", "bool", True, False, "Write the request trace.", "Scrive la traccia delle richieste."),
        ("logging.enable_console_log", "bool", True, False, "Also print the logs on the console.", "Stampa i log anche sulla console."),
    ]),
]

CLIENT = [
    ("run", "Run and connection", "Esecuzione e connessione", [
        ("client_name", "str", "client_1", True, "Name of this client; distinct for every client of a multi-client run.", "Nome di questo client; distinto per ogni client di una run multi-client."),
        ("namespace", "str", "social_sim", True, "Ray namespace; it must match the server.", "Namespace Ray; deve coincidere con quello del server."),
        ("server.address", "str", None, False, "Address of the server; optional when ray_config.temp exists in the configuration folder.", "Indirizzo del server; facoltativo se nella cartella di configurazione esiste ray_config.temp."),
        ("server.port", "int", None, False, "Port of the server; optional with ray_config.temp.", "Porta del server; facoltativa con ray_config.temp."),
    ]),
    ("time", "Time and population", "Tempo e popolazione", [
        ("simulation.num_days", "int", 30, True, "Days to simulate; 0 means an infinite simulation.", "Giorni da simulare; 0 significa una simulazione infinita.", {"min": 0}),
        ("simulation.num_slots_per_day", "int", 24, True, "Time slots in a day (one per hour).", "Slot di tempo in un giorno (uno per ora).", {"min": 1}),
        ("simulation.heartbeat_interval", "int", 5, False, "Seconds between heartbeats sent to the server.", "Secondi tra gli heartbeat inviati al server.", {"min": 1}),
        ("simulation.percentage_new_agents_iteration", "float", 0.0, False, "Legacy: fraction of new agents joining each day (use agents.new_agents).", "Retaggio: frazione di nuovi agenti ogni giorno (usa agents.new_agents).", {"min": 0, "max": 1}),
        ("simulation.percentage_removed_agents_iteration", "float", 0.0, False, "Legacy: fraction of agents leaving each day (use agents.churn).", "Retaggio: frazione di agenti che escono ogni giorno (usa agents.churn).", {"min": 0, "max": 1}),
        ("simulation.discussion_topics", "list", [], True, "Topics agents write about.", "Argomenti di cui scrivono gli agenti."),
        ("simulation.activity_profiles", "table", None, True, "Named activity patterns: profile name to the hours (0-23) in which the agent is active.", "Schemi di attività con nome: nome del profilo e ore (0-23) in cui l'agente è attivo."),
        ("simulation.hourly_activity", "kv", None, True, "Probability that an agent without a profile is active in each hour, keyed by hour.", "Probabilità che un agente senza profilo sia attivo in ogni ora, indicizzata per ora."),
        ("recommendations.default_limit", "int", 5, False, "Posts the client asks the server for in each recommendation call.", "Post che il client chiede al server a ogni chiamata di raccomandazione.", {"min": 1}),
    ]),
    ("actions", "Actions and archetypes", "Azioni e archetipi", [
        ("simulation.actions_likelihood.post", "float", 3.0, True, "Relative weight of POST.", "Peso relativo di POST.", {"min": 0}),
        ("simulation.actions_likelihood.image", "float", 0.0, False, "Relative weight of sharing an image.", "Peso relativo della condivisione di un'immagine.", {"min": 0}),
        ("simulation.actions_likelihood.news", "float", 0.0, False, "Relative weight of posting a news item.", "Peso relativo della pubblicazione di una notizia.", {"min": 0}),
        ("simulation.actions_likelihood.comment", "float", 5.0, True, "Relative weight of COMMENT.", "Peso relativo di COMMENT.", {"min": 0}),
        ("simulation.actions_likelihood.read", "float", 2.0, True, "Relative weight of READ (read the feed and react).", "Peso relativo di READ (leggere il feed e reagire).", {"min": 0}),
        ("simulation.actions_likelihood.share", "float", 1.0, True, "Relative weight of SHARE.", "Peso relativo di SHARE.", {"min": 0}),
        ("simulation.actions_likelihood.search", "float", 5.0, True, "Relative weight of searching posts by topic.", "Peso relativo della ricerca di post per argomento.", {"min": 0}),
        ("simulation.actions_likelihood.cast", "float", 0.0, False, "Relative weight of the cast action.", "Peso relativo dell'azione cast.", {"min": 0}),
        ("simulation.actions_likelihood.share_link", "float", 0.0, False, "Relative weight of sharing a link (page agents).", "Peso relativo della condivisione di un link (agenti pagina).", {"min": 0}),
        ("simulation.actions_likelihood.follow", "float", 0.1, True, "Relative weight of FOLLOW.", "Peso relativo di FOLLOW.", {"min": 0}),
        ("simulation.agent_archetypes.enabled", "bool", True, True, "Restrict each agent to the actions of its archetype (validator, broadcaster, explorer).", "Limita ogni agente alle azioni del suo archetipo (validator, broadcaster, explorer)."),
        ("simulation.agent_archetypes.agent_downcast", "bool", True, True, "Force validators and explorers to rule-based behaviour whatever their llm flag says; broadcasters keep it. Saves model calls.", "Forza validator ed explorer a un comportamento a regole qualunque sia il loro flag llm; i broadcaster lo mantengono. Risparmia chiamate al modello."),
        ("simulation.agent_archetypes.distribution", "kv", {"validator": 0.33, "broadcaster": 0.33, "explorer": 0.34}, False, "Share of each archetype among the agents.", "Quota di ciascun archetipo tra gli agenti."),
        ("simulation.emotion_annotation", "bool", False, False, "Annotate the emotions of written texts (a model call per text).", "Annota le emozioni dei testi scritti (una chiamata al modello per testo)."),
    ]),
    ("agents", "Reading, follows and population dynamics", "Lettura, follow e dinamica della popolazione", [
        ("agents.reading_from_follower_ratio", "float", 0.6, True, "Share of the posts of a feed that come from followed users.", "Quota dei post di un feed che viene da utenti seguiti.", {"min": 0, "max": 1}),
        ("agents.max_length_thread_reading", "int", 5, False, "Maximum depth of the comment thread an agent reads.", "Profondità massima del thread di commenti che un agente legge.", {"min": 1}),
        ("agents.attention_window", "int", 336, False, "Slots of content still visible to the agent (336 = 14 days of 24 slots).", "Slot di contenuto ancora visibili all'agente (336 = 14 giorni da 24 slot).", {"min": 1}),
        ("agents.probability_of_daily_follow", "float", 0.1, True, "Probability that an agent evaluates new follows at the end of each day.", "Probabilità che un agente valuti nuovi follow a fine giornata.", {"min": 0, "max": 1}),
        ("agents.probability_of_secondary_follow", "float", 0.1, True, "Probability of a follow or unfollow after interacting with someone's content.", "Probabilità di un follow o unfollow dopo un'interazione con i contenuti di qualcuno.", {"min": 0, "max": 1}),
        ("agents.probability_of_follow_back", "float", None, True, "Probability of answering a follow or unfollow in kind (reciprocal follow).", "Probabilità di ricambiare un follow o un unfollow (follow reciproco).", {"min": 0, "max": 1}),
        ("agents.follow_action_decay.enabled", "bool", False, False, "Make the weight of FOLLOW fall as the agent gets older.", "Fa calare il peso di FOLLOW con l'età dell'agente."),
        ("agents.follow_action_decay.decay_function", "choice", "exponential", False, "Shape of the decay.", "Forma del decadimento.", {"choices": ["exponential", "linear"]}),
        ("agents.follow_action_decay.half_life_rounds", "int", 168, False, "Rounds after which the exponential multiplier halves.", "Turni dopo i quali il moltiplicatore esponenziale si dimezza.", {"min": 1}),
        ("agents.follow_action_decay.decay_rate", "float", 0.01, False, "Loss of multiplier per round for the linear decay.", "Perdita di moltiplicatore per turno nel decadimento lineare.", {"min": 0}),
        ("agents.follow_action_decay.min_probability_ratio", "float", 0.1, False, "Floor of the multiplier.", "Soglia minima del moltiplicatore.", {"min": 0, "max": 1}),
        ("agents.churn.enabled", "bool", False, True, "Let inactive agents leave the platform.", "Lascia che gli agenti inattivi abbandonino la piattaforma."),
        ("agents.churn.churn_probability", "float", 0.1, False, "Probability that the churn check runs on a given day.", "Probabilità che il controllo di abbandono scatti in un dato giorno.", {"min": 0, "max": 1}),
        ("agents.churn.inactivity_threshold", "int", 5, False, "Rounds of inactivity after which an agent becomes a candidate.", "Turni di inattività dopo i quali un agente diventa candidato.", {"min": 1}),
        ("agents.churn.churn_percentage", "float", 0.05, False, "Share of the candidates that actually leave.", "Quota dei candidati che se ne va davvero.", {"min": 0, "max": 1}),
        ("agents.new_agents.enabled", "bool", False, True, "Let new agents join during the run.", "Lascia entrare nuovi agenti durante la run."),
        ("agents.new_agents.probability_new_agents", "float", 0.1, False, "Probability that new agents join on a given day.", "Probabilità che nuovi agenti entrino in un dato giorno.", {"min": 0, "max": 1}),
        ("agents.new_agents.percentage_new_agents", "float", 0.05, False, "Size of the arrival, as a share of the population.", "Dimensione dell'arrivo, come quota della popolazione.", {"min": 0, "max": 1}),
    ]),
    ("llm", "Language models", "Modelli linguistici", [
        ("llm.address", "str", "localhost", True, "Host of the text model server.", "Host del server del modello di testo."),
        ("llm.port", "int", 11434, True, "Port of the text model server.", "Porta del server del modello di testo.", {"min": 1}),
        ("llm.model", "str", "llama3.2", True, "Text model that writes posts and comments.", "Modello di testo che scrive post e commenti."),
        ("llm.backend", "choice", "ollama", False, "ollama uses the remote path (and may upgrade to the batched adapter); vllm starts the embedded local VLLMService.", "ollama usa il percorso remoto (e può passare all'adattatore a batch); vllm avvia il VLLMService locale incorporato.", {"choices": ["ollama", "vllm"]}),
        ("llm.api_format", "choice", "auto", False, "With a remote backend: probe OpenAI-compatible first then Ollama (auto), or force one.", "Con un backend remoto: prova prima OpenAI-compatibile poi Ollama (auto), oppure forzane uno.", {"choices": ["auto", "openai", "ollama"]}),
        ("llm.batching_policy", "choice", "auto", False, "auto probes the endpoint and uses batching if it works; off never batches; force fails at start if batching does not work.", "auto prova l'endpoint e usa il batching se funziona; off non fa mai batching; force fallisce all'avvio se il batching non funziona.", {"choices": ["auto", "off", "force"]}),
        ("llm.temperature", "float", 0.7, True, "Sampling temperature of the text model.", "Temperatura di campionamento del modello di testo.", {"min": 0}),
        ("llm.llm_api_key", "str", "NULL", False, "API key; the string NULL means none.", "Chiave API; la stringa NULL significa nessuna."),
        ("llm.llm_max_tokens", "int", -1, False, "Maximum tokens of an answer; -1 leaves it to the server.", "Token massimi di una risposta; -1 lo lascia al server."),
        ("llm_v.address", "str", "localhost", False, "Host of the vision model server.", "Host del server del modello di visione."),
        ("llm_v.port", "int", 11434, False, "Port of the vision model server.", "Porta del server del modello di visione.", {"min": 1}),
        ("llm_v.model", "str", "minicpm-v", False, "Vision model that describes images; without it image actions are skipped.", "Modello di visione che descrive le immagini; senza di esso le azioni con immagini sono saltate."),
        ("llm_v.temperature", "float", 0.5, False, "Sampling temperature of the vision model.", "Temperatura di campionamento del modello di visione.", {"min": 0}),
        ("llm_v.llm_api_key", "str", "NULL", False, "API key of the vision model.", "Chiave API del modello di visione."),
        ("llm_v.llm_max_tokens", "int", 300, False, "Maximum tokens of a vision answer.", "Token massimi di una risposta del modello di visione.", {"min": 1}),
    ]),
    ("memory", "Agent memory", "Memoria degli agenti", [
        ("agents.memory_enabled", "bool", False, True, "Memory for LLM agents (client side only; rule-based agents have none).", "Memoria per gli agenti LLM (solo lato client; gli agenti a regole non ne hanno)."),
        ("agents.memory_backend", "str", "hybrid_semantic", False, "Memory engine backend.", "Backend del motore di memoria."),
        ("agents.memory_prompt_mode", "str", "subtle_timeline", False, "How memory is written into the prompt.", "Come la memoria è scritta nel prompt."),
        ("agents.memory_semantic_enabled", "bool", True, False, "Semantic retrieval with embeddings.", "Recupero semantico con gli embedding."),
        ("agents.memory_embedding_model", "str", "embeddinggemma", False, "Embedding model served by the client's model stack.", "Modello di embedding servito dallo stack di modelli del client."),
        ("agents.memory_search_k", "int", 8, False, "Items retrieved by a semantic search.", "Elementi recuperati da una ricerca semantica.", {"min": 1}),
        ("agents.memory_search_max_chars", "int", 900, False, "Text budget of the retrieved items.", "Budget di testo degli elementi recuperati.", {"min": 1}),
        ("agents.memory_search_time_window_rounds", "int", 18, False, "How far back, in rounds, a search looks.", "Quanto indietro, in turni, guarda una ricerca.", {"min": 1}),
        ("agents.memory_pair_limit", "int", 8, False, "Limit of the pairwise interaction history.", "Limite dello storico delle interazioni a coppie.", {"min": 1}),
        ("agents.memory_reply_context_max_chars", "int", 220, False, "Characters of memory injected into reply prompts.", "Caratteri di memoria inseriti nei prompt di risposta.", {"min": 1}),
        ("agents.memory_total_max_chars", "int", 2200, False, "Total characters of memory in a prompt.", "Caratteri totali di memoria in un prompt.", {"min": 1}),
        ("agents.memory_tier_a_max_chars", "int", 350, False, "Budget of the tier A memories.", "Budget dei ricordi di livello A.", {"min": 1}),
        ("agents.memory_tier_b_max_chars", "int", 900, False, "Budget of the tier B memories.", "Budget dei ricordi di livello B.", {"min": 1}),
        ("agents.memory_tier_c_max_chars", "int", 900, False, "Budget of the tier C memories.", "Budget dei ricordi di livello C.", {"min": 1}),
        ("agents.memory_tier_c_uncertainty_threshold", "float", 0.45, False, "Uncertainty above which tier C is used.", "Incertezza oltre la quale si usa il livello C.", {"min": 0, "max": 1}),
        ("agents.memory_digest_update_cadence_rounds", "int", 3, False, "Rounds between refreshes of the community digest.", "Turni tra un aggiornamento e l'altro del digest della comunità.", {"min": 1}),
        ("agents.memory_digest_events_limit", "int", 24, False, "Events summarised by the digest.", "Eventi riassunti dal digest.", {"min": 1}),
        ("agents.memory_reflection_cadence_rounds", "int", 3, False, "Rounds between reflections.", "Turni tra una riflessione e l'altra.", {"min": 1}),
        ("agents.memory_reflection_min_events", "int", 12, False, "Events needed before a reflection can run.", "Eventi necessari perché una riflessione possa partire.", {"min": 1}),
        ("agents.memory_reflection_trigger_importance_sum", "float", 3.5, False, "Sum of importance that triggers a reflection.", "Somma di importanza che fa scattare una riflessione.", {"min": 0}),
        ("agents.memory_reflection_max_items_per_run", "int", 60, False, "Items a reflection may read.", "Elementi che una riflessione può leggere.", {"min": 1}),
        ("agents.memory_embedding_async", "bool", False, False, "Compute embeddings asynchronously.", "Calcola gli embedding in modo asincrono."),
        ("agents.memory_importance_mode", "str", "auto", False, "How the importance of an event is decided.", "Come si decide l'importanza di un evento."),
    ]),
    ("opinions", "Opinion dynamics", "Dinamica delle opinioni", [
        ("opinion_dynamics.enabled", "bool", True, True, "Update the opinions of the agents.", "Aggiorna le opinioni degli agenti."),
        ("opinion_dynamics.model_name", "choice", "bounded_confidence", True, "bounded_confidence works for every agent; llm_evaluation asks a model and only works for LLM agents.", "bounded_confidence vale per ogni agente; llm_evaluation chiede a un modello e vale solo per gli agenti LLM.", {"choices": ["bounded_confidence", "llm_evaluation"]}),
        ("opinion_dynamics.parameters.epsilon", "float", 0.25, True, "Confidence bound: opinions closer than this influence each other.", "Soglia di confidenza: opinioni più vicine di così si influenzano.", {"min": 0, "max": 1}),
        ("opinion_dynamics.parameters.mu", "float", 0.5, True, "Convergence rate inside the bound.", "Tasso di convergenza dentro la soglia.", {"min": 0, "max": 1}),
        ("opinion_dynamics.parameters.theta", "float", 0.0, False, "Polarisation rate outside the bound.", "Tasso di polarizzazione fuori dalla soglia.", {"min": 0, "max": 1}),
        ("opinion_dynamics.parameters.cold_start", "choice", "neutral", False, "Opinion of an agent that has none: neutral, or inherited from the author.", "Opinione di un agente che non ne ha: neutra, oppure ereditata dall'autore.", {"choices": ["neutral", "inherited"]}),
        ("opinion_dynamics.parameters.evaluation_scope", "choice", "interlocutor_only", False, "llm_evaluation only: consider the author alone, or also the opinions of the accounts the reader follows.", "Solo llm_evaluation: considera il solo autore, oppure anche le opinioni degli account seguiti dal lettore.", {"choices": ["interlocutor_only", "neighbors"]}),
        ("opinion_dynamics.opinion_groups", "ranges", None, False, "Names of the opinion classes and the interval of [0, 1] each covers.", "Nomi delle classi di opinione e intervallo di [0, 1] che ciascuna copre."),
    ]),
    ("stress", "Stress and reward", "Stress e ricompensa", [
        ("stress_reward.enabled", "bool", False, True, "Compute stress and reward from interactions, and let them shape activity and churn.", "Calcola stress e ricompensa dalle interazioni e lascia che influenzino attività e abbandono."),
        ("stress_reward.backward_rounds", "int", 24, False, "Rounds the agent looks back when it asks for its current state.", "Turni a ritroso che l'agente guarda quando chiede il suo stato attuale.", {"min": 0}),
        ("stress_reward.system.churn.enabled", "bool", False, False, "Let stress drive agents out of the platform.", "Lascia che lo stress porti gli agenti fuori dalla piattaforma."),
    ]),
    ("logging", "Logs", "Log", [
        ("logging.enable_execution_log", "bool", True, False, "Write the execution log of the client.", "Scrive il log di esecuzione del client."),
        ("logging.enable_actor_log", "bool", True, False, "Write the structured actor log.", "Scrive il log strutturato degli attori."),
        ("logging.enable_client_log", "bool", True, False, "Write the client log.", "Scrive il log del client."),
        ("logging.enable_console_log", "bool", True, False, "Also print the logs on the console.", "Stampa i log anche sulla console."),
        ("logging.enable_llm_usage_log", "bool", True, False, "Write the accounting of the model calls.", "Scrive il conteggio delle chiamate al modello."),
    ]),
]


def fields(sections):
    out = []
    for sid, en, it, items in sections:
        fs = []
        for item in items:
            path, kind, default, basic, h_en, h_it = item[:6]
            extra = item[6] if len(item) > 6 else {}
            fs.append({"path": path, "kind": kind, "default": default, "min": extra.get("min"), "xmin": extra.get("xmin"), "max": extra.get("max"),
                       "choices": extra.get("choices"), "basic": basic, "label": path, "label_it": path, "help": h_en, "help_it": h_it})
        out.append({"id": sid, "title": en, "title_it": it, "fields": fs})
    return out


def flatten(obj, prefix=""):
    for k, v in obj.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict) and v and not all(isinstance(x, (list, str)) for x in v.values()) and k not in ("actions_likelihood", "hourly_activity", "activity_profiles", "opinion_groups", "distribution", "transitions"):
            yield from flatten(v, key + ".")
        else:
            yield key


def catalogue_paths(sections):
    return {i[0] for s in sections for i in s[3]}


#: keys that the example writes at a level the code does not read (the code reads them under ``parameters``): not documented
#: as settings of their own
MISPLACED_IN_EXAMPLE = {"simulation.note"}


def undocumented() -> list:
    missing = []
    for example in ("rule_population_100", "llm_population_100"):
        for fname, sections in (("server_config.json", SERVER), ("simulation_config.json", CLIENT)):
            f = ROOT / "example" / example / fname
            if not f.is_file():
                continue
            known = catalogue_paths(sections)
            for p in flatten(json.loads(f.read_text(encoding="utf-8"))):
                if p not in known and p not in MISPLACED_IN_EXAMPLE and not any(k.startswith(p + ".") for k in known):
                    entry = f"{example}/{fname}: {p}"
                    if entry not in missing:
                        missing.append(entry)
    return missing


def build() -> dict:
    return {"server": fields(SERVER), "client": fields(CLIENT)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = json.dumps(build(), indent=1, ensure_ascii=False) + "\n"
    missing = undocumented()
    if missing:
        print("not in the catalogue:\n  " + "\n  ".join(missing), file=sys.stderr)
    if args.check:
        return 0 if (OUTPUT.is_file() and OUTPUT.read_text(encoding="utf-8") == text and not missing) else 1
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
