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

### Example Knowledge Graph

```
Agent: user_123
Topic: "Climate Science"

Concepts:
  - C1: "global warming" (IDEA, salience=0.9)
  - C2: "fossil fuels" (ENTITY, salience=0.8)
  - C3: "renewable energy" (IDEA, salience=0.7)
  - C4: "carbon emissions" (ENTITY, salience=0.85)

Relations:
  - R1: C2 "causes" C4 (weight=0.9, confidence=0.8)
  - R2: C4 "causes" C1 (weight=0.85, confidence=0.7)
  - R3: C3 "reduces" C4 (weight=0.75, confidence=0.8)
  - R4: C1 "opposes" C3 (weight=0.6, confidence=0.5)

When agent posts about "climate change":
  -> Retrieve C1, C2, C4 (high salience)
  -> Retrieve R1, R2 (strong relations)
  -> Generate content mentioning fossil fuels causing emissions
```

---

## Architecture Design

### Component Overview

```
┌─────────────────────────────────────────────────────────┐
│              YClient (Agent Side)                        │
├─────────────────────────────────────────────────────────┤
│  KnowledgeGraphManager                                   │
│  ├─ AgentKG (per agent)                                 │
│  │  ├─ Concept Storage                                  │
│  │  ├─ Relation Storage                                 │
│  │  └─ Topic Index                                      │
│  │                                                       │
│  ├─ KG Builder                                          │
│  │  ├─ ConceptExtractor (LLM/rule-based)              │
│  │  ├─ RelationIdentifier                              │
│  │  └─ TopicAssociator                                 │
│  │                                                       │
│  ├─ KG Query Engine                                     │
│  │  ├─ Concept Retrieval                               │
│  │  ├─ Relation Traversal                              │
│  │  └─ Context Assembly                                │
│  │                                                       │
│  └─ Forgetting Engine                                   │
│     ├─ Time-based Decay                                │
│     ├─ Access-based Retention                          │
│     └─ Pruning Strategies                              │
│                                                          │
│  Action Generators (Modified)                           │
│  ├─ PostGenerator + KG Context                         │
│  ├─ CommentGenerator + KG Context                      │
│  └─ ShareGenerator + KG Context                        │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│             YServer (Orchestrator)                       │
├─────────────────────────────────────────────────────────┤
│  KnowledgeGraphService                                   │
│  ├─ KG Persistence (SQL + Redis)                       │
│  ├─ Cross-Agent KG Analytics                           │
│  └─ KG Sync/Backup                                     │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│            Data Storage Layer                            │
├─────────────────────────────────────────────────────────┤
│  SQL Tables:                                             │
│  ├─ kg_concepts                                         │
│  ├─ kg_relations                                        │
│  ├─ kg_topics                                           │
│  └─ kg_metadata                                         │
│                                                          │
│  Redis Cache:                                            │
│  ├─ Active KG cache (fast access)                      │
│  ├─ Concept embeddings                                  │
│  └─ Query results cache                                 │
└─────────────────────────────────────────────────────────┘
```

### Data Flow

**Learning Phase (Building KG):**
```
Agent creates post/comment
         ↓
Extract concepts from content (LLM/rules)
         ↓
Identify relations between concepts
         ↓
Associate with current topic
         ↓
Update agent's KG (add/strengthen concepts & relations)
         ↓
Apply decay to old concepts
         ↓
Persist to storage
```

**Generation Phase (Using KG):**
```
Agent needs to create content on topic T
         ↓
Query KG for concepts related to topic T
         ↓
Retrieve high-salience concepts + strong relations
         ↓
Assemble context: concepts, relations, examples
         ↓
Pass context to LLM/rule-based generator
         ↓
Generate content incorporating learned knowledge
```

---

## Implementation Pipeline

### Phase 1: Foundation (Data Layer)

#### Step 1.1: Add Database Schema

**Location:** `scripts/migrations/add_knowledge_graphs.sql`

