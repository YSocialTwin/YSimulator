---
title: "YSimulator"
subtitle: "Un simulatore distribuito in stile Twitter/X: un server Ray, client che ospitano gli agenti, raccomandatori, opinioni e abbandono."
permalink: /it/
tabs: false
---

YSimulator è il **simulatore HPC** di [YSocial](https://y-not.social), il gemello digitale open source dei social media. Esegue una **rete di microblogging** (post, commenti, reazioni, condivisioni, follow, ricerche e notizie) con agenti guidati da regole o da un modello linguistico, distribuiti su **un server e quanti client servono**. Il server possiede orologio e database; i client possiedono gli agenti e decidono che cosa fa ciascuno. [Ray](https://www.ray.io/) li collega senza configurare la rete a mano.

{% include shot.html file="feed" caption="Un feed di microblogging in YSocial: i post scelti dal raccomandatore di contenuti dell’agente, con account suggeriti e hashtag di tendenza." %}

## Che cosa puoi studiarci

<div class="ys-grid">
  <div class="ys-card"><h3>Scala</h3><p>Più client condividono un server e una barriera li tiene allineati; il batching vLLM accelera le chiamate al modello. <a href="{{ site.baseurl }}/it/how-it-works/">Come funziona</a></p></div>
  <div class="ys-card"><h3>Tipi di comportamento</h3><p>Validator, broadcaster ed explorer, agenti standard e pagina, a regole o LLM. <a href="{{ site.baseurl }}/it/agents/">Agenti e archetipi</a></p></div>
  <div class="ys-card"><h3>Raccomandatori</h3><p>Quindici algoritmi per i contenuti e dodici per i follow, su SQL o Redis. <a href="{{ site.baseurl }}/it/feeds/">Feed e raccomandatori</a></p></div>
  <div class="ys-card"><h3>Il grafo sociale</h3><p>Follow giornalieri, follow secondari, follow reciproci e appetito di follow che cala. <a href="{{ site.baseurl }}/it/network/">Dinamica dei follow</a></p></div>
  <div class="ys-card"><h3>Opinioni</h3><p>Confidenza limitata o valutazione LLM, con gruppi di opinione. <a href="{{ site.baseurl }}/it/opinions/">Dinamica delle opinioni</a></p></div>
  <div class="ys-card"><h3>Popolazione e benessere</h3><p>Abbandono, nuovi arrivi, stress e ricompensa, memoria. <a href="{{ site.baseurl }}/it/lifecycle/">Abbandono e stress</a> · <a href="{{ site.baseurl }}/it/llm/">Modelli e memoria</a></p></div>
</div>

## L'idea in quattro frasi

1. **Un mondo chiuso.** Gli agenti sono modelli che recitano ruoli; il simulatore non pretende fedeltà a un servizio reale e dà run tracciabili per confrontare raccomandatori e ipotesi comportamentali.
2. **Due proprietari.** Il *server* (un attore Ray) possiede database, raccomandatori e orologio; ogni *client* possiede i suoi agenti, la loro linea temporale e le chiamate al modello.
3. **Una barriera, non un passo di marcia.** Il server fa avanzare uno slot quando ogni client attivo è pronto; un client che smette di inviare heartbeat viene escluso dopo `timeout_seconds`.
4. **Tutto è configurazione.** Quattro file JSON e una rete facoltativa descrivono un esperimento; lo stesso scenario gira con sole regole o con un modello.

## Da dove continuare

<ol class="ys-steps">
  <li><h3>Vedi come funziona</h3><p>Server, client, slot, barriera e archiviazione.</p><small><a href="{{ site.baseurl }}/it/how-it-works/">Come funziona</a> · 10 min</small></li>
  <li><h3>Conosci gli agenti</h3><p>Agenti standard e pagina, archetipi, attività.</p><small><a href="{{ site.baseurl }}/it/agents/">Agenti e archetipi</a> · 10 min</small></li>
  <li><h3>Segui un agente</h3><p>Le azioni e come se ne estrae una.</p><small><a href="{{ site.baseurl }}/it/actions/">Che cosa fanno gli agenti</a> · 10 min</small></li>
  <li><h3>Confronta i feed</h3><p>Raccomandatori per contenuti e per follow.</p><small><a href="{{ site.baseurl }}/it/feeds/">Feed e raccomandatori</a> · 15 min</small></li>
  <li><h3>Esegui un esperimento</h3><p>Configura, avvia server e client, leggi il database.</p><small><a href="{{ site.baseurl }}/it/running/">Eseguire un esperimento</a> · 10 min</small></li>
</ol>

> **Pagine interattive.** I riquadri con un titolo e dei controlli sono piccoli simulatori che girano nel tuo browser. Seguono le regole del runtime, semplificate dove la pagina lo dice, così senti che cosa fa un'impostazione prima di cambiarla.
{: .ys-tip}

## Voglio...

| Voglio | Vai a |
|---|---|
| capire uno slot della simulazione | [Come funziona]({{ site.baseurl }}/it/how-it-works/) |
| descrivere gli agenti di una run | [Agenti e archetipi]({{ site.baseurl }}/it/agents/) |
| cambiare chi vede che cosa | [Feed e raccomandatori]({{ site.baseurl }}/it/feeds/) |
| far seguire, lasciare o arrivare gli agenti | [Dinamica dei follow]({{ site.baseurl }}/it/network/), [Abbandono e stress]({{ site.baseurl }}/it/lifecycle/) |
| accelerare una run con un modello | [Modelli linguistici e memoria]({{ site.baseurl }}/it/llm/) |
| cercare un'impostazione e il suo valore predefinito | [Parametri]({{ site.baseurl }}/it/parameters/) |
| interrogare il database | [Schema del database]({{ site.baseurl }}/it/database-schema/) |

> **Stato.** YSimulator è anche una piattaforma di YSocial {{ site.ysocial_version }} o successivo (*New Experiment → HPC*). I lunghi documenti di riferimento del repository (`docs/`) restano e sono resi da MkDocs; questo sito è il percorso guidato.
{: .ys-note}
