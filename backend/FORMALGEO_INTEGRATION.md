# FormalGeo End-to-End Integration Guide

## Overview

This guide explains how the FormalGeo step-by-step grader is integrated into the complete multi-agent grading pipeline in `backend/app.py`.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Student Submission                            │
│              (Image with problem + handwritten solution)            │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    PHASE 1: Image Analysis (LLM)                     │
│                                                                      │
│  LLMService.analyze_image()                                         │
│  ├─ Extracts text description                                       │
│  ├─ Extracts drawing description                                    │
│  ├─ Identifies steps in solution                                    │
│  └─ Returns structured analysis                                     │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│              PHASE 2: Step Extraction (A1 Agent)                     │
│                                                                      │
│  StepExtractorAgent.run()                                           │
│  ├─ Parses solution text into granular steps                        │
│  ├─ Normalizes mathematical notation                                │
│  ├─ Tokenizes expressions                                           │
│  └─ Returns: List[Step] with step_id, raw_text, tokens              │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│              PHASE 3: Claim Generation (A2 Agent)                    │
│                                                                      │
│  ClaimGeneratorAgent.run()                                          │
│  ├─ Converts steps to atomic claims                                 │
│  ├─ Identifies dependencies between claims                          │
│  ├─ Maps to predicate types (RADIUS_EQUAL, etc.)                    │
│  └─ Returns: {givens, student_diagram_claims, claims}               │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│            PHASE 4: Formalization (GeometryFormalizerAgent)          │
│                                                                      │
│  GeometryFormalizerAgent.run()                                      │
│  ├─ Converts claims to CDL (Condition Description Language)         │
│  ├─ Loads FormalGeo predicate_GDL & theorem_GDL                     │
│  ├─ Constructs problem_CDL from construction + text + claims        │
│  └─ Returns: GDL payload with all formal representations            │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│         PHASE 5: Verification (MathVerifier + FormalGeo)             │
│                                                                      │
│  MathVerifier.verify_all()                                          │
│  │                                                                   │
│  ├─ IF use_step_grading=True AND FormalGeo available:               │
│  │   │                                                               │
│  │   └─► FormalGeoStepGrader.grade_geometry_solution()              │
│  │       ├─ initialize_problem(problem_CDL)                          │
│  │       │   └─ Loads problem into FormalGeo Interactor             │
│  │       │                                                           │
│  │       ├─ FOR EACH student step:                                  │
│  │       │   ├─ verify_single_step()                                │
│  │       │   │   ├─ Check dependencies valid                        │
│  │       │   │   ├─ Parse claim to (predicate, item)                │
│  │       │   │   ├─ Check if already in KB (redundant)              │
│  │       │   │   ├─ verify_theorem_application()                    │
│  │       │   │   │   ├─ fuzzy_match_theorem()                       │
│  │       │   │   │   ├─ snapshot_solver_state()                     │
│  │       │   │   │   ├─ solver.apply_theorem()                      │
│  │       │   │   │   ├─ check_conclusion_exists()                   │
│  │       │   │   │   └─ restore if failed                           │
│  │       │   │   └─ calculate_deduction() if invalid                │
│  │       │   │                                                       │
│  │       │   └─ IF valid: update KB                                 │
│  │       │       IF invalid: mark error, DON'T update KB            │
│  │       │                                                           │
│  │       ├─ identify_missing_steps()                                │
│  │       │   └─ Check if goal reached                               │
│  │       │                                                           │
│  │       └─ Returns: GradingReport                                  │
│  │           ├─ total_points: int (0-100)                            │
│  │           ├─ deductions: List[Deduction]                          │
│  │           ├─ step_feedback: List[StepFeedback]                    │
│  │           ├─ missing_steps: List[MissingStep]                     │
│  │           ├─ goal_reached: bool                                   │
│  │           └─ confidence: float                                    │
│  │                                                                   │
│  └─ ELSE: Fall back to claim-by-claim verification                  │
│       └─ Uses FormalGeoVerifier.verify() per claim                  │
│                                                                      │
│  Returns: List[VerificationResult]                                  │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│              PHASE 6: Rubric Scoring (A3 Agent)                      │
│                                                                      │
│  RubricScorerAgent.run()                                            │
│  ├─ Maps verification results to rubric items                       │
│  ├─ Calculates earned points per rubric item                        │
│  └─ Returns: (scores, total, maximum)                               │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                PHASE 7: Referee (A4 Agent)                           │
│                                                                      │
│  RefereeAgent.run()                                                 │
│  ├─ Checks for unknown claims                                       │
│  ├─ Identifies disagreements                                        │
│  └─ Returns: referee notes                                          │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        FINAL GRADING REPORT                          │
│                                                                      │
│  GradingPipeline.grade() returns:                                   │
│  {                                                                   │
│    "problem_id": str,                                               │
│    "steps": List[Step],                                             │
│    "claims": List[Claim],                                           │
│    "verification_results": List[VerificationResult],                │
│    "rubric_scores": List[RubricScore],                              │
│    "score_total": int,                                              │
│    "score_max": int,                                                │
│    "referee": dict,                                                 │
│    "formalgeo_used": bool,                  ← NEW                   │
│    "formalgeo_grading": GradingReport       ← NEW (if available)    │
│  }                                                                   │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Integration Points