```sql
-- Agent knowledge graphs metadata
CREATE TABLE kg_metadata (
    agent_id UUID PRIMARY KEY,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL,
    last_updated TIMESTAMP NOT NULL,
    total_interactions INTEGER DEFAULT 0,
    total_concepts INTEGER DEFAULT 0,
    total_relations INTEGER DEFAULT 0,
    FOREIGN KEY (agent_id) REFERENCES user_mgmt(id)
);

-- Concepts in knowledge graphs
CREATE TABLE kg_concepts (
    id UUID PRIMARY KEY,
    agent_id UUID NOT NULL,
    name VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL,  -- ENTITY, EVENT, IDEA, OPINION
    description TEXT,
    
    -- Temporal
    first_seen TIMESTAMP NOT NULL,
    last_accessed TIMESTAMP NOT NULL,
    access_count INTEGER DEFAULT 0,
    
    -- Memory strength
    salience FLOAT DEFAULT 0.5,  -- 0-1
    decay_rate FLOAT DEFAULT 0.1,  -- 0-1
    
    -- Context
    source_posts JSONB,  -- Array of post UUIDs
    associated_topics JSONB,  -- Array of topic names
    
    FOREIGN KEY (agent_id) REFERENCES user_mgmt(id),
    UNIQUE(agent_id, name)  -- Prevent duplicate concepts per agent
);

-- Relations between concepts
CREATE TABLE kg_relations (
    id UUID PRIMARY KEY,
    agent_id UUID NOT NULL,
    source_concept_id UUID NOT NULL,
    target_concept_id UUID NOT NULL,
    relation_type VARCHAR(50) NOT NULL,  -- RELATED_TO, CAUSES, OPPOSES, etc.
    
    -- Strength
    weight FLOAT DEFAULT 0.5,  -- 0-1
    confidence FLOAT DEFAULT 0.5,  -- 0-1
    
    -- Context
    evidence_posts JSONB,  -- Array of post UUIDs
    co_occurrence_count INTEGER DEFAULT 1,
    
    -- Temporal
    first_observed TIMESTAMP NOT NULL,
    last_reinforced TIMESTAMP NOT NULL,
    decay_rate FLOAT DEFAULT 0.1,
    
    FOREIGN KEY (agent_id) REFERENCES user_mgmt(id),
    FOREIGN KEY (source_concept_id) REFERENCES kg_concepts(id) ON DELETE CASCADE,
    FOREIGN KEY (target_concept_id) REFERENCES kg_concepts(id) ON DELETE CASCADE,
    UNIQUE(agent_id, source_concept_id, target_concept_id, relation_type)
);

-- Topic knowledge tracking
CREATE TABLE kg_topics (
    id UUID PRIMARY KEY,
    agent_id UUID NOT NULL,
    topic_name VARCHAR(255) NOT NULL,
    
    -- Agent expertise
    expertise_level FLOAT DEFAULT 0.1,  -- 0-1
    interaction_count INTEGER DEFAULT 0,
    last_interaction TIMESTAMP,
    
    -- Associated knowledge
    concept_ids JSONB,  -- Array of concept UUIDs
    relation_ids JSONB,  -- Array of relation UUIDs
    
    FOREIGN KEY (agent_id) REFERENCES user_mgmt(id),
    UNIQUE(agent_id, topic_name)
);

-- Indexes for performance
CREATE INDEX idx_kg_concepts_agent ON kg_concepts(agent_id);
CREATE INDEX idx_kg_concepts_salience ON kg_concepts(agent_id, salience DESC);
CREATE INDEX idx_kg_concepts_topic ON kg_concepts USING GIN(associated_topics);

CREATE INDEX idx_kg_relations_agent ON kg_relations(agent_id);
CREATE INDEX idx_kg_relations_source ON kg_relations(source_concept_id);
CREATE INDEX idx_kg_relations_target ON kg_relations(target_concept_id);
CREATE INDEX idx_kg_relations_weight ON kg_relations(agent_id, weight DESC);

CREATE INDEX idx_kg_topics_agent ON kg_topics(agent_id);
CREATE INDEX idx_kg_topics_name ON kg_topics(agent_id, topic_name);
```

**Redis Keys:**

