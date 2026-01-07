# Hardcoded Parameters Analysis Report
**Generated**: 2026-01-05  
**Repository**: YSocialTwin/YSimulator

---

## Executive Summary

This report identifies all hardcoded parameter values in the YSimulator codebase and categorizes them based on whether they are configurable via configuration files (`server_config.json`, `simulation_config.json`, `llm_prompts.json`).

**Key Findings:**
- ✅ **Most important parameters ARE configurable** via config files
- ⚠️ **2 issues found** where hardcoded values should use passed parameters
- 📝 **5 parameters** could benefit from being added to config files

---

## 1. Parameters Already Configurable ✅

These parameters have hardcoded defaults but are properly loaded from configuration files when available:

### 1.1 `timeout_seconds`
- **Location**: `YSimulator/YServer/server.py:167`
- **Default**: `60` seconds
- **Config**: `timeout_seconds` in `server_config.json`
- **Status**: ✅ Working correctly

### 1.2 `num_slots_per_day`
- **Location**: `YSimulator/YServer/coordination/round_manager.py:24`
- **Default**: `24`
- **Config**: `simulation.num_slots_per_day` in `simulation_config.json`
- **Status**: ✅ Working correctly

### 1.3 `attention_window`
- **Location**: `YSimulator/YServer/interests_modeling/interest_manager.py:28`
- **Default**: `336` (14 days × 24 slots)
- **Config**: `agents.attention_window` in `simulation_config.json`
- **Status**: ✅ Working correctly

### 1.4 `llm_v.temperature`
- **Location**: `YSimulator/YClient/LLM_interactions/llm_service.py:79`
- **Default**: `0.5`
- **Config**: `llm_v.temperature` in `simulation_config.json`
- **Status**: ✅ Working correctly

### 1.5 `redis.sliding_window_days`
- **Location**: `YSimulator/YServer/classes/db_middleware.py:69, 84`
- **Default**: `2` days
- **Config**: `redis.sliding_window_days` in `server_config.json`
- **Status**: ✅ Working correctly (default on line 69, overridden from config on line 84)

### 1.6 `max_length_thread_reading`
- **Location**: Multiple files (repositories, services)
- **Default**: `5`
- **Config**: `agents.max_length_thread_reading` in `simulation_config.json`
- **Status**: ✅ Partially working (parameter defaults use 5, but can be overridden)

---

## 2. Issues Found ⚠️

### 2.1 ⚠️ `slots_per_day` hardcoded in ContentRecommender
- **Location**: `YSimulator/YServer/recommendation/content_recommender.py:246`
- **Current Code**: `slots_per_day = 24  # Assuming 24 slots per day`
- **Issue**: Hardcoded value duplicates `num_slots_per_day` configuration
- **Impact**: Medium - Could cause inconsistency if `num_slots_per_day` is changed in config
- **Recommendation**: Pass `num_slots_per_day` as parameter to `ContentRecommender.__init__()` and use it instead
- **Fix Required**: Yes

### 2.2 ⚠️ `default_limit` for recommendations
- **Location**: `YSimulator/YServer/recommendation/content_recommender.py:43`
- **Current Code**: `limit: int = 5,`
- **Issue**: Default limit for recommendation results is not configurable
- **Impact**: Low - Works fine, but users might want to customize
- **Recommendation**: Add `recommendations.default_limit` to `simulation_config.json`
- **Fix Required**: Optional (quality of life improvement)

---

## 3. Parameters That Could Be Made Configurable 📝

### 3.1 `batch_size` in agent_manager
- **Location**: `YSimulator/YClient/agent_manager.py:208`
- **Value**: `100`
- **Purpose**: Ray batch processing size for agent operations
- **Impact**: Medium - Affects performance tuning
- **Recommendation**: Add `agents.ray_batch_size` to `simulation_config.json`

### 3.2 `initial_slot` value
- **Location**: `YSimulator/YServer/coordination/round_manager.py:45, 85`
- **Value**: `1`
- **Purpose**: Starting slot number for simulations
- **Impact**: Very Low - Rarely needs to be different
- **Recommendation**: Leave as is (starting at slot 1 is logical)

### 3.3 Query `limit` defaults
- **Locations**: Multiple repository and service files
- **Values**: `10`, `50` (various query limits)
- **Purpose**: Database query result limits
- **Impact**: Low - Reasonable defaults
- **Recommendation**: Consider adding `database.query_limits` if users request it

### 3.4 Thread context defaults
- **Files**: Multiple repository files
- **Value**: `max_length: int = 5`
- **Note**: Already in config as `agents.max_length_thread_reading` but some methods don't use it
- **Impact**: Low
- **Recommendation**: Ensure all methods that need it receive it from config

