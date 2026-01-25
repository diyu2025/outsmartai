# How to Run E2E Test with Your Diameter-Right Angle Image

## Quick Start (3 Commands)

```bash
# 1. Go to backend directory
cd /Users/yud/repo/outsmartai/backend

# 2. Set your OpenAI API key (or use mock)
export LLM_PROVIDER=openai
export LLM_API_KEY=your_openai_api_key

# 3. Run the test
./run_e2e_test.sh
```

That's it! The test will run the complete pipeline and show detailed results.

---

## What the Test Does

The E2E test runs your **complete 7-phase grading pipeline**:

```
Image → [LLM Analysis] → [A1 Steps] → [A2 Claims] → [Formalization] 
     → [FormalGeo Grading] → [A3 Rubric] → [A4 Referee] → Final Score
```

### Detailed Pipeline:

1. **LLM Image Analysis**: Extracts problem text and solution steps from image
2. **StepExtractorAgent (A1)**: Parses solution into granular steps
3. **ClaimGeneratorAgent (A2)**: Converts steps to atomic mathematical claims
4. **GeometryFormalizerAgent**: Formalizes to CDL/GDL format
5. **FormalGeoStepGrader**: Verifies each step with theorem prover ⭐ **NEW**
6. **RubricScorerAgent (A3)**: Calculates score based on rubric
7. **RefereeAgent (A4)**: Handles disagreements/unknowns

---

## Running Options

### Option 1: Using the Shell Script (Easiest)

```bash
cd /Users/yud/repo/outsmartai/backend

# With your OpenAI API key
export LLM_PROVIDER=openai
export LLM_API_KEY=sk-...
./run_e2e_test.sh

# Test specific image
./run_e2e_test.sh tests/data/CorrectSolution1.png

# With mock LLM (no API needed, but won't grade accurately)
./run_e2e_test.sh
```

### Option 2: Direct Python (More Control)

```bash
cd /Users/yud/repo/outsmartai/backend

# Set environment
export LLM_PROVIDER=openai
export LLM_API_KEY=sk-...

# Run with FormalGeo's Python
/Users/yud/repo/FormalGeo/.venv/bin/python tests/test_e2e_diameter.py \
  --image tests/data/CorrectSolution2.png \
  --provider openai \
  --api-key $LLM_API_KEY
```

### Option 3: Via Flask API

```bash
# Start the Flask server
cd /Users/yud/repo/outsmartai/backend
export LLM_PROVIDER=openai
export LLM_API_KEY=sk-...
python app.py

# In another terminal, send request
curl -X POST http://localhost:5000/analyze \
  -H "Content-Type: application/json" \
  -d "{\"image\": \"$(base64 -i tests/data/CorrectSolution2.png)\"}"
```

---

## Understanding the Output

### Expected Output Structure

```
================================================================================
END-TO-END TEST: Diameter-Right Angle Problem with FormalGeo
================================================================================

📷 Loading image: CorrectSolution2.png
   Size: 77,735 bytes

🔧 Configuration:
   LLM Provider: openai
   API Key: ✓ Set

--------------------------------------------------------------------------------
PHASE 1: Image Analysis (LLM)
--------------------------------------------------------------------------------

✅ Analysis complete!

📝 Text Description:
   Problem: Prove that angle C is a right angle...

🎨 Drawing Description:
   There is a circle with a diameter from point A to Point B...

📋 Extracted 13 steps
   1. OA = OC = OB
   2. Triangle AOC and Triangle BOC are both isosceles triangles...
   3. ∠OAC = ∠OCA and ∠OBC = ∠OCB...

--------------------------------------------------------------------------------
PHASES 2-7: Multi-Agent Grading Pipeline
--------------------------------------------------------------------------------

Running:
  → StepExtractorAgent (A1)
  → ClaimGeneratorAgent (A2)
  → GeometryFormalizerAgent
  → FormalGeoStepGrader / MathVerifier (H1)
  → RubricScorerAgent (A3)
  → RefereeAgent (A4)

✅ Grading pipeline complete!

================================================================================
GRADING RESULTS
================================================================================

🎯 FINAL SCORE: 85/100

🔬 FormalGeo Grading: ✅ USED

📝 Steps Extracted: 13
   1. OA = OC = OB
   2. Triangles AOC and BOC are isosceles
   3. ∠OAC = ∠OCA
   ...

🔍 Claims Generated: 8
   1. [S1C1] RADIUS_EQUAL(OA, OC, OB)
   2. [S2C1] ISOSCELES_BASE_ANGLES(triangle AOC)
   ...

✅ Verification Summary:
   ✓ True:    6
   ✗ False:   1
   ? Unknown: 1

❌ Failed Claims:
   - S7C1: WRONG_CONCLUSION

💯 Rubric Breakdown:
   [R1] 2/2 - Correctly identified radii equality
   [R2] 2/2 - Valid isosceles triangle reasoning
   [R3] 1/2 - Partial credit for angle sum
   [R4] 0/2 - Incorrect conclusion about final angle

--------------------------------------------------------------------------------
FORMALGEO DETAILED GRADING REPORT
--------------------------------------------------------------------------------

📊 FormalGeo Score: 80/100
🎯 Goal Reached: false
💯 Confidence: 0.88

📝 Step-by-Step Verification:
   ✓ Step 1: Valid (theorem: circle_property_radius_equal)
   ✓ Step 2: Valid (theorem: isosceles_triangle_definition)
   ✓ Step 3: Valid (theorem: isosceles_base_angles_equal)
   ✓ Step 4: Valid (theorem: isosceles_base_angles_equal)
   ✓ Step 5: Valid (theorem: angle_substitution)
   ✓ Step 6: Valid (theorem: triangle_angle_sum)
   ✓ Step 7: Valid (theorem: triangle_angle_sum)
   ✗ Step 8: Invalid theorem application - prerequisites not met

❌ Point Deductions (1 total):

   -20 pts | step 8
   Reason: Step 8 incorrectly applies inscribed angle theorem. Angle AOB is 180° (straight line/diameter), not 90°.
   Confidence: 0.92

📄 Summary:
   Student demonstrated good understanding of isosceles triangle properties and correctly applied radius equality. However, there was an incorrect application of inscribed angle theorem at step 8. The solution shows strong foundational knowledge but needs refinement in theorem application.

💾 Full results saved to:
   /Users/yud/repo/outsmartai/backend/tests/output/e2e_result_CorrectSolution2.json

================================================================================
TEST COMPLETED
================================================================================

================================================================================
FINAL RESULT: 85/100 (85.0%)
FormalGeo Used: Yes
================================================================================
```