```python
# Active KG cache (hot data)
"ysim:kg:{agent_id}:concepts" -> Hash of concept_id -> concept data
"ysim:kg:{agent_id}:relations" -> Hash of relation_id -> relation data
"ysim:kg:{agent_id}:topics:{topic_name}" -> Set of concept IDs

# Query cache
"ysim:kg:{agent_id}:query:{topic}:concepts" -> Cached concept list (TTL: 5min)
"ysim:kg:{agent_id}:query:{topic}:relations" -> Cached relation list (TTL: 5min)

# Concept embeddings (for similarity search)
"ysim:kg:embeddings:{concept_id}" -> Float array (embedding vector)

# Metadata
"ysim:kg:{agent_id}:enabled" -> Boolean
"ysim:kg:{agent_id}:stats" -> Hash (total_concepts, total_relations, etc.)
```


#### Step 1.2: Add Repository and Service Layer

**Location:** `YSimulator/YServer/repositories/knowledge_graph_repository.py`

```python
class KnowledgeGraphRepository(BaseRepository):
    """Repository for knowledge graph data access."""
    
    def __init__(self, db_engine, redis_client=None, logger=None):
        self.db_engine = db_engine
        self.redis_client = redis_client
        self.logger = logger or logging.getLogger(__name__)
    
    # Concept operations
    def add_concept(self, agent_id: str, concept: dict) -> bool:
        """Add or update concept in agent's KG."""
        pass
    
    def get_concepts_by_topic(self, agent_id: str, topic: str, 
                             limit: int = 10) -> List[dict]:
        """Get top concepts for agent related to topic."""
        pass
    
    def get_concept_by_name(self, agent_id: str, name: str) -> Optional[dict]:
        """Get specific concept by name."""
        pass
    
    def update_concept_access(self, concept_id: str):
        """Update last_accessed and increment access_count."""
        pass
    
    # Relation operations
    def add_relation(self, agent_id: str, relation: dict) -> bool:
        """Add or strengthen relation in agent's KG."""
        pass
    
    def get_relations_for_concepts(self, agent_id: str, 
                                   concept_ids: List[str]) -> List[dict]:
        """Get relations connecting given concepts."""
        pass
    
    # Topic operations
    def update_topic_expertise(self, agent_id: str, topic: str, 
                               increment: float = 0.01):
        """Increase agent's expertise in topic."""
        pass
    
    def get_topic_knowledge(self, agent_id: str, topic: str) -> dict:
        """Get all knowledge (concepts + relations) for topic."""
        pass
    
    # Maintenance
    def apply_decay(self, agent_id: str, decay_factor: float = 0.95):
        """Apply time-based decay to all concepts/relations."""
        pass
    
    def prune_weak_knowledge(self, agent_id: str, threshold: float = 0.1):
        """Remove concepts/relations below salience threshold."""
        pass
```

**Location:** `YSimulator/YServer/services/knowledge_graph_service.py`

```python
class KnowledgeGraphService:
    """
    Business logic for knowledge graph operations.
    Coordinates between repository and higher-level operations.
    """
    
    def __init__(self, kg_repo, post_service, logger=None):
        self.kg_repo = kg_repo
        self.post_service = post_service
        self.logger = logger
    
    def learn_from_post(self, agent_id: str, post_content: str, 
                       topic: str, post_id: str):
        """
        Extract knowledge from post and update agent's KG.
        
        Steps:
        1. Extract concepts from content
        2. Identify relations between concepts
        3. Associate with topic
        4. Update KG
        """
        pass
    
    def learn_from_interaction(self, agent_id: str, target_post_id: str, 
                              interaction_type: str):
        """
        Learn from reading/reacting to others' posts.
        Lighter learning than creating own content.
        """
        pass
    
    def get_knowledge_context(self, agent_id: str, topic: str, 
                             max_concepts: int = 5) -> dict:
        """
        Retrieve relevant knowledge for content generation.
        
        Returns:
            {
                "concepts": [...],  # Top concepts for topic
                "relations": [...],  # Relations between concepts
                "examples": [...],  # Past posts on this topic
                "expertise": 0.7    # Agent's expertise level
            }
        """
        pass
```

---

## LLM Integration

### Step 2.1: LLM-Based Concept Extraction

**Location:** `YSimulator/YClient/knowledge_graph/extractors/llm_extractor.py`