### 1. GeometryFormalizerAgent Enhancement

**Location**: `backend/app.py` lines 1423-1509

**Changes**:
- Loads FormalGeo datasets on initialization
- Provides `predicate_GDL` and `theorem_GDL` to pipeline
- Falls back to minimal GDL if datasets unavailable

```python
def __init__(self, llm_service):
    self.formalgeo_datasets_path = "/Users/yud/repo/formalgeo7k/projects/formalgeo7k"
    
    # Try to load FormalGeo datasets
    try:
        from formalgeo.data import DatasetLoader
        dl = DatasetLoader(
            dataset_name="formalgeo7k",
            datasets_path=self.formalgeo_datasets_path
        )
        self.predicate_gdl = dl.predicate_GDL
        self.theorem_gdl = dl.theorem_GDL
    except Exception as e:
        # Fall back to minimal GDL
        self.predicate_gdl = None
        self.theorem_gdl = None
```

### 2. MathVerifier Integration

**Location**: `backend/app.py` lines 421-637

**Changes**:
- Imports `FormalGeoStepGrader`
- Adds `use_step_grading` parameter to `verify_all()`
- Implements `_grade_with_formalgeo()` method
- Stores FormalGeo report for later retrieval
- Converts between grading formats

```python
async def verify_all(self, ..., use_step_grading: bool = True):
    # Formalize with GeometryFormalizerAgent
    gdl_payload = await self.geo.formalize(...)
    
    # Try FormalGeo step grading
    if use_step_grading and self.step_grading_available and gdl_payload:
        step_grading_result = await self._grade_with_formalgeo(
            gdl_payload, claims, givens, student_diagram_claims
        )
        
        if step_grading_result:
            return self._convert_step_grading_to_verification(...)
    
    # Fall back to claim-by-claim verification
    ...
```

### 3. GradingPipeline Enhancement

**Location**: `backend/app.py` lines 866-924

**Changes**:
- Adds `use_formalgeo` parameter
- Checks if FormalGeo was used
- Includes FormalGeo report in final result

```python
async def grade(self, ..., use_formalgeo: bool = True):
    verification_results = await self.math_verifier.verify_all(
        ...,
        use_step_grading=use_formalgeo
    )
    
    # Check if FormalGeo was used
    formalgeo_used = any(
        r.reason_code == "FORMALGEO_VERIFIED" 
        for r in verification_results
    )
    
    result = {
        ...
        "formalgeo_used": formalgeo_used,
        "formalgeo_grading": formalgeo_report  # Detailed report
    }
```

## Testing

### Test Files Created

1. **`tests/test_formalgeo_grader.py`** - Unit tests for FormalGeoStepGrader
   - Tests dataset loading
   - Tests grader initialization
   - Tests problem loading
   - Tests step verification
   - Tests theorem matching
   - Tests full grading

2. **`tests/test_e2e_formalgeo.py`** - End-to-end integration test
   - Full pipeline test with image
   - FormalGeo integration test (direct)
   - Requires LLM API key for full test

3. **`tests/test_formalgeo_simple.py`** - Simple standalone test
   - No Flask dependencies
   - Tests diameter-right angle problem
   - Can run with just FormalGeo installed

4. **`tests/download_formalgeo_datasets.py`** - Dataset download utility

### Running Tests

#### Option 1: Unit Test (No datasets required)
```bash
cd /Users/yud/repo/outsmartai/backend
python tests/test_formalgeo_simple.py
```

#### Option 2: Download datasets first
```bash
cd /Users/yud/repo/outsmartai/backend
/Users/yud/repo/FormalGeo/.venv/bin/python tests/download_formalgeo_datasets.py
```

Then run:
```bash
/Users/yud/repo/FormalGeo/.venv/bin/python tests/test_formalgeo_simple.py
```

