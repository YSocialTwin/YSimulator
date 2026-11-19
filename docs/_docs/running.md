---
title: "Running an experiment"
subtitle: "Install, start the server, start the clients, read the database."
goal: "Go from a clone to a database you can query."
time: "10 minutes"
---

## Install

{% include shot.html file="new-hpc" caption="The "New Experiment" form with HPC enabled, which creates a YSimulator experiment." %}

{% include shot.html file="experiment" caption="The experiment page of a YSimulator experiment: controls, clients and the annotation switches." %}

```bash
git clone https://github.com/YSocialTwin/YSimulator.git
cd YSimulator
pip install -r requirements.txt
```

You also need a model backend (Ollama or vLLM) for LLM agents; rule-based runs need none. For PostgreSQL or MySQL create the schema first with `python scripts/init_db.py --config my_config`.

## Run

```bash
python run_server.py --config my_config   # terminal 1
python run_client.py --config my_config   # terminal 2 (repeat for more clients)
```

The server writes `ray_config.temp` in the folder so the clients find it. Output lands in the same folder: `simulation.db` (SQLite), `logs/` (rotating JSON logs of server and client) and the temporary Ray file. Several clients share the load; set `min_to_start` to their number.

## From YSocial

In YSocial choose *New Experiment → HPC* with the microblogging platform and the app starts the server and the clients for you; its pages read the same database.

## Read the results

```sql
SELECT u.archetype, COUNT(*) AS posts
FROM post p JOIN user_mgmt u ON u.id = p.user_id
WHERE p.comment_to = '-1' GROUP BY u.archetype;
```

The [Database schema](../database-schema/) page lists every table.

## Where to next

- [Database schema]({{ site.baseurl }}/database-schema/)
- [Glossary]({{ site.baseurl }}/glossary/)
