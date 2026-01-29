# Fix for SQLite Datatype Mismatch Error

## Problem Statement

The application was failing with the following error:
```
RuntimeError: Failed to get or create round for day=1, hour=1: (sqlite3.IntegrityError) datatype mismatch
[SQL: INSERT INTO rounds (id, day, hour) VALUES (?, ?, ?)]
[parameters: ('dc66cffe-0373-4676-a010-8b2943cd710b', 1, 1)]
```

## Root Cause Analysis

The error was caused by a fundamental mismatch between two schema definitions:

### PostgreSQL Schema (`scripts/postgresql_server.sql`)
- Used `SERIAL PRIMARY KEY` for ID fields
- SERIAL creates an INTEGER auto-increment column
- All foreign key references used INTEGER

### SQLAlchemy Models (`YServer/classes/models.py`)
- Used `Column(String(36), primary_key=True)` for ID fields
- Designed for UUID-based distributed system compatibility
- All foreign key references used String(36)

### Code Implementation
- Generated UUID strings like `'dc66cffe-0373-4676-a010-8b2943cd710b'`
- Expected to store these in the `id` field

### Why It Failed

1. **SQLite with SQLAlchemy**: When using SQLite, tables are created using `Base.metadata.create_all(engine)`, which uses the SQLAlchemy model definitions. This creates tables with VARCHAR(36) ID columns.

2. **PostgreSQL with SQL file**: When using PostgreSQL with the `postgresql_server.sql` schema file, tables are created with INTEGER ID columns.

3. **Type Mismatch**: The Python code tries to insert UUID strings into INTEGER columns, causing the datatype mismatch error.

## Solution

Updated `scripts/postgresql_server.sql` to use `VARCHAR(36)` for all ID fields to match the SQLAlchemy models. This ensures consistency whether tables are created via SQLAlchemy (SQLite) or SQL script (PostgreSQL).

### Changes Made

1. **All Primary Keys**: Changed from `SERIAL PRIMARY KEY` to `VARCHAR(36) PRIMARY KEY`
   - emotions.id
   - hashtags.id
   - interests.iid
   - rounds.id
   - user_mgmt.id
   - follow.id
   - recommendations.id
   - user_interest.id
   - voting.vid
   - websites.id
   - articles.id
   - article_topics.id
   - images.id
   - post.id
   - mentions.id
   - post_emotions.id
   - post_hashtags.id
   - post_sentiment.id
   - post_topics.id
   - post_toxicity.id
   - reactions.id

2. **All Foreign Keys**: Updated to reference `VARCHAR(36)` instead of `INTEGER`

3. **Special Cases**:
   - Added explicit `UNIQUE` constraint to rounds table: `CONSTRAINT uq_round_day_hour UNIQUE (day, hour)`
   - Updated timestamp-like fields that were actually storing round IDs: `last_fetched`, `fetched_on`, `joined_on`, `left_on`
   - Removed problematic default values like `DEFAULT '-1'` from foreign key fields and made them nullable instead

## Testing

Created `test_rounds_fix.py` which verifies:

1. ✅ Rounds can be created with UUID string IDs in SQLite
2. ✅ Unique constraints are properly enforced on (day, hour)
3. ✅ The `get_or_create_round()` method works correctly
4. ✅ Multiple rounds can be created with different day/hour combinations
5. ✅ Attempting to create duplicate rounds (same day/hour) is properly rejected

All tests pass successfully.

## Impact

### Benefits
- Consistent schema across SQLite and PostgreSQL deployments
- Proper UUID-based distributed system support
- No more datatype mismatch errors

### Compatibility Notes
- **New databases**: Will work correctly with UUID-based IDs
- **Existing PostgreSQL databases**: Will need migration to convert INTEGER IDs to VARCHAR(36) UUIDs
- **Existing SQLite databases**: Already using VARCHAR(36) from SQLAlchemy models, no migration needed

## Migration Path for Existing Databases

If you have an existing PostgreSQL database using the old INTEGER-based schema, you'll need to:

1. Backup your database
2. Create migration scripts to:
   - Generate UUID values for existing integer IDs
   - Update all foreign key references
   - Alter column types from INTEGER to VARCHAR(36)
3. Test thoroughly before deploying

Note: This is a significant schema change that requires careful planning for production systems.
