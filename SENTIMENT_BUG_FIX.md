# Sentiment Storage Bug Fix

## Issue
The `post_sentiment` table was empty despite no errors being logged during simulation runs.

## Root Cause
The `_process_annotations()` method was being called **before** topics were assigned to posts in the `submit_actions()` method. The order was:

1. Create post in database
2. **Call `_process_annotations()` ← Too early!**
3. Assign topics to the post

Since sentiment entries require `topic_ids` (one sentiment entry per topic), and no topics were assigned yet when annotation processing ran, the sentiment processing logic would:
- Call `get_post_topics(post_id)` → returns empty list
- Skip the sentiment storage loop (no iterations)
- Log nothing about the issue

## Solution
Reordered the operations in `submit_actions()` for POST actions:

1. Create post in database
2. Assign topics to the post (from article or action.topic)
3. **Call `_process_annotations()` ← Now topics are available!**

This ensures that when sentiment processing runs, it can find the topics and create the appropriate sentiment entries.

## Additional Improvements
Added comprehensive logging to help diagnose similar issues in the future:

### Sentiment Logging
- **When processing**: `"Processing sentiment for post {id}: compound=X.XXX"`
- **When no topics found**: `"No topics found for post {id}, skipping sentiment storage. Sentiment data will not be saved."` (WARNING)
- **When using parent topics**: `"Using N topics from parent post {parent_id} for comment {id}"`
- **For each entry**: `"Added sentiment entry for post {id}, topic {topic_id}"` or error message
- **Summary**: `"Successfully added sentiment for post {id} across N topics"`

### Toxicity Logging
- **When processing**: `"Processing toxicity for post {id}: TOXICITY=X.XXX"`
- **After storage**: `"Successfully added toxicity data for post {id}"` or error message

## Testing
The fix maintains backward compatibility and all existing tests pass:
- `test_text_annotations.py` ✅
- `test_db_annotations.py` ✅

## Impact on Comments
Comments are not affected by this issue because:
1. Comments don't get their own topics initially
2. The `_process_annotations()` method retrieves topics from the parent post
3. Parent posts already have topics assigned, so comment sentiment works correctly

## Expected Behavior After Fix
With this fix, when simulation runs:
1. Posts with topics will have sentiment entries in `post_sentiment` table
2. Logs will show sentiment processing with compound scores
3. If a post has no topics, logs will warn about skipping sentiment storage
4. Comments will inherit topics from parent posts and have sentiment entries
