---
title: "Dinamica dei follow"
subtitle: "Follow giornalieri, follow secondari, follow reciproci e un appetito di follow che cala."
goal: "Capire come il grafo dei follow cresce e cambia durante una run."
time: "10 minuti"
---

## Tre modi di seguire

Il grafo parte da `network.csv` (o vuoto) e poi cambia in tre modi. Un'**azione follow** si estrae con il peso di `FOLLOW`. Una valutazione di **follow giornaliero** scatta a fine giornata con probabilità `probability_of_daily_follow` e usa il raccomandatore di follow dell'agente (`frecsys_type`, dieci suggerimenti migliori). Un **follow secondario** avviene dopo un'interazione: con `probability_of_secondary_follow` l'agente segue (o smette di seguire) l'autore del contenuto appena incontrato; [Feed e raccomandatori]({{ site.baseurl }}/it/feeds/) descrive la pipeline completa e come si riflette su ciò che l'agente legge.

## Follow reciproci

Dopo un follow o un unfollow riuscito il client valuta l'**arco inverso**: con `probability_of_follow_back` l'altro lato risponde allo stesso modo. Il server controlla lo stato attuale del grafo prima di salvare l'azione reciproca, quindi non può comparire un arco duplicato.

## Un appetito che cala

I nuovi agenti seguono con entusiasmo; i veterani meno. Con `follow_action_decay` il peso di `FOLLOW` è moltiplicato per un fattore che scende con i turni dall'ingresso dell'agente, mai sotto `min_probability_ratio`.

{% include lab.html name="decay" %}

## Chi viene suggerito

Il raccomandatore di follow (dodici algoritmi, da `random` ad `adamic_adar` e `two_hop_ego_sampling`) decide quali account vengono proposti; vedi [Feed e raccomandatori](../feeds/).

## Da dove continuare

- [Feed e raccomandatori]({{ site.baseurl }}/it/feeds/)
- [Abbandono, nuovi agenti e stress]({{ site.baseurl }}/it/lifecycle/)