### 3.5 Recommendation limit in database adapter
- **Location**: `YSimulator/YServer/server.py:1700, 1751, 1787`
- **Values**: `5`, `10` (various recommendation limits)
- **Impact**: Low
- **Recommendation**: Use same `recommendations.default_limit` config value

---

## 4. Hardcoded Values That Are Acceptable ✅

These are application logic constants that typically don't need configuration:

### 4.1 String Constants (OK)
- **Agent types**: `"rule_based"`, `"llm_evaluation"` - Application logic
- **Action types**: `"COMMENT"`, `"POST"`, `"SHARE"`, etc. - Application logic
- **Error messages**: Various error strings - UI/logging text
- **Recommendation modes**: `"rchrono_popularity"`, `"common_interests"` - Algorithm names
- **Status**: ✅ These are code constants, not user-configurable parameters

### 4.2 Default Credentials (OK)
- **Location**: `YSimulator/YClient/classes/ray_models.py:19`
- **Value**: `"default_password"`
- **Note**: Placeholder only, not used for actual authentication
- **Status**: ✅ Acceptable

### 4.3 Emotion List (OK)
- **Location**: `YSimulator/YClient/LLM_interactions/llm_service.py:616`
- **Value**: Long comma-separated list of emotion names
- **Purpose**: Standard emotion set for annotation
- **Status**: ✅ This is a domain constant, not a configuration parameter

---

## 5. Priority Recommendations

### HIGH PRIORITY (Should Fix)
1. ✏️ **Fix `slots_per_day` in ContentRecommender**
   - Add `num_slots_per_day` parameter to `ContentRecommender.__init__()`
   - Pass from server initialization (line 312)
   - Use instead of hardcoded 24

### MEDIUM PRIORITY (Nice to Have)
2. 📝 **Add `batch_size` to configuration**
   - Add `agents.ray_batch_size: 100` to `simulation_config.json`
   - Load in `agent_manager.py`
   - Useful for performance tuning

3. 📝 **Add `default_limit` to configuration**
   - Add `recommendations.default_limit: 5` to `simulation_config.json`
   - Use in ContentRecommender and other recommendation methods
   - Useful for customization

### LOW PRIORITY (Optional)
4. 📝 Consider adding `database.query_limits` if users request it
5. 📝 Ensure all thread context methods use config value consistently

---

## 6. Configuration File Structure

### Current Configuration Files
```
example/
├── [variant]/
│   ├── server_config.json       # Server, database, Redis, logging config
│   ├── simulation_config.json   # Simulation parameters, agents, actions
│   └── llm_prompts.json         # LLM prompt templates
```

### Parameters in Config Files

**server_config.json includes:**
- `timeout_seconds`
- `min_to_start`
- `database.*`
- `redis.*` (including `sliding_window_days`)
- `posts.visibility_rounds`
- `simulation.agent_archetypes.*`
- `logging.*`

**simulation_config.json includes:**
- `simulation.num_slots_per_day`
- `simulation.num_days`
- `simulation.heartbeat_interval`
- `simulation.actions_likelihood.*`
- `agents.attention_window`
- `agents.max_length_thread_reading`
- `agents.reading_from_follower_ratio`
- `agents.probability_of_daily_follow`
- `agents.churn.*`
- `agents.new_agents.*`
- `llm.*` (model, temperature, etc.)
- `llm_v.*`
- `logging.*`

---

## 7. Conclusion

**Overall Assessment**: ✅ Good

The codebase follows good practices with most important parameters being configurable. The main findings are:

1. **✅ 6 major parameters** are properly configurable via config files
2. **⚠️ 1 issue** needs fixing (ContentRecommender slots_per_day)
3. **📝 3 parameters** would benefit from being made configurable
4. **✅ String constants** are appropriately hardcoded as application logic

**Most Critical Action**: Fix the `slots_per_day` hardcoded value in ContentRecommender to use the `num_slots_per_day` parameter that's already available from configuration.

---

## 8. Detailed File Locations

### Files Analyzed
- YSimulator/YServer/server.py
- YSimulator/YServer/coordination/round_manager.py
- YSimulator/YServer/interests_modeling/interest_manager.py
- YSimulator/YServer/classes/db_middleware.py
- YSimulator/YServer/recommendation/content_recommender.py
- YSimulator/YServer/repositories/*.py
- YSimulator/YServer/services/*.py
- YSimulator/YClient/LLM_interactions/llm_service.py
- YSimulator/YClient/agent_manager.py
- YSimulator/YClient/client.py

### Configuration Files Verified
- example/llm_population_100_no_opinion/server_config.json
- example/llm_population_100_no_opinion/simulation_config.json

