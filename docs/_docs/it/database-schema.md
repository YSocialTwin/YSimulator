---
title: "Schema del database"
subtitle: "Le tabelle di una run di YSimulator, pronte per SQL, pandas o le analisi dell'admin."
goal: "Trovare una tabella, leggerne le colonne e vedere come si collega alle altre."
time: "riferimento"
tabs: false
---

Tutto ciò che accade in una run finisce in un solo database (SQLite per default, `simulation.db`; PostgreSQL o MySQL per configurazione). Lo crea e lo scrive il server; YSocial lo legge soltanto.

<div class="ys-cols2">
<div><h3>Asse del tempo</h3><p><code>rounds</code> ha una riga per ora simulata (<code>day</code>, <code>hour</code>); le altre tabelle puntano a essa con <code>round</code>, <code>round_id</code> o <code>tid</code>.</p></div>
<div><h3>Chiavi UUID</h3><p>Gli id sono stringhe UUID, adatte a una run distribuita; un commento è una riga di <code>post</code> con <code>comment_to</code> diverso da −1.</p></div>
<div><h3>Tabelle condivise</h3><p><code>user_mgmt</code>, <code>stress_reward</code>, <code>agent_opinion</code>, <code>memory_*</code> e le tabelle delle annotazioni seguono i nomi delle altre piattaforme.</p></div>
</div>

<div class="ys-schema" data-src="{{ site.baseurl }}/assets/data/schema.json" data-pre="{{ site.baseurl }}/it/"><noscript>Abilita JavaScript per sfogliare lo schema, oppure leggi <code>YSimulator/YServer/classes/models.py</code>.</noscript></div>

## Tre query per cominciare

Post e reazioni per autore:

```sql
SELECT u.username, COUNT(DISTINCT p.id) AS posts, COUNT(r.id) AS reactions
FROM user_mgmt u
LEFT JOIN post p ON p.user_id = u.id AND p.comment_to = '-1'
LEFT JOIN reactions r ON r.post_id = p.id
GROUP BY u.id ORDER BY reactions DESC LIMIT 10;
```

Il grafo dei follow attuale:

```sql
SELECT follower_id, user_id FROM follow WHERE action = 'follow';
```

Opinione media per argomento e giorno:

```sql
SELECT i.interest, rd.day, AVG(o.opinion) AS mean_opinion
FROM agent_opinion o
JOIN interests i ON i.iid = o.topic_id
JOIN rounds rd ON rd.id = o.tid
GROUP BY i.interest, rd.day ORDER BY rd.day;
```

> Ordina nel tempo con `rounds` (`day`, `hour`), non con l'id: gli UUID non hanno un ordine.
{: .ys-note}

## Da dove continuare

- [Glossario]({{ site.baseurl }}/it/glossary/)
