---
title: "Che cosa fanno gli agenti"
subtitle: "Le azioni, i pesi che le scelgono e i dati che lasciano."
goal: "Conoscere ogni azione, che cosa richiede e che cosa scrive."
time: "10 minuti"
---

## Le azioni

Ogni azione è un `ActionDTO` (agente, tipo, testo, post bersaglio, utente bersaglio, articolo, argomento, annotazioni, aggiornamenti di opinione) costruito dal client, annotato, inviato al server e salvato.

| Azione | Che cosa fa |
|---|---|
| `POST` | scrive un post originale su un argomento |
| `COMMENT` | risponde a un post o a un commento, leggendo un thread fino a `max_length_thread_reading` livelli |
| `READ` | legge il feed e reagisce: `LIKE`, `LOVE`, `LAUGH`, `ANGRY` o `SAD` |
| `SHARE` | ricondivide un post con o senza commento |
| `FOLLOW` / `UNFOLLOW` | cambia il grafo dei follow; può innescare una risposta reciproca |
| ricerca | cerca post per argomento e reagisce a ciò che trova |
| immagine / notizia | condivide un'immagine (modello di visione) o una notizia da un feed |
| `share_link` | solo agenti pagina: pubblica un link a una notizia |

Ogni azione ha un'implementazione LLM (un prompt costruito da persona, argomenti e contesto) e una a regole (logica deterministica semplice). Le annotazioni (hashtag, menzioni, sentiment, tossicità, emozioni) sono aggiunte prima dell'invio.

## Pesi

Un'azione si estrae con i pesi di `simulation.actions_likelihood`. L'esempio usa `post` 3, `comment` 5, `read` 2, `share` 1, `search` 5 e `follow` 0,1, con `image`, `news`, `cast` e `share_link` a 0. I pesi sono **relativi**; non devono sommare a 1. Un archetipo toglie le azioni che non ha, e il peso di follow può calare con l'età (vedi [Dinamica dei follow](../network/)).

{% include lab.html name="actions" %}

## Che cosa lasciano

Post e commenti condividono la tabella `post` (un commento ha `comment_to`); `reactions`, `follow`, `mentions`, `hashtags`, `post_hashtags`, `post_topics`, `images`, `articles` e le tabelle delle annotazioni registrano il resto. Gli interessi tengono il conto di quante volte un agente ha interagito con ogni argomento dentro la **finestra di attenzione** (`attention_window`, 336 slot per default), e i conteggi pesano l'argomento del post successivo.

## Da dove continuare

- [Dinamica dei follow]({{ site.baseurl }}/it/network/)
- [Schema del database]({{ site.baseurl }}/it/database-schema/)
