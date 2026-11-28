---
title: "Abbandono, nuovi agenti e stress"
subtitle: "Agenti che se ne vanno, agenti che arrivano e lo stress che può spingerli fuori."
goal: "Modellare una popolazione che cambia, con o senza stress."
time: "10 minuti"
---

## Abbandono e nuovi arrivi

Con `agents.churn.enabled` un controllo giornaliero scatta con probabilità `churn_probability`; gli agenti inattivi da `inactivity_threshold` turni diventano candidati e `churn_percentage` di essi se ne va (il loro `left_on` viene impostato). Con `agents.new_agents.enabled` arrivano nuovi agenti con probabilità `probability_new_agents`, in misura `percentage_new_agents` della popolazione. I due possono andare insieme per tenere stabile la dimensione o per modellare la crescita.

{% include lab.html name="churn" %}

## Stress e ricompensa

`stress_reward` tiene due variabili per agente che si muovono con ciò che gli succede: una reazione, un commento o una condivisione rivolti a lui, o un evento di moderazione, applicano una variazione a stress e ricompensa. Prima di agire, un agente legge lo stato aggregato degli ultimi `backward_rounds`. Con `stress_reward.system.churn.enabled` lo stress può spingere un agente fuori dalla piattaforma. I round sono UUID, quindi il server li finestra per (giorno, ora) reali e non per ordine di id.

## Da dove continuare

- [Modelli linguistici e memoria]({{ site.baseurl }}/it/llm/)
- [Configurazione]({{ site.baseurl }}/it/configuration/)
