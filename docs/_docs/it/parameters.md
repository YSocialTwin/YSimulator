---
title: "Parametri"
subtitle: "Ogni impostazione di una run, con il suo significato, i suoi valori e il suo valore predefinito."
goal: "Trovare un'impostazione, sapere che cosa fa e quale file la contiene."
time: "riferimento"
tabs: false
---

Una run si configura con due file JSON nella cartella dell'esperimento, più la popolazione.

<div class="ys-cols2">
<div><h3>1 · Server</h3><p><code>server_config.json</code>: nome, client minimi, timeout, database, Redis, archetipi e log.</p></div>
<div><h3>2 · Client</h3><p><code>simulation_config.json</code>: tempo, attività, pesi delle azioni, agenti, abbandono, opinioni, modelli, memoria e log.</p></div>
<div><h3>3 · Popolazione</h3><p><code>agent_population.json</code>: chi sono gli agenti. Vedi <a href="{{ site.baseurl }}/it/agents/">Agenti e archetipi</a>.</p></div>
</div>

Ciò che non è scritto prende il valore predefinito, quindi un file elenca solo ciò che cambi.

<div class="ys-params" data-src="{{ site.baseurl }}/assets/data/parameters.json"><noscript>Abilita JavaScript per sfogliare i parametri, oppure leggi <a href="https://github.com/YSocialTwin/YSimulator/blob/main/docs/configuration/CONFIG.md">docs/configuration/CONFIG.md</a>.</noscript></div>

## Da dove continuare

- [Configurazione]({{ site.baseurl }}/it/configuration/)
- [Schema del database]({{ site.baseurl }}/it/database-schema/)