```python
class LLMConceptExtractor:
    """
    Extract concepts and relations from text using LLM.
    High quality but more expensive.
    """
    
    def __init__(self, llm_service, logger=None):
        self.llm_service = llm_service
        self.logger = logger
    
    def extract_concepts(self, text: str, topic: str) -> List[dict]:
        """
        Extract key concepts from text.
        
        Args:
            text: Content to analyze
            topic: Current discussion topic
        
        Returns:
            List of concepts with name, type, description, salience
        """
        prompt = f"""
        Extract key concepts from this text about {topic}.
        
        Text: "{text}"
        
        For each concept, provide:
        1. Name (2-4 words)
        2. Type (ENTITY, EVENT, IDEA, or OPINION)
        3. Brief description (one sentence)
        4. Salience (0-1, how important is this concept)
        
        Return as JSON array.
        """
        
        response = self.llm_service.generate(prompt)
        concepts = self._parse_llm_response(response)
        
        return concepts
    
    def extract_relations(self, text: str, concepts: List[dict]) -> List[dict]:
        """
        Identify relations between extracted concepts.
        
        Returns:
            List of relations with source, target, type, confidence, weight
        """
        concept_names = [c["name"] for c in concepts]
        
        prompt = f"""
        Given these concepts: {concept_names}
        
        From the text: "{text}"
        
        Identify relationships between concepts.
        Relation types: CAUSES, SUPPORTS, OPPOSES, RELATED_TO, PART_OF
        
        For each relation:
        1. Source concept
        2. Target concept  
        3. Relation type
        4. Confidence (0-1)
        5. Strength/weight (0-1)
        
        Return as JSON array.
        """
        
        response = self.llm_service.generate(prompt)
        relations = self._parse_llm_response(response)
        
        return relations
```

---

## Rule-Based Integration

### Step 3.1: Simplified Concept Extraction

**Location:** `YSimulator/YClient/knowledge_graph/extractors/rule_extractor.py`

```python
class RuleBasedConceptExtractor:
    """
    Extract concepts using NLP rules and heuristics.
    Faster and cheaper than LLM, but lower quality.
    """
    
    def __init__(self, logger=None):
        self.logger = logger
        
        # Simple NLP tools (spaCy, NLTK, or custom)
        try:
            import spacy
            self.nlp = spacy.load("en_core_web_sm")
        except:
            self.nlp = None
            self.logger.warning("spaCy not available, using basic extraction")
    
    def extract_concepts(self, text: str, topic: str) -> List[dict]:
        """
        Extract concepts using NLP rules.
        
        Strategy:
        1. Extract named entities (PERSON, ORG, GPE, etc.)
        2. Extract noun phrases
        3. Filter by relevance to topic
        4. Assign salience based on frequency/position
        """
        concepts = []
        
        if self.nlp:
            # Use spaCy for better extraction
            doc = self.nlp(text)
            
            # Named entities
            for ent in doc.ents:
                concepts.append({
                    "name": ent.text,
                    "type": self._map_entity_type(ent.label_),
                    "description": f"{ent.label_}: {ent.text}",
                    "salience": 0.7  # Default salience
                })
            
            # Noun chunks
            for chunk in doc.noun_chunks:
                if len(chunk.text.split()) >= 2:  # Multi-word concepts
                    concepts.append({
                        "name": chunk.text.lower(),
                        "type": "IDEA",
                        "description": f"Concept from text: {chunk.text}",
                        "salience": 0.5
                    })
        else:
            # Fallback: simple keyword extraction
            concepts = self._extract_keywords(text, topic)
        
        # Deduplicate and adjust salience
        concepts = self._deduplicate_concepts(concepts)
        
        return concepts[:10]  # Limit to top 10
    
    def extract_relations(self, text: str, concepts: List[dict]) -> List[dict]:
        """
        Extract relations using simple co-occurrence.
        
        Strategy:
        - Concepts in same sentence are RELATED_TO
        - Use pattern matching for causal language
        """
        relations = []
        concept_names = [c["name"] for c in concepts]
        
        # Check co-occurrence in sentences
        sentences = text.split('. ')
        
        for sent in sentences:
            sent_lower = sent.lower()
            present_concepts = [name for name in concept_names 
                               if name.lower() in sent_lower]
            
            # Create RELATED_TO relations for co-occurring concepts
            for i, source in enumerate(present_concepts):
                for target in present_concepts[i+1:]:
                    relations.append({
                        "source": source,
                        "target": target,
                        "type": "RELATED_TO",
                        "confidence": 0.6,
                        "weight": 0.5
                    })
        
        return relations
```

