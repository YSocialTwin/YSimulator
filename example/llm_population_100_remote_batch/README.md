# LLM Population Example with Remote Batch Adapter (100 Agents)

This example demonstrates YSimulator running on the non-`vllm` path while automatically upgrading to the new remote batched adapter when the configured LLM server supports batch requests.

## Overview

- **Population**: 100 LLM-enabled agents plus 1 news page
- **Backend requested in config**: `ollama`
- **Batching mode**: `batching_policy = "auto"`
- **Upgrade target**: `RemoteBatchLLMService`
- **Text model**: `llama3.2`
- **Vision model**: `minicpm-v`
- **Duration**: 3 days

## How it works

At client startup:

1. YSimulator uses the standard non-`vllm` configuration.
2. It sends a short batch probe to the configured remote endpoint.
3. If the endpoint accepts the batch request, the client uses the remote batched adapter.
4. If the endpoint does not support batching, the client falls back to the standard `LLMService`.

This keeps the deployment remote and GPU ownership external to YSimulator, while still enabling the same batch-capable actor behavior used by `VLLMService`.

## Key configuration

From [simulation_config.json](/Users/rossetti/PycharmProjects/YSimulator/example/llm_population_100_remote_batch/simulation_config.json):

```json
{
  "llm": {
    "backend": "ollama",
    "address": "localhost",
    "port": 11434,
    "model": "llama3.2",
    "batching_policy": "auto"
  }
}
```

### Batching policy options

- `auto`: probe and upgrade to the remote batched adapter if supported
- `off`: always use the standard `LLMService`
- `force`: fail startup if the endpoint does not support batching

## Usage

### 1. Start the server

```bash
python run_server.py --config example/llm_population_100_remote_batch
```

### 2. Start the client

```bash
python run_client.py --config example/llm_population_100_remote_batch
```

## Expected runtime behavior

If the endpoint supports batching, the client log should contain a line like:

```text
Upgraded non-vLLM backend to batch-capable service backend: remote_batch
```

If the endpoint does not support batching, the simulation still runs using the standard non-batched `LLMService` path.

## Notes

- This example reuses the same 100-agent population assets as `example/llm_population_100`.
- It does **not** start an embedded local vLLM engine.
- It is suitable when batching is provided by the remote model server rather than by an in-process vLLM instance.
