# LLM Page News Sharing Implementation

## Overview

This document explains how LLM-powered page agents share news articles with commentary in YSimulator.

## Feature Description

When a page agent (social media page) is configured with LLM capabilities, it can:
1. Fetch news articles from RSS feeds
2. Generate engaging commentary about the articles
3. Share the news with both the commentary and article reference

## Implementation Details

### Flow Diagram

```
Page Agent (is_page=1, agent_type="llm")
  ↓
[activity_selector.py] → Returns "share_link" action
  ↓
[share_link_generator.py] → Calls generate_news_post_async()
  ↓
[llm_actions.py] → Saves article to DB, gets article_id
  ↓
[llm_actions.py] → Generates commentary via @ray.remote function
  ↓
Returns (commentary_future, article_id)
  ↓
Tuple stored: (agent_id, cluster_id, future, article_id)
  ↓
[batch_processor.py] → Gathers futures, extracts article_id
  ↓
Creates ActionDTO with:
  - content: LLM-generated commentary
  - article_id: UUID reference to news article
```

### Key Components

#### 1. Action Selection
**File**: `YSimulator/YClient/activity_selector.py`

```python
if agent_profile.is_page == 1:
    agent_type = determine_agent_type(agent_profile)
    return "share_link", agent_type, None
```

Pages always use the "share_link" action type.

#### 2. LLM News Post Generation
**File**: `YSimulator/YClient/action_generators/share_link_generator.py`

```python
if agent_type == "llm":
    future, article_id = generate_news_post_async(
        self.context.news_service,
        self.context.llm,
        agent.cluster,
        article,
        agent.username,
    )
    result.pending_llm_calls.append((agent.id, agent.cluster, future, article_id))
```

For LLM pages, creates async task and stores the article_id for later processing.

#### 3. Async Commentary Generation
**File**: `YSimulator/YClient/actions/llm_actions.py`

```python
def generate_news_post_async(news_service, llm_service, agent_cluster, article, website_name):
    # Save article to database
    article_id = ray.get(news_service.save_article_to_db.remote(article))
    
    # Generate commentary asynchronously
    commentary_future = generate_llm_news_commentary.remote(
        llm_service, agent_cluster, article, website_name
    )
    
    return commentary_future, article_id
```

Saves the article first to get an ID, then generates commentary asynchronously.

#### 4. Ray Remote Function
**File**: `YSimulator/YClient/actions/llm_actions.py`

```python
@ray.remote
def generate_llm_news_commentary(llm_service, cluster_id, article, website_name):
    commentary = ray.get(llm_service.generate_news_commentary.remote(article, website_name))
    return commentary
```

Ray remote function that calls the LLM service to generate commentary.

#### 5. LLM Service Methods
**Files**: 
- `YSimulator/YClient/LLM_interactions/llm_service.py`
- `YSimulator/YClient/LLM_interactions/vllm_service.py`

Both implement `generate_news_commentary`:
```python
def generate_news_commentary(self, article: dict, website_name: str = None) -> str:
    article_title = article.get("title", "News Article")
    article_text = article.get("summary", article.get("description", ""))
    
    # Use prompt templates to generate engaging commentary
    system_msg = system_template.format(website_name=website_name)
    user_msg = user_template.format(article_title=article_title, article_text=article_text)
    
    # Generate with LLM (max 280 characters)
    commentary = ...
    return commentary
```

Generates engaging social media commentary about the news article.

#### 6. Batch Processing
**File**: `YSimulator/YClient/simulation/batch_processor.py`

```python
# Extract article_id from tuple
topic_or_article = pending_item[3] if len(pending_item) > 3 else None
action = ActionDTO(a_id, cid, "POST", content=res_txt)

# Set article_id if it's a valid UUID
if topic_or_article:
    try:
        uuid.UUID(topic_or_article)
        action.article_id = topic_or_article
    except ValueError:
        action.topic = topic_or_article
```

Gathers the async results and creates ActionDTO with both content and article_id.

## Result

The final action contains:
- **content**: LLM-generated commentary (e.g., "Exciting developments in AI! This article explores...")
- **article_id**: UUID reference to the full article in the database
- **action_type**: "POST"
- **agent_id**: The page's ID

This allows the frontend to:
1. Display the page's commentary
2. Show a link to the full article
3. Track engagement with the shared news

## Comparison: LLM vs Rule-Based Pages

### LLM Pages
- Generate **engaging, contextual commentary** using AI
- Commentary is **unique** for each article
- Can **adapt tone** based on website/page persona
- Asynchronous generation for better performance

### Rule-Based Pages  
- Use simple **templated commentary**
- Faster but less engaging
- No AI required

Both correctly set `article_id` to reference the shared news article.

## Configuration

To enable LLM-powered news sharing for pages:

1. Set page agent configuration:
```json
{
  "username": "NewsPage",
  "is_page": 1,
  "has_llm": true,
  ...
}
```

2. Ensure LLM service is configured in simulation config:
```json
{
  "llm": {
    "provider": "openai",
    "model": "gpt-4",
    ...
  }
}
```

3. Configure RSS feed in news service for the page to fetch articles

## Testing

To verify LLM page news sharing is working:

1. Check logs for: `"LLM Page {username} generating news post async"`
2. Verify article_id is logged: `"LLM Page {username} got article_id: {uuid}"`
3. Check batch processor logs: `"LLM post for agent {id}: article_id={uuid}"`
4. Inspect database for posts with:
   - Non-empty content (the commentary)
   - Valid article_id (UUID format)

## Troubleshooting

### Posts have no content
- Check if LLM service is initialized
- Verify prompt templates exist in config
- Check LLM service logs for errors

### Posts have no article_id
- Verify news service is saving articles correctly
- Check if `save_article_to_db` returns valid UUID
- Ensure batch processor is extracting article_id from tuple

### Commentary is always generic
- Check if LLM service `generate_news_commentary` method is being called
- Verify article data includes title and summary
- Check prompt templates are loaded correctly

## Related Files

- `YSimulator/YClient/activity_selector.py` - Action selection
- `YSimulator/YClient/action_generators/share_link_generator.py` - News sharing logic
- `YSimulator/YClient/actions/llm_actions.py` - Async LLM operations
- `YSimulator/YClient/actions/rule_based_actions.py` - Rule-based alternative
- `YSimulator/YClient/LLM_interactions/llm_service.py` - LLM service (OpenAI/etc)
- `YSimulator/YClient/LLM_interactions/vllm_service.py` - vLLM service
- `YSimulator/YClient/simulation/batch_processor.py` - Async result gathering
