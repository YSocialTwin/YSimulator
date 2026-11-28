---
title: "Modelli linguistici e memoria"
subtitle: "Ollama o vLLM, batching, un modello di visione, annotazioni e memoria degli agenti."
goal: "Scegliere un backend di modello e sapere che cosa costa ogni livello facoltativo."
time: "10 minuti"
---

## I backend

`llm` configura il modello di testo e `llm_v` un modello di visione facoltativo (senza, le azioni con immagini sono saltate). `llm.backend` è `ollama` (il percorso remoto; può passare a un adattatore a batch) oppure `vllm` (un motore locale incorporato). Per un backend remoto `api_format` è `auto`, `openai` o `ollama`, e `batching_policy` è `auto` (prova e fa batching se possibile), `off` oppure `force` (fallisce all'avvio se il batching non funziona).

## Batching

Con un backend capace di batch il client raggruppa le chiamate di uno slot invece di farle una alla volta: post, commenti, risposte, condivisioni, reazioni di lettura, ricerche, estrazione di emozioni e valutazione di opinioni. Il repository riporta accelerazioni da uno a due ordini di grandezza sul percorso vLLM, a seconda del carico; il percorso Ollama non cambia.

## Annotazioni

Il testo può essere annotato per hashtag, menzioni, sentiment (VADER), tossicità ed emozioni (`simulation.emotion_annotation`, una chiamata al modello per testo). Riempiono `post_hashtags`, `mentions`, `post_sentiment`, `post_toxicity`, `emotions` e `post_emotions`.

## Memoria

Con `agents.memory_enabled` ogni agente LLM tiene una memoria legata alla run: eventi, schede dei thread, schede sociali (affinità, conflitto, umorismo, fiducia), riflessioni e un digest della comunità, recuperati con ricerca semantica (`memory_embedding_model`, per default `embeddinggemma`) e inseriti nei prompt di post, risposte, condivisioni e navigazione. Vive interamente nel client: il server non chiama mai la memoria né il modello di embedding. Gli agenti a regole non ne hanno.

> Memoria e annotazione delle emozioni aggiungono chiamate al modello e prompt più lunghi; per un primo esperimento spegnile e confronta.
{: .ys-tip}

## Da dove continuare

- [Configurazione]({{ site.baseurl }}/it/configuration/)
- [Eseguire un esperimento]({{ site.baseurl }}/it/running/)