---

## Forgetting Mechanisms

### Step 4.1: Time-Based Decay

**Location:** `YSimulator/YClient/knowledge_graph/forgetting_engine.py`

```python
class ForgettingEngine:
    """
    Implement forgetting mechanisms for knowledge graphs.
    Simulates realistic memory decay and consolidation.
    """
    
    def __init__(self, kg_service, config: dict, logger=None):
        self.kg_service = kg_service
        self.config = config
        self.logger = logger
        
        # Decay parameters
        self.time_decay_rate = config.get("time_decay_rate", 0.05)  # Per day
        self.access_boost = config.get("access_boost", 0.1)  # Per access
        self.prune_threshold = config.get("prune_threshold", 0.1)  # Min salience
    
    def apply_time_decay(self, agent_id: str, days_elapsed: int = 1):
        """
        Apply time-based decay to all knowledge.
        
        Decay formula:
        new_salience = old_salience * (1 - decay_rate) ^ days_elapsed
        """
        decay_factor = (1 - self.time_decay_rate) ** days_elapsed
        
        self.kg_service.apply_decay(agent_id, decay_factor)
        
        self.logger.debug(
            f"Applied time decay to agent {agent_id}: factor={decay_factor:.3f}"
        )
    
    def consolidate_memory(self, agent_id: str):
        """
        Consolidate memory: boost frequently accessed concepts,
        weaken rarely used ones.
        """
        concepts = self.kg_service.get_all_concepts(agent_id)
        
        for concept in concepts:
            access_count = concept["access_count"]
            days_since_access = (datetime.now() - concept["last_accessed"]).days
            
            if days_since_access == 0 and access_count > 5:
                # Frequently accessed today -> boost
                new_salience = min(concept["salience"] + self.access_boost, 1.0)
                self.kg_service.update_concept_salience(
                    concept["id"], new_salience
                )
    
    def prune_weak_knowledge(self, agent_id: str):
        """
        Remove concepts and relations below salience threshold.
        """
        self.kg_service.prune_weak_knowledge(agent_id, self.prune_threshold)
    
    def periodic_maintenance(self, agent_id: str):
        """
        Run all forgetting mechanisms.
        Call this once per simulation day.
        """
        self.apply_time_decay(agent_id, days_elapsed=1)
        self.consolidate_memory(agent_id)
        
        # Prune every 7 days
        if self._should_prune(agent_id):
            self.prune_weak_knowledge(agent_id)
```


---

## Testing Strategy

### Unit Tests

```python
# tests/test_knowledge_graph.py

def test_concept_extraction_llm():
    """Test LLM-based concept extraction."""
    extractor = LLMConceptExtractor(mock_llm_service)
    
    text = "Climate change is caused by fossil fuels releasing carbon emissions."
    topic = "environment"
    
    concepts = extractor.extract_concepts(text, topic)
    
    assert len(concepts) > 0
    assert any(c["name"] == "climate change" for c in concepts)
    assert all(c["type"] in ["ENTITY", "EVENT", "IDEA", "OPINION"] for c in concepts)


def test_concept_extraction_rules():
    """Test rule-based concept extraction."""
    extractor = RuleBasedConceptExtractor()
    
    text = "Climate change is caused by fossil fuels."
    concepts = extractor.extract_concepts(text, "environment")
    
    assert len(concepts) > 0
    assert any("climate" in c["name"].lower() for c in concepts)


def test_time_decay():
    """Test time-based forgetting."""
    forgetting_engine = ForgettingEngine(mock_kg_service, config={})
    
    agent_id = "agent_001"
    concept = {"id": "c1", "salience": 0.8}
    mock_kg_service.add_concept(agent_id, concept)
    
    # Apply decay
    forgetting_engine.apply_time_decay(agent_id, days_elapsed=10)
    
    # Check reduced salience
    updated = mock_kg_service.get_concept_by_id("c1")
    assert updated["salience"] < 0.8


def test_access_boost():
    """Test that accessing concepts boosts salience."""
    kg_service = KnowledgeGraphService(mock_repo)
    
    concept_id = "c1"
    initial_salience = 0.5
    
    # Access multiple times
    for _ in range(5):
        kg_service.access_concept(concept_id)
    
    concept = mock_repo.get_concept_by_id(concept_id)
    assert concept["salience"] > initial_salience
```

