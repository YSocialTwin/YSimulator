# Adding Agent Knowledge Graphs for Consistent Behavior

**Guide Version:** 1.0  
**Last Updated:** January 9, 2026  
**Target Use Case:** Individual agent knowledge graphs for consistent, contextualized content generation  

## Table of Contents

1. [Overview](#overview)
2. [Knowledge Graph Specification](#knowledge-graph-specification)
3. [Architecture Design](#architecture-design)
4. [Implementation Pipeline](#implementation-pipeline)
5. [LLM Integration](#llm-integration)
6. [Rule-Based Integration](#rule-based-integration)
7. [Forgetting Mechanisms](#forgetting-mechanisms)
8. [Testing Strategy](#testing-strategy)
9. [Configuration and Deployment](#configuration-and-deployment)
10. [Performance Considerations](#performance-considerations)

---

## Overview

This guide describes how to extend YSimulator to support **individual knowledge graphs (KG)** for each agent. These KGs enable agents to maintain consistent behavior by storing and retrieving concepts, relationships, and discussion topics they encounter during interactions.

### Goals

1. **Contextual Memory:** Agents remember concepts and relationships from past interactions
2. **Consistency:** Agents reference their learned knowledge when creating content
3. **Topic Coherence:** Agents build domain-specific knowledge around discussion topics
4. **Forgetting:** Implement realistic memory decay for older/unused knowledge
5. **Enable/Disable:** Make KG optional and configurable per agent
6. **Dual Support:** Support both LLM-based and rule-based agents

### Key Features

- **Concept Extraction:** Automatically identify key concepts from posts and conversations
- **Relationship Discovery:** Learn connections between concepts through context
- **Topic-Centric:** Organize knowledge around discussion topics
- **Query Interface:** Retrieve relevant knowledge when generating content
- **Memory Decay:** Implement forgetting mechanisms based on time and usage
- **Scalability:** Efficient storage and retrieval for thousands of agents

---

## Knowledge Graph Specification

### KG Data Model

Each agent maintains an individual knowledge graph with the following structure:

```python
AgentKnowledgeGraph:
    agent_id: UUID                    # Owner of this KG
    enabled: bool                     # Whether KG is active
    
    # Core KG Components
    concepts: Dict[str, Concept]      # concept_id -> Concept
    relations: List[Relation]         # Directed edges between concepts
    topics: Dict[str, Topic]          # topic_id -> Topic metadata
    
    # Metadata
    created_at: datetime
    last_updated: datetime
    total_interactions: int           # Number of posts/comments processed
```

#### Concept

```python
Concept:
    id: UUID                          # Unique concept identifier
    name: str                         # Concept label (e.g., "climate change")
    type: str                         # Type: ENTITY, EVENT, IDEA, OPINION
    description: str                  # Short description
    
    # Temporal information
    first_seen: datetime              # When first encountered
    last_accessed: datetime           # Last time referenced
    access_count: int                 # Number of times referenced
    
    # Context
    source_posts: List[UUID]          # Posts where concept appeared
    associated_topics: List[str]      # Topics related to this concept
    
    # Memory strength
    salience: float                   # Importance score (0-1)
    decay_rate: float                 # How fast concept fades (0-1)
```

#### Relation

```python
Relation:
    id: UUID                          # Unique relation identifier
    source_concept_id: UUID           # Source concept
    target_concept_id: UUID           # Target concept
    relation_type: str                # Type: RELATED_TO, CAUSES, OPPOSES, SUPPORTS, etc.
    
    # Strength
    weight: float                     # Connection strength (0-1)
    confidence: float                 # How confident is this relation (0-1)
    
    # Context
    evidence_posts: List[UUID]        # Posts supporting this relation
    co_occurrence_count: int          # How often concepts appear together
    
    # Temporal
    first_observed: datetime
    last_reinforced: datetime
    decay_rate: float
```

#### Topic

```python
Topic:
    id: str                           # Topic identifier (e.g., "politics")
    name: str                         # Human-readable name
    
    # Associated knowledge
    concepts: Set[UUID]               # Concepts related to this topic
    relations: Set[UUID]              # Relations within this topic domain
    
    # Agent's expertise
    expertise_level: float            # How knowledgeable (0-1)
    interaction_count: int            # Posts/comments on this topic
    last_interaction: datetime
```