---

## Output Files

After running the test, you'll find:

```
tests/output/
└── e2e_result_CorrectSolution2.json  # Complete grading results
```

This JSON file contains:
- Full image analysis
- All extracted steps
- Generated claims
- Verification results for each claim
- FormalGeo step-by-step feedback
- Point deductions with explanations
- Final score and summary

---

## Interpreting FormalGeo Results

### Step Verification Status

- **✓ Valid**: Step is mathematically correct, theorem properly applied
- **✗ Invalid**: Step has an error (see error type below)

### Error Types

| Error Type | Points | Meaning |
|------------|--------|---------|
| `missing_premise` | -20 | Required prerequisite step missing |
| `invalid_theorem` | -20 | Theorem cannot be applied (prerequisites not met) |
| `wrong_conclusion` | -20 | Theorem applied but conclusion is wrong |
| `not_derivable` | -20 | Claim cannot be derived from current state |
| `computation_error` | -10 | Local calculation mistake |
| `syntax_error` | -10 | Incorrect notation/format |
| `cascading_error` | -10 | Error inherited from invalid previous step |

---

## Troubleshooting

### "No module named 'formalgeo'"

```bash
# Use FormalGeo's virtual environment
/Users/yud/repo/FormalGeo/.venv/bin/python tests/test_e2e_diameter.py
```

### "No dataset named 'formalgeo7k'"

```bash
# Download the dataset
cd /Users/yud/repo/outsmartai/backend
/Users/yud/repo/FormalGeo/.venv/bin/python tests/download_formalgeo_datasets.py
```

### "ModuleNotFoundError: No module named 'flask'"

```bash
# Install Flask in FormalGeo venv
/Users/yud/repo/FormalGeo/.venv/bin/pip install flask flask-cors python-dotenv pillow
```

### Test runs but FormalGeo not used

Check the output - if you see `🔬 FormalGeo Grading: ❌ NOT USED`, it means:
- Datasets not loaded properly
- FormalGeo module not available
- Formalization failed

Enable verbose logging to debug:
```python
# In app.py, add at top:
import logging
logging.basicConfig(level=logging.DEBUG)
```

---

## Testing Different Images

You have 3 test images available:

```bash
# Correct solution (should score high)
./run_e2e_test.sh tests/data/CorrectSolution1.png
./run_e2e_test.sh tests/data/CorrectSolution2.png

# Wrong solution (should have deductions)
./run_e2e_test.sh tests/data/WrongSolution1.png
```

---

## Next Steps

Once the test passes:

1. **Integrate with frontend**: The `/analyze` endpoint now returns FormalGeo results
2. **Customize deductions**: Modify `calculate_deduction()` in `formalgeo_grader.py`
3. **Add more problems**: System works with any geometry problem
4. **Tune theorem matching**: Improve `fuzzy_match_theorem()` for better accuracy

---

## Summary

To run the E2E test **right now** with the image you provided:

```bash
cd /Users/yud/repo/outsmartai/backend
export LLM_PROVIDER=openai
export LLM_API_KEY=your_key
./run_e2e_test.sh
```

The test will analyze your diameter-right angle problem image, extract the solution steps, verify each step with FormalGeo's theorem prover, and provide a detailed grading report with explanations for any errors.

**Expected result**: If the solution in the image is correct, you should see **~100/100**. If there are errors, FormalGeo will identify exactly which step is wrong and why.