---

## Configuration and Deployment

### Agent Configuration

**Location:** Update `agent_population.json` schema

```json
{
  "agents": [
    {
      "id": "agent_001",
      "username": "alice",
      
      "knowledge_graph": {
        "enabled": true,           // Enable/disable KG for this agent
        "implementation": "llm",   // "llm" or "rule_based"
        
        "extraction_config": {
          "max_concepts_per_post": 5,
          "min_concept_salience": 0.3,
          "extract_on_read": true,   // Learn from reading others' posts
          "extract_on_write": true   // Learn from own posts
        },
        
        "retrieval_config": {
          "max_concepts_for_context": 5,
          "min_salience_for_retrieval": 0.4,
          "include_relations": true,
          "cache_ttl_seconds": 300
        },
        
        "forgetting_config": {
          "enabled": true,
          "time_decay_rate": 0.05,    // 5% decay per day
          "access_boost": 0.1,         // 10% boost per access
          "prune_threshold": 0.1,      // Remove if salience < 0.1
          "maintenance_frequency": "daily"
        }
      }
    }
  ]
}
```

### Global Configuration

**Location:** `config/knowledge_graph_config.json`

```json
{
  "knowledge_graph": {
    "global_enabled": true,
    
    "storage": {
      "backend": "postgres",
      "use_redis_cache": true,
      "cache_ttl_seconds": 300
    },
    
    "extraction": {
      "llm": {
        "model": "gpt-3.5-turbo",
        "max_tokens": 500,
        "temperature": 0.3,
        "batch_size": 10
      },
      "rule_based": {
        "use_spacy": true,
        "spacy_model": "en_core_web_sm",
        "min_concept_length": 2,
        "max_concepts_per_post": 10
      }
    },
    
    "forgetting": {
      "time_decay_rate": 0.05,
      "access_boost": 0.1,
      "prune_threshold": 0.1,
      "maintenance_interval_hours": 24
    },
    
    "performance": {
      "max_concepts_per_agent": 500,
      "max_relations_per_agent": 1000,
      "query_cache_size": 1000,
      "embedding_cache_size": 5000
    }
  }
}
```

---

## Performance Considerations

### Optimization Strategies

1. **Caching:**
```python
# Cache KG queries in Redis
"ysim:kg:{agent_id}:query:{topic}:concepts" -> TTL: 5 minutes
```

2. **Lazy Loading:**
```python
# Only load KG when needed
def get_kg_if_enabled(agent_id):
    if cache.get(f"kg:{agent_id}:enabled"):
        return load_kg(agent_id)
    return None
```

3. **Batch Processing:**
```python
# Extract concepts from multiple posts in one LLM call
def batch_extract_concepts(posts: List[str]) -> List[List[dict]]:
    # Process all at once
    pass
```

4. **Pruning:**
```python
# Regular cleanup to keep KG manageable
def periodic_cleanup():
    for agent in active_agents:
        if kg_size(agent.id) > MAX_CONCEPTS:
            prune_weak_knowledge(agent.id)
```

### Scalability Limits

**Per Agent:**
- Max concepts: 500
- Max relations: 1000
- Max query cache: 100 entries

**System-Wide:**
- Total agents with KG: 10,000+
- Redis memory: ~10MB per agent (5GB for 500 agents)
- Query latency: <50ms (cached), <200ms (uncached)

---

## Integration with Action Generators

### Modified Post Generator

**Location:** Modify `YSimulator/YClient/action_generators/post_generator.py`

