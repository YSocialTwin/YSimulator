---
title: "Dinamica delle opinioni"
subtitle: "Opinioni in [0, 1] che si attraggono, si polarizzano o sono giudicate da un modello."
goal: "Scegliere un modello di opinione e leggerne i parametri."
time: "10 minuti"
---

## Opinioni e gruppi

Ogni agente tiene un numero in [0, 1] per argomento (0 fortemente contrario, 1 fortemente favorevole). Per la lettura i numeri sono mappati in **gruppi di opinione** (`opinion_groups`: *Strongly against* da 0 a 0,2, *Against*, *Neutral*, *In favor*, *Strongly in favor*). Le opinioni si aggiornano quando un agente commenta o condivide, e un agente che incontra un argomento per la prima volta ne riceve una con `cold_start` (`neutral` oppure `inherited` dall'autore).

## Due modelli

**`bounded_confidence`** vale per ogni agente. Se le opinioni di lettore e autore distano meno di `epsilon`, il lettore si sposta di una frazione `mu` verso l'autore; fuori dalla soglia si allontana con tasso `theta`. **`llm_evaluation`** chiede al modello se è d'accordo con il post, quindi vale solo per gli agenti LLM; con `evaluation_scope` `neighbors` pesa anche le opinioni degli account seguiti dal lettore.

{% include lab.html name="opinions" %}

## Che cosa alimenta

Ogni cambiamento è salvato in `agent_opinion` (argomento, round, interlocutore, post), così puoi ricostruire traiettorie e gruppi. Anche gli agenti pagina hanno opinioni, e le opinioni compaiono nei prompt degli agenti a modello.

## Da dove continuare

- [Abbandono, nuovi agenti e stress]({{ site.baseurl }}/it/lifecycle/)
- [Modelli linguistici e memoria]({{ site.baseurl }}/it/llm/)
