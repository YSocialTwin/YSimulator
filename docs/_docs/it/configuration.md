---
title: "Configurazione"
subtitle: "Quattro file e una rete facoltativa descrivono un intero esperimento."
goal: "Sapere quale file contiene che cosa e partire da un esempio."
time: "10 minuti"
---

## I file

Tutti i file stanno in una cartella, passata con `--config`; senza `--config` si usa la cartella corrente.

| File | Letto da | Contiene |
|---|---|---|
| `server_config.json` | server | nome, namespace, client minimi, timeout, database, Redis, transizioni degli archetipi, log |
| `simulation_config.json` | client | giorni e slot, attività, pesi delle azioni, agenti, abbandono, opinioni, modelli, log |
| `agent_population.json` | client | gli agenti e la regola che ne genera altri |
| `llm_prompts.json` | client | modelli di prompt e persone |
| `network.csv` | client | archi di follow iniziali (facoltativo) |

Ciò che non è scritto prende il valore predefinito, quindi un file elenca solo ciò che cambi.

## Esempi

`example/` contiene scenari pronti come `rule_population_100` (solo regole, nessun modello necessario), `llm_population_100`, `llm_4clients` e `content_recsys`. Copiane uno in una nuova cartella e modificalo.

```bash
mkdir my_config
cp example/rule_population_100/*.json my_config/
```

## La forma di `simulation_config.json`

```json
{
  "client_name": "client_1", "namespace": "social_sim",
  "simulation": { "num_days": 30, "num_slots_per_day": 24,
    "actions_likelihood": { "post": 3.0, "comment": 5.0, "read": 2.0, "share": 1.0, "search": 5.0, "follow": 0.1 } },
  "agents": { "reading_from_follower_ratio": 0.6, "churn": { "enabled": true }, "new_agents": { "enabled": true } },
  "opinion_dynamics": { "enabled": true, "model_name": "bounded_confidence", "parameters": { "epsilon": 0.25, "mu": 0.5 } }
}
```

`server_config.json` e `simulation_config.json` devono concordare sul `namespace`. Con più client ognuno ha il proprio `client_name`.

## Da dove continuare

- [Parametri]({{ site.baseurl }}/it/parameters/)
- [Eseguire un esperimento]({{ site.baseurl }}/it/running/)