```python
class PostGenerator(BaseGenerator):
    
    def __init__(self, server, config, kg_query_engine=None):
        super().__init__(server, config)
        self.kg_query_engine = kg_query_engine
    
    def generate(self, agent_data: dict, context: dict) -> Optional[ActionDTO]:
        """Generate post action with KG context."""
        
        agent_id = agent_data["id"]
        topic = self._select_topic(agent_data)
        
        # Get KG context if enabled
        kg_context = None
        if self.kg_query_engine and self._is_kg_enabled(agent_id):
            kg_context = self.kg_query_engine.get_context_for_topic(
                agent_id, topic
            )
        
        # Generate content based on implementation type
        if agent_data.get("implementation") == "llm":
            content = self._generate_llm_post(
                agent_data, topic, kg_context
            )
        else:
            content = self._generate_rule_post(
                agent_data, topic, kg_context
            )
        
        # Learn from own post
        if kg_context and content:
            self._update_kg(agent_id, content, topic)
        
        return ActionDTO(
            agent_id=agent_id,
            action_type="POST",
            content=content,
            topic=topic
        )
    
    def _generate_llm_post(self, agent_data: dict, topic: str, 
                          kg_context: dict) -> str:
        """Generate post using LLM with KG context."""
        
        base_prompt = f"Write a post about {topic}."
        
        # Add KG context if available
        if kg_context and kg_context["concepts"]:
            kg_prompt = f"""
            You have knowledge about this topic:
            {kg_context['narrative']}
            
            Key concepts you know: {', '.join(c['name'] for c in kg_context['concepts'])}
            
            Your expertise level: {kg_context['expertise_level']:.2f}
            
            Reference your knowledge naturally in your post.
            """
            base_prompt = kg_prompt + "\n\n" + base_prompt
        
        response = self.llm_service.generate(base_prompt, agent_data)
        return response
    
    def _generate_rule_post(self, agent_data: dict, topic: str, 
                           kg_context: dict) -> str:
        """Generate post using rules with KG context."""
        
        if kg_context and kg_context["concepts"]:
            # Use learned concepts in post
            concept_names = [c["name"] for c in kg_context["concepts"][:2]]
            
            if concept_names:
                template = random.choice([
                    f"I think {concept_names[0]} is important for {topic}.",
                    f"Regarding {topic}, {concept_names[0]} matters.",
                    f"Let's discuss {concept_names[0]} in the context of {topic}."
                ])
                return template
        
        # Fallback to simple post
        return f"Here are my thoughts on {topic}."
```

---

## Summary Checklist

### YServer Changes
- [ ] Add database tables (kg_concepts, kg_relations, kg_topics, kg_metadata)
- [ ] Create KnowledgeGraphRepository
- [ ] Create KnowledgeGraphService
- [ ] Add Redis caching for KG queries
- [ ] Implement KG maintenance endpoints

### YClient Changes
- [ ] Create LLMConceptExtractor
- [ ] Create RuleBasedConceptExtractor
- [ ] Create KGQueryEngine
- [ ] Create ForgettingEngine
- [ ] Modify PostGenerator to use KG
- [ ] Modify CommentGenerator to use KG
- [ ] Add KG initialization in SimulationClient
- [ ] Add periodic KG maintenance task

### Configuration
- [ ] Add KG config to agent profiles
- [ ] Create global KG configuration file
- [ ] Add enable/disable flags
- [ ] Configure decay and retention parameters

### Testing
- [ ] Unit tests for concept extraction (LLM & rules)
- [ ] Unit tests for relation identification
- [ ] Unit tests for KG queries
- [ ] Unit tests for forgetting mechanisms
- [ ] Integration tests for learning workflow
- [ ] Integration tests for generation with KG
- [ ] Performance tests for query latency

---

## Next Steps

1. **Start with Data Layer:** Implement database schema and repository
2. **Build Extractors:** Start with rule-based, then add LLM
3. **Implement Query Engine:** Make KG retrievable
4. **Integrate with Generators:** Connect KG to content creation
5. **Add Forgetting:** Implement decay mechanisms
6. **Test Thoroughly:** Ensure consistency and performance
7. **Optimize:** Profile and improve query performance

---

**Document Version:** 1.0  
**Author:** YSimulator Development Team  
**Date:** January 9, 2026  
**Related Documentation:**
- [ADDING_MODERATOR_AGENT_GUIDE.md](ADDING_MODERATOR_AGENT_GUIDE.md) - Agent extension example
- [EXTENDING.md](EXTENDING.md) - General extension guide
- [AGENT_TYPES.md](../agents/AGENT_TYPES.md) - Agent architecture
