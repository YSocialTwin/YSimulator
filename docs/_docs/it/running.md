---
title: "Eseguire un esperimento"
subtitle: "Installa, avvia il server, avvia i client, leggi il database."
goal: "Andare da un clone a un database che puoi interrogare."
time: "10 minuti"
---

## Installa

{% include shot.html file="new-hpc" caption="Il modulo "New Experiment" con HPC attivo, che crea un esperimento YSimulator." %}

{% include shot.html file="experiment" caption="La pagina di un esperimento YSimulator: controlli, client e interruttori delle annotazioni." %}

```bash
git clone https://github.com/YSocialTwin/YSimulator.git
cd YSimulator
pip install -r requirements.txt
```

Per gli agenti LLM serve anche un backend di modello (Ollama o vLLM); le run a regole non ne richiedono. Per PostgreSQL o MySQL crea prima lo schema con `python scripts/init_db.py --config my_config`.

## Esegui

```bash
python run_server.py --config my_config   # terminale 1
python run_client.py --config my_config   # terminale 2 (ripeti per più client)
```

Il server scrive `ray_config.temp` nella cartella perché i client lo trovino. L'output finisce nella stessa cartella: `simulation.db` (SQLite), `logs/` (log JSON a rotazione di server e client) e il file Ray temporaneo. Più client si dividono il carico; imposta `min_to_start` al loro numero.

## Da YSocial

In YSocial scegli *New Experiment → HPC* con la piattaforma di microblogging e l'app avvia server e client al posto tuo; le sue pagine leggono lo stesso database.

## Leggi i risultati

```sql
SELECT u.archetype, COUNT(*) AS posts
FROM post p JOIN user_mgmt u ON u.id = p.user_id
WHERE p.comment_to = '-1' GROUP BY u.archetype;
```

La pagina [Schema del database](../database-schema/) elenca ogni tabella.

## Da dove continuare

- [Schema del database]({{ site.baseurl }}/it/database-schema/)
- [Glossario]({{ site.baseurl }}/it/glossary/)
