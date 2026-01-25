# FormalGeo Integration Status Report

## ✅ What's Working

1. **GDL Loading**: Successfully loads predicate_GDL and theorem_GDL from local resources
   - Located in: `/Users/yud/repo/outsmartai/backend/gdl_resources/formalgeo7k/gdl/`
   - Correct structure with keys: `['Preset', 'Entity', 'Relation', 'Attribution']`
   - 196 theorems loaded

2. **FormalGeo Problem Initialization**: Problem loads successfully
   - KB initialized with 58 items
   - No errors during loading (only warnings about EE/FV checks)

3. **Pipeline Integration**: FormalGeo grading runs in the pipeline
   - MathVerifier correctly detects FormalGeo availability
   - Step grader initializes correctly
   - 7 CDL claims converted to steps

4. **Environment**: Correct Python venv being used
   - `/Users/yud/repo/outsmartai/.venv/bin/python`
   - formalgeo version 0.0.4 installed

## ❌ What's Not Working

### Main Issue: All Claims Show as "not_derivable"

All 7 CDL claims are being marked as FALSE with error "not_derivable". This means:
- The claims exist in valid CDL format
- FormalGeo can parse them
- But FormalGeo's solver cannot derive them from the current KB

Example claims that fail:
1. `Equal(LengthOfLine(OA),LengthOfLine(OC))` - Should be derivable from circle properties
2. `Equal(LengthOfLine(OC),LengthOfLine(OB))` - Should be derivable from circle properties  
3. `Equal(MeasureOfAngle(OAC),MeasureOfAngle(OCA))` - Should follow from isosceles triangle

### Root Cause Analysis

The problem is likely one of these:

#### 1. Problem CDL is Missing Key Information

Current construction_cdl:
```
['Collinear(AOB)', 'Shape(AB,BC,CA)', 'Cocircular(O,ABC)']
```

Current text_cdl:
```
['IsCentreOfCircle(O,O)', 'IsDiameterOfCircle(AB,O)']
```

**Issue**: `IsCentreOfCircle(O,O)` is wrong - second parameter should be a circle ID, not O again.

#### 2. Claims are in CDL format but not matching FormalGeo's predicate format

The parser is extracting points as `('o', 'a', 'o', 'c')` from `Equal(LengthOfLine(OA),LengthOfLine(OC))`.

**But FormalGeo expects**: Items in the format that matches its parsed predicates.

For `Equal(LengthOfLine(OA),LengthOfLine(OC))`, FormalGeo expects:
```python
("Equal", (("LengthOfLine", ("O", "A")), ("LengthOfLine", ("O", "C"))))
```

Not:
```python
("Equal", ("o", "a", "o", "c"))
```

#### 3. The simple regex parser is insufficient

Current parser extracts points but loses the structure of nested predicates like `LengthOfLine(OA)`.

## 🔧 What Needs to Be Fixed

### Priority 1: Use FormalGeo's Built-in CDL Parser

Instead of regex parsing, we should:
1. Add claims directly to problem_CDL's `text_cdl` array
2. Let FormalGeo's `parse_problem_cdl` handle the parsing
3. Then check if the parsed items exist in the KB

### Priority 2: Fix the verification approach

Current approach:
```python
# Wrong: Trying to parse claim ourselves and check if it exists
claim_predicate, claim_item = self.parse_claim_to_predicate(claim_cdl)
exists = self.solver.problem.condition.has(claim_predicate, claim_item)
```

Better approach:
```python
# Right: Add claim to problem as text_cdl, apply theorems, see if derivable
# OR: Use FormalGeo's forward/backward search to verify derivability
```

### Priority 3: Improve Geometry Formalizer Agent

The LLM is generating some incorrect CDL:
- `IsCentreOfCircle(O,O)` → should be `IsCentreOfCircle(O,CircleO)` or similar
- Missing some construction details that would help FormalGeo

## 📋 Recommended Next Steps

### Step 1: Simplify the verification approach

Don't try to parse claims ourselves. Instead:

```python
def verify_step(self, step_cdl: str):
    # Save current KB state
    initial_state = snapshot_kb()
    
    # Try to add this CDL statement to the problem
    try:
        # Parse using FormalGeo's parser
        parsed = parse_problem_cdl({"text_cdl": [step_cdl], ...})
        
        # Try to add to condition
        # If it's already there -> redundant but valid
        # If prerequisites missing -> not_derivable
        # If adds successfully -> check what theorem makes it derivable
        
    except Exception as e:
        return "syntax_error"
```

### Step 2: Use FormalGeo's forward search

```python
from formalgeo.solver import ForwardSearcher

# Apply all available theorems to see what's derivable
searcher = ForwardSearcher(self.solver)
searcher.search()  # Applies theorems automatically

# Now check if claim exists in KB
if self.solver.problem.condition.has(predicate, item):
    return "valid"
```

### Step 3: Fix the GeometryFormalizerAgent prompt

Add examples showing correct formats:
- Circle constructions need proper center specification
- Claims should be atomic (no complex nesting initially)

## 🎯 Current Output

```
🎯 FINAL SCORE: 0/8 (0.0%)
🔬 FormalGeo Grading: ❌ NOT USED
```

The "NOT USED" is misleading - FormalGeo DID run, but all claims failed verification so the flag shows as not used.

To show ✅ USED, at least one claim needs `reason_code="FORMALGEO_VERIFIED"`, which requires at least one claim to have `is_valid=True`.

## 📌 Summary

**Progress**: 80% complete
- ✅ GDL loading
- ✅ Problem initialization  
- ✅ Pipeline integration
- ❌ Claim verification (all failing)

**Key Issue**: The simple regex-based claim parser doesn't work with FormalGeo's internal representation. We need to either:
1. Use FormalGeo's parsers directly, or
2. Use FormalGeo's search capabilities to verify derivability

**Recommendation**: Switch from "parse and check KB" approach to "apply theorems and search" approach using FormalGeo's built-in `ForwardSearcher`.
