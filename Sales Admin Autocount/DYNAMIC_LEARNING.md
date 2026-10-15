# Dynamic Learning System Documentation

## Overview

The system now includes a dynamic learning capability that automatically improves routing and trigger detection based on user interactions.

## Components

### 1. Database Tables

#### `MessageRoutingLog`
Logs all routing decisions for learning and analysis:
- `message`: The user's message (max 2000 chars)
- `detected_agent`: Which agent was selected
- `confidence`: Routing confidence score (0-1)
- `method`: "keyword" or "llm_classify"
- `user_feedback`: "correct", "incorrect", or None (for future feedback UI)
- `created_at`: Timestamp

#### `LearnedTriggerKeyword`
Stores dynamically learned keywords:
- `keyword`: The learned keyword
- `agent_type`: Which agent/trigger type this keyword belongs to
- `confidence`: Confidence score (0-1)
- `usage_count`: How many times this keyword was used
- `success_count`: How many times it led to correct routing
- `created_at`: When first learned
- `last_used_at`: When last used
- `active`: Whether this keyword is currently active

### 2. DynamicRouter Class (`dynamic_router.py`)

Handles intelligent routing between agents with learning capabilities:

**Features:**
- **Base keywords**: Hardcoded defaults for each agent
- **Learned keywords**: Automatically learned from user interactions
- **Keyword matching**: Scores each agent based on keyword matches
- **LLM fallback**: Uses LLM classification when no keywords match
- **Confidence scoring**: Normalizes scores to 0-1 range
- **Caching**: 5-minute cache for learned keywords

**Methods:**
- `detect_agent(message, method)`: Detects which agent should handle the message
- `log_routing_decision()`: Logs routing decisions for learning
- `record_user_feedback()`: Records user feedback (future feature)
- `learn_new_keyword()`: Extracts and learns new keywords from messages

### 3. Updated TriggerDetector (`trigger.py`)

Enhanced with dynamic learning for general trigger detection:

**New Features:**
- Accepts database session parameter
- Fetches learned trigger keywords from database
- Filters out common words
- `learn_new_trigger_keyword()`: Learns new trigger keywords from successful interactions

**Usage:**
```python
trigger_detector = TriggerDetector(glossary_manager, db)
trigger_type = trigger_detector.detect(message)
```

## How It Works

### Routing Flow

1. **Message received** from Telegram
2. **DynamicRouter** checks for keyword matches:
   - First checks base keywords (hardcoded)
   - Then checks learned keywords (from database)
   - Scores each agent based on match count
3. **If keywords match**: Routes to highest-scoring agent
4. **If no keywords match**: Uses LLM classification
5. **Logs decision** to `MessageRoutingLog` table
6. **Learns keywords** from the message for future use

### Learning Process

1. **Keyword extraction**: Extracts words from message
2. **Filtering**: Removes common words (the, a, is, etc.) and short words (<3 chars)
3. **Database check**: Checks if keyword already exists
4. **Confidence update**:
   - New keywords: Start with 0.8 confidence
   - Existing keywords: Increase confidence by 0.05 (max 1.0)
   - Track usage and success counts
5. **Cache refresh**: Clears keyword cache to force reload

### Confidence Thresholds

- **0.7+**: Keywords actively used in routing
- **Below 0.7**: Learned but not yet trusted enough
- **1.0**: Maximum confidence (well-verified keywords)

## Configuration

### Router Method Options

- `keyword`: Only use keyword matching (no LLM fallback)
- `llm_classify`: Always use LLM classification
- `hybrid`: Use keywords first, LLM fallback (default)

### Example Usage

```python
from dynamic_router import DynamicRouter

router = DynamicRouter(db)

# Detect agent with hybrid method
agent_type, confidence, method = router.detect_agent(
    "Tell me about ABC Trading",
    method="hybrid"
)

# Log the decision
router.log_routing_decision(
    message="Tell me about ABC Trading",
    detected_agent="order_invoice",
    confidence=0.9,
    method="keyword"
)

# Learn from successful interaction
router.learn_new_keyword(
    message="Tell me about ABC Trading",
    correct_agent="order_invoice",
    confidence=0.8
)
```

## Database Migration

The new tables will be created automatically when the database is initialized:

```bash
python setup_test_deployment.py --init-only
```

Or simply restart the application - the tables will be created on startup.

## Monitoring and Analytics

### View Routing Logs

```sql
SELECT 
    detected_agent,
    COUNT(*) as count,
    AVG(confidence) as avg_confidence,
    method
FROM message_routing_log
WHERE created_at > datetime('now', '-7 days')
GROUP BY detected_agent, method
ORDER BY count DESC;
```

### View Learned Keywords

```sql
SELECT 
    agent_type,
    keyword,
    confidence,
    usage_count,
    success_count,
    last_used_at
FROM learned_trigger_keywords
WHERE active = 1
ORDER BY confidence DESC, usage_count DESC;
```

### Identify Low-Confidence Routes

```sql
SELECT 
    message,
    detected_agent,
    confidence,
    method
FROM message_routing_log
WHERE confidence < 0.6
ORDER BY created_at DESC
LIMIT 20;
```

## Future Enhancements

1. **User feedback UI**: Allow users to correct routing decisions
2. **Confidence decay**: Gradually reduce confidence for unused keywords
3. **Keyword grouping**: Learn phrases, not just single words
4. **Context-aware learning**: Consider conversation context
5. **A/B testing**: Compare keyword vs LLM routing performance
6. **Dashboard**: Visual analytics for routing accuracy

## Benefits

✅ **Self-improving**: System gets smarter with use
✅ **No manual updates**: Keywords learned automatically
✅ **Adaptable**: Adjusts to user behavior patterns
✅ **Fallback safe**: LLM ensures reasonable routing even without keywords
✅ **Trackable**: All decisions logged for analysis
✅ **Configurable**: Can adjust thresholds and methods

## Troubleshooting

### Routing Not Learning

1. Check database connection
2. Verify `MessageRoutingLog` table exists
3. Check logs for database errors
4. Ensure confidence threshold (0.7) is appropriate

### Too Many False Positives

1. Increase confidence threshold in `dynamic_router.py`
2. Add more words to `COMMON_WORDS` set
3. Adjust keyword matching logic
4. Review learned keywords and deactivate low-quality ones

### Keywords Not Being Learned

1. Check if message contains common words (filtered out)
2. Verify word length >= 3 characters
3. Check database table exists and is accessible
4. Review logs for extraction errors
