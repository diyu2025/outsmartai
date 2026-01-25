# ✅ HOW TO RUN E2E TEST - UPDATED

## The Correct Way to Run (Use This!)

```bash
cd /Users/yud/repo/outsmartai/backend

# Set your OpenAI API key
export LLM_PROVIDER=openai
export LLM_API_KEY=sk-your-key

# Run with the wrapper script (automatically uses correct Python)
./run_e2e.sh
```

## ⚠️ IMPORTANT: DO NOT use `python3 run_e2e.py`

The `python3` command uses the system Python which **does not have formalgeo installed**.

You **MUST** use one of these:
1. `./run_e2e.sh` (recommended - wrapper script)
2. `/Users/yud/repo/outsmartai/.venv/bin/python run_e2e.py` (direct)

## What Was Fixed

### Problem
When running with `python3`, you got:
```
🔬 FormalGeo Grading: ❌ NOT USED
[FormalGeoStepGrader] Failed to initialize problem: 'Preset'
```

### Root Causes
1. **Wrong Python**: `python3` → system Python without formalgeo
2. **LLM hallucinating GDL**: Prompt was asking LLM to generate predicate_GDL
3. **Wrong predicate names**: LLM was using `DiameterOfCircle` instead of `IsDiameterOfCircle`
4. **Invalid CDL syntax**: LLM was using arithmetic in predicates like `Equal(A,B+C)`

### Fixes Applied
1. **Created wrapper script** (`run_e2e.sh`): Ensures correct Python is used
2. **Updated LLM prompt**: Explicitly tell LLM NOT to generate GDL, only CDL
3. **Added correct predicate names** to prompt
4. **Added warning about arithmetic**: No `+` in predicates

## Current Status

✅ GDL loading works correctly
✅ Predicate GDL has correct structure: `['Preset', 'Entity', 'Relation', 'Attribution']`
✅ FormalGeo problem initialization works
✅ 105 KB items loaded successfully

⚠️ Still need LLM to generate valid CDL (no arithmetic in predicates)

## Next Test

Run:
```bash
./run_e2e.sh
```

You should see:
```
[FormalGeoStepGrader] Problem loaded successfully
[FormalGeoStepGrader] Initial KB has 105 items
```

If you see an error about arithmetic operators, the LLM is still generating invalid CDL and needs another iteration on the prompt.

## Summary

**Always use `./run_e2e.sh`** - it will:
1. Check that formalgeo is installed
2. Show the FormalGeo version
3. Use the correct Python environment
4. Run the E2E test with proper error handling