#### Option 3: Full E2E test (requires LLM API)
```bash
export RUN_FULL_E2E=1
export LLM_PROVIDER=openai
export LLM_API_KEY=your_key

/Users/yud/repo/FormalGeo/.venv/bin/python tests/test_e2e_formalgeo.py
```

## Using with the Example Problem

To test with the diameter-right angle problem from your image:

1. **Save the image**:
   ```bash
   # Save your image to:
   /Users/yud/repo/outsmartai/backend/tests/data/diameter_right_angle.png
   ```

2. **Set up environment**:
   ```bash
   export LLM_PROVIDER=openai
   export LLM_API_KEY=your_openai_key
   ```

3. **Run the full pipeline**:
   ```bash
   cd /Users/yud/repo/outsmartai/backend
   python -c "
   import asyncio
   import base64
   from pathlib import Path
   from app import GradingPipeline, LLMService
   
   async def test():
       image_bytes = Path('tests/data/diameter_right_angle.png').read_bytes()
       llm = LLMService()
       pipeline = GradingPipeline(llm)
       
       analysis = await llm.analyze_image(image_bytes)
       result = await pipeline.grade(
           problem_id='diameter_right_angle',
           text_description=analysis['text_description'],
           drawing_description=analysis['drawing_description'],
           image_data=image_bytes
       )
       
       print(f'Score: {result[\"score_total\"]}/{result[\"score_max\"]}')
       print(f'FormalGeo used: {result[\"formalgeo_used\"]}')
   
   asyncio.run(test())
   "
   ```

## Expected Output Format

When FormalGeo grading is enabled, the output includes:

```json
{
  "problem_id": "diameter_right_angle",
  "steps": [...],
  "claims": [...],
  "verification_results": [
    {
      "claim_id": "S1C1",
      "verdict": "true",
      "reason_code": "FORMALGEO_VERIFIED",
      "proof_trace": ["circle_property_radius_equal"],
      "evidence_strength": "strong"
    }
  ],
  "rubric_scores": [...],
  "score_total": 85,
  "score_max": 100,
  "formalgeo_used": true,
  "formalgeo_grading": {
    "total_points": 80,
    "deductions": [
      {
        "deducted_points": 20,
        "deduction_reason": "Step 7: Incorrect conclusion...",
        "deduction_step": "step 7",
        "formalgeo_evidence": {...}
      }
    ],
    "step_feedback": [
      {
        "step_id": 1,
        "is_valid": true,
        "theorem_applied": "circle_property_radius_equal",
        "confidence": 0.95
      }
    ],
    "missing_steps": [],
    "goal_reached": false,
    "confidence": 0.88,
    "summary": "Student demonstrated good understanding..."
  }
}
```

## Configuration

### Dataset Path

Update the dataset path in `backend/app.py` line 1425:

```python
self.formalgeo_datasets_path = "/path/to/your/formalgeo7k/datasets"
```

### Enable/Disable FormalGeo

Control FormalGeo usage in the grading request:

```python
# Enable FormalGeo grading
result = await pipeline.grade(..., use_formalgeo=True)

# Disable (use LLM-based verification only)
result = await pipeline.grade(..., use_formalgeo=False)
```

## Troubleshooting

### Dataset Not Found

**Error**: `No dataset named 'formalgeo7k'`

**Solution**:
1. Download the dataset:
   ```python
   from formalgeo.data import download_dataset
   download_dataset("formalgeo7k_v1", "/path/to/datasets")
   ```

2. Update path in `app.py`

### FormalGeo Not Available

**Error**: `FormalGeo not available: No module named 'formalgeo'`

**Solution**:
```bash
pip install formalgeo
```

Or use FormalGeo's virtual environment:
```bash
/Users/yud/repo/FormalGeo/.venv/bin/python your_script.py
```

### Flask Import Error in Tests

**Error**: `ModuleNotFoundError: No module named 'flask'`

**Solution**: Use the simple test that doesn't require Flask:
```bash
python tests/test_formalgeo_simple.py
```

## Summary

The FormalGeo grader is now fully integrated into the multi-agent pipeline:

✅ GeometryFormalizerAgent loads FormalGeo datasets  
✅ MathVerifier uses step-by-step grading when available  
✅ GradingPipeline includes FormalGeo reports  
✅ Graceful fallback to LLM-based verification  
✅ Comprehensive test suite created  
✅ Documentation and examples provided  

The system provides rigorous, theorem-based verification of student geometry solutions with detailed step-by-step feedback and point deductions following your GRADING PROCEDURE.
