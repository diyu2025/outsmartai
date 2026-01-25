# Quick Start: Testing FormalGeo Grader with Your Image

## Fastest Way to Test (No Setup Required)

Run the simple test that bypasses dataset requirements:

```bash
cd /Users/yud/repo/outsmartai/backend
/Users/yud/repo/FormalGeo/.venv/bin/python tests/test_formalgeo_simple.py
```

This will attempt to find and load the FormalGeo datasets from `/Users/yud/repo/formalgeo7k/projects`.

## If You See "No dataset found"

Download the dataset (one-time setup):

```bash
cd /Users/yud/repo/outsmartai/backend
/Users/yud/repo/FormalGeo/.venv/bin/python tests/download_formalgeo_datasets.py
```

This downloads `formalgeo7k_v1` to `/Users/yud/repo/formalgeo7k/datasets/formalgeo7k_v1`.

Then update `app.py` line 1425 to point to the correct path:
```python
self.formalgeo_datasets_path = "/Users/yud/repo/formalgeo7k/datasets"
```

## Full E2E Test with Your Image

1. **Save your diameter-right angle image**:
   ```bash
   # Save the 3 images you provided to:
   mkdir -p /Users/yud/repo/outsmartai/backend/tests/data
   # Save as diameter_right_angle.png
   ```

2. **Set up LLM credentials**:
   ```bash
   export LLM_PROVIDER=openai
   export LLM_API_KEY=your_openai_api_key
   export RUN_FULL_E2E=1
   ```

3. **Run the full pipeline**:
   ```bash
   cd /Users/yud/repo/outsmartai/backend
   /Users/yud/repo/FormalGeo/.venv/bin/python tests/test_e2e_formalgeo.py
   ```

This will:
- ✅ Analyze image with LLM
- ✅ Extract steps (A1 Agent)
- ✅ Generate claims (A2 Agent)
- ✅ Formalize to CDL/GDL (GeometryFormalizerAgent)
- ✅ **Grade with FormalGeo theorem prover**
- ✅ Calculate rubric scores (A3 Agent)
- ✅ Generate final report

## Expected Output

```
================================================================================
FORMALGEO GRADER TEST: Diameter-Right Angle Problem
================================================================================

Step 1: Loading FormalGeo datasets...
  Found dataset: formalgeo7k in /Users/yud/repo/formalgeo7k/datasets
  ✓ Loaded 169 theorems

Step 2: Initializing FormalGeo grader...
  ✓ Grader initialized

Step 3: Constructing diameter-right angle problem...
  Problem: Prove angle ACB = 90°
  Given: Circle O, diameter AB, point C on circle

Step 4: Student solution steps...
  Step 1: Equal(LengthOfLine(O,A),LengthOfLine(O,C))
  Step 2: Equal(LengthOfLine(O,C),LengthOfLine(O,B))
  ...

Step 5: Grading solution with FormalGeo...

================================================================================
GRADING RESULTS
================================================================================

📊 Score: 80/100
🎯 Goal Reached: false
💯 Confidence: 0.88

📝 Step-by-Step Feedback:
  ✓ Step 1: Valid
  ✓ Step 2: Valid
  ✓ Step 3: Valid
  ...

❌ Deductions (2 total):
  - Step 7: Incorrect theorem application...
    Points: -20 (confidence: 0.92)

📄 Summary:
  Student demonstrated good understanding of isosceles triangle properties...

================================================================================
TEST COMPLETED
================================================================================
```

## Troubleshooting

### "No module named 'formalgeo'"
```bash
cd /Users/yud/repo/FormalGeo
source .venv/bin/activate
pip install -e .
```

### "No dataset named 'formalgeo7k'"
Run the download script:
```bash
/Users/yud/repo/FormalGeo/.venv/bin/python tests/download_formalgeo_datasets.py
```

### "ModuleNotFoundError: No module named 'flask'"
Use the simple test instead:
```bash
/Users/yud/repo/FormalGeo/.venv/bin/python tests/test_formalgeo_simple.py
```

## What's Next?

Once the test passes, you can:

1. **Integrate with your frontend**: The grading API at `/analyze` now returns FormalGeo results
2. **Customize grading criteria**: Modify `calculate_deduction()` in `formalgeo_grader.py`
3. **Add more problems**: The system works with any FormalGeo-compatible geometry problem
4. **Enhance theorem matching**: Improve `fuzzy_match_theorem()` for better informal name mapping

## Files Overview

```
backend/
├── graders/formalgeo_grader.py     # Core grading engine
├── app.py                           # Flask app with integration
├── tests/
│   ├── test_formalgeo_simple.py    # ← START HERE
│   ├── test_e2e_formalgeo.py       # Full pipeline
│   └── download_formalgeo_datasets.py  # Dataset downloader
├── FORMALGEO_INTEGRATION.md        # Detailed integration guide
└── IMPLEMENTATION_SUMMARY.md       # Complete summary
```

## Quick Test Command

```bash
cd /Users/yud/repo/outsmartai/backend && \
/Users/yud/repo/FormalGeo/.venv/bin/python tests/test_formalgeo_simple.py
```

That's it! The FormalGeo grader is ready to verify your geometry solutions with mathematical rigor. 🎓✨
