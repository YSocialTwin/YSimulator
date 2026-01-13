# Core Features Documentation

This directory contains documentation for YSimulator's core features and systems.

## Files

- **[RECOMMENDATION_SYSTEMS.md](RECOMMENDATION_SYSTEMS.md)** - Content & follow recommendations (1,200+ lines)
  - 10 content recommendation strategies
  - 5 follow recommendation algorithms
  - Performance benchmarks
  - Configuration options

- **[OPINION_DYNAMICS.md](OPINION_DYNAMICS.md)** - Opinion modeling (1,200+ lines)
  - Bounded confidence model
  - LLM opinion evaluation
  - Opinion groups and polarization
  - Configuration and examples

- **[OPINION_DYNAMICS_ARCHITECTURE.md](OPINION_DYNAMICS_ARCHITECTURE.md)** - Adding new opinion models (guide)
  - Two-layer architecture
  - Model development guide
  - Complete implementation examples

- **[INTERESTS.md](INTERESTS.md)** - Interest management (340+ lines)
  - Attention windows
  - Sliding window mechanism
  - Topic extraction
  - Interest tracking and evolution

- **[ANNOTATION_IMPLEMENTATION.md](ANNOTATION_IMPLEMENTATION.md)** - Emotion annotations (220+ lines)
  - GoEmotions taxonomy
  - 28 emotion categories
  - Sentiment analysis
  - Implementation details

### vLLM Backend & Performance

- **[VLLM_INTEGRATION_GUIDE](../configuration/VLLM_INTEGRATION_GUIDE.md)** - vLLM setup and configuration (450+ lines)
  - Quick start guide for vLLM backend
  - Configuration options comparison (vLLM vs Ollama)
  - Performance benchmarks (8x-30x speedup)
  - Troubleshooting and best practices

- **[VLLM_BATCH_INFERENCE.md](VLLM_BATCH_INFERENCE.md)** - Batch inference implementation (500+ lines)
  - Comprehensive batch processing architecture
  - Batching coverage for all LLM operations
  - Performance optimization details (10x-50x speedup)
  - Implementation guide and testing

- **[VLLM_INTEGRATION_SUMMARY.md](VLLM_INTEGRATION_SUMMARY.md)** - Implementation summary (500+ lines)
  - Phase 1 & 2 implementation overview
  - Technical design and architecture
  - Performance benchmarks and results
  - Complete test coverage report

- **[VLLM_FINAL_REPORT.md](VLLM_FINAL_REPORT.md)** - Complete implementation report (315+ lines)
  - Dual-model support (text + vision)
  - Configuration schema and examples
  - Performance impact analysis
  - Deployment guide and requirements

## Quick Links

- [Back to Documentation Index](../getting-started/INDEX.md)
- [Configuration Guide](../configuration/CONFIG.md)
- [Architecture Overview](../architecture/ARCHITECTURE.md)
