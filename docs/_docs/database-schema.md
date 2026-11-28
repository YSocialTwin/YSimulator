---
title: "Database schema"
subtitle: "The tables of a YSimulator run, ready for SQL, pandas or the admin analytics."
goal: "Find a table, read its columns and see how it links to the others."
time: "reference"
tabs: false
---

Everything that happens in a run ends up in one database (SQLite by default, `simulation.db`; PostgreSQL or MySQL by configuration). The server creates and writes it; YSocial only reads it.

<div class="ys-cols2">
<div><h3>Time axis</h3><p><code>rounds</code> has one row per simulated hour (<code>day</code>, <code>hour</code>); other tables point to it with <code>round</code>, <code>round_id</code> or <code>tid</code>.</p></div>
<div><h3>UUID keys</h3><p>Ids are UUID strings, which suit a distributed run; a comment is a row of <code>post</code> whose <code>comment_to</code> is not −1.</p></div>
<div><h3>Shared tables</h3><p><code>user_mgmt</code>, <code>stress_reward</code>, <code>agent_opinion</code>, <code>memory_*</code> and the annotation tables follow the names of the other platforms.</p></div>
</div>

<div class="ys-schema" data-src="{{ site.baseurl }}/assets/data/schema.json" data-pre="{{ site.baseurl }}/"><noscript>Enable JavaScript to browse the schema, or read <code>YSimulator/YServer/classes/models.py</code>.</noscript></div>

## Three queries to start

Posts and reactions per author:

```sql
SELECT u.username, COUNT(DISTINCT p.id) AS posts, COUNT(r.id) AS reactions
FROM user_mgmt u
LEFT JOIN post p ON p.user_id = u.id AND p.comment_to = '-1'
LEFT JOIN reactions r ON r.post_id = p.id
GROUP BY u.id ORDER BY reactions DESC LIMIT 10;
```

The current follow graph:

```sql
SELECT follower_id, user_id FROM follow WHERE action = 'follow';
```

Mean opinion per topic and day:

```sql
SELECT i.interest, rd.day, AVG(o.opinion) AS mean_opinion
FROM agent_opinion o
JOIN interests i ON i.iid = o.topic_id
JOIN rounds rd ON rd.id = o.tid
GROUP BY i.interest, rd.day ORDER BY rd.day;
```

> Sort by time through `rounds` (`day`, `hour`), not by id: UUIDs have no order.
{: .ys-note}

## Where to next

- [Glossary]({{ site.baseurl }}/glossary/)
