# Step-by-Step Verification Mechanism Explained

## The Core Question
**How can we verify that step 1-6 are correct, detect that step 7 is wrong, and properly handle the cascading errors in steps 8-10?**

## Answer: FormalGeo's Knowledge Base as Ground Truth

### The Key Insight

FormalGeo's `Interactor` maintains a **dynamic knowledge base** that grows as we apply valid theorems. We can verify each step by checking:

1. **Can this step's theorem be applied?** (Prerequisites exist in knowledge base)
2. **Does applying it produce the claimed result?** (Conclusion appears in knowledge base after application)

If YES to both → Step is CORRECT → Update knowledge base with new conclusions  
If NO to either → Step is WRONG → Do NOT update knowledge base → Flag error

---

## Detailed Example Walkthrough

### Problem Setup
```
Given: Circle O with diameter AB, point C on circle
Goal: Prove angle ACB = 90°
```

**FormalGeo Initial State (after loading problem CDL):**
```python
solver.problem.condition.items_group = {
    "Point": [("A",), ("B",), ("C",), ("O",)],
    "Circle": [("O",)],
    "Line": [("AB",)],
    "Cocircular": [("O","A","C","B")],
    "Diameter": [("AB",)],
    # ... and many auto-derived predicates from construction phase
}
```

---

### Student Solution (10 Steps)

```
Step 1: "OA = OC = OB (all radii of circle O)"
Step 2: "Triangle AOC is isosceles"
Step 3: "Triangle BOC is isosceles"
Step 4: "∠OAC = ∠OCA (base angles of isosceles triangle AOC)"
Step 5: "∠OBC = ∠OCB (base angles of isosceles triangle BOC)"
Step 6: "Let ∠OAC = α, ∠OCA = α, ∠OBC = β, ∠OCB = β"
Step 7: "∠AOC = 180° - 2α (angle sum in triangle AOC)"  ← CORRECT
Step 8: "∠BOC = 180° - 2β (angle sum in triangle BOC)"  ← CORRECT
Step 9: "∠AOB = 90° (inscribed angle theorem)"          ← WRONG! (should be 180°)
Step 10: "∠ACB = α + β = 45°"                           ← WRONG! (consequence of step 9)
```

---

## Verification Process (Step-by-Step)

### **Initialization**
```python
solver = Interactor(predicate_GDL, theorem_GDL)
solver.load_problem(problem_CDL)

# Snapshot initial knowledge base
KB_initial = {
    "Line": {("O","A"), ("O","B"), ("O","C"), ("A","B")},
    "Equation": set(),  # No equations yet
    # ... other predicates
}
```

---

### **Step 1 Verification**

**Student Claim (formalized by GeometryFormalizerAgent):**
```python
step1_claim = {
    "claim_cdl": [
        "Equal(LengthOfLine(OA),LengthOfLine(OC))",
        "Equal(LengthOfLine(OC),LengthOfLine(OB))"
    ],
    "theorem_name": "radius_equal"
}
```

**Verification Process:**
```python
def verify_step1():
    # 1. Check if claim already in KB (redundant but valid)
    claim_predicate = "Equation"
    claim_item = "LengthOfLine(O,A) - LengthOfLine(O,C)"  # parsed to sympy equation
    
    exists = solver.problem.condition.has(claim_predicate, claim_item)
    if exists:
        return VALID_REDUNDANT
    
    # 2. Try to apply theorem "radius_equal" (or fuzzy matched name)
    matched_theorem = fuzzy_match("radius_equal", solver.parsed_theorem_GDL.keys())
    # Finds: "circle_property_radius_equal"
    
    # 3. Extract parameters from claim
    params = extract_parameters(matched_theorem, claim_item)
    # Returns: (O, A, C) - circle center and two points on circle
    
    # 4. Check prerequisites
    theorem_def = solver.parsed_theorem_GDL["circle_property_radius_equal"]
    # Prerequisites: Cocircular(O, ..., A, ...), Cocircular(O, ..., C, ...)
    
    prereqs_met = check_prerequisites(solver, theorem_def, params)
    # Checks: Cocircular(O,A,C,B) exists? YES ✓
    
    if not prereqs_met:
        return INVALID("missing_premise")
    
    # 5. Apply theorem and check conclusion
    before_state = snapshot_kb(solver)
    
    update = solver.apply_theorem(
        t_name="circle_property_radius_equal",
        t_para=(O, A, C, B),
        t_branch=None
    )
    
    after_state = snapshot_kb(solver)
    
    # 6. Check if claimed equation now exists
    claim_exists = solver.problem.condition.has("Equation", claim_item)
    
    if claim_exists:
        # SUCCESS! New knowledge added to KB
        new_knowledge = after_state - before_state
        # new_knowledge = {Equation: [LengthOfLine(O,A) - LengthOfLine(O,C) = 0, ...]}
        
        return VALID(
            new_knowledge=new_knowledge,
            theorem_applied="circle_property_radius_equal"
        )
    else:
        # Theorem applied but didn't produce claim - WRONG CONCLUSION
        restore_kb(solver, before_state)
        return INVALID("wrong_conclusion")
```

**Result:** ✅ **VALID** - Step 1 is correct, KB updated with radius equality equations

**Knowledge Base After Step 1:**
```python
KB_after_step1 = KB_initial ∪ {
    "Equation": {
        "LengthOfLine(O,A) - LengthOfLine(O,C) = 0",
        "LengthOfLine(O,C) - LengthOfLine(O,B) = 0",
        "LengthOfLine(O,A) - LengthOfLine(O,B) = 0"
    }
}
```

---

### **Step 2 Verification**

**Student Claim:**
```python
step2_claim = {
    "claim_cdl": "IsoscelesTriangle(A,O,C)",
    "theorem_name": "isosceles_definition",
    "depends_on": [1]  # Depends on step 1
}
```

**Verification:**
```python
def verify_step2():
    # 1. Check dependency
    if step1_result.is_valid == False:
        return INVALID("dependency_failed", depends_on=[1])
    
    # 2. Match theorem
    matched = fuzzy_match("isosceles_definition", theorems)
    # Finds: "isosceles_triangle_judgment_two_sides_equal"
    
    # 3. Check prerequisites
    # Requires: Equal(LengthOfLine(OA), LengthOfLine(OC))
    prereqs = solver.problem.condition.has(
        "Equation", 
        "LengthOfLine(O,A) - LengthOfLine(O,C)"
    )
    # prereqs = TRUE ✓ (added in step 1!)
    
    # 4. Apply theorem
    solver.apply_theorem(
        t_name="isosceles_triangle_judgment_two_sides_equal",
        t_para=("A", "O", "C")
    )
    
    # 5. Check conclusion exists
    exists = solver.problem.condition.has(
        "IsoscelesTriangle",
        ("A", "O", "C")
    )
    
    return VALID if exists else INVALID("not_derivable")
```

**Result:** ✅ **VALID** - Step 2 is correct

**Knowledge Base After Step 2:**
```python
KB_after_step2 = KB_after_step1 ∪ {
    "IsoscelesTriangle": {("A","O","C"), ("C","O","A")}
}
```

---

### **Steps 3-8 Verification**

Following the same pattern, steps 3-8 are all verified as **VALID** because:
- Each theorem's prerequisites exist in the KB (from prior steps)
- Applying the theorem produces the claimed conclusion
- KB grows with each valid step

**Knowledge Base After Step 8:**
```python
KB_after_step8 = KB_after_step7 ∪ {
    "Equation": {
        # From step 7:
        "MeasureOfAngle(A,O,C) - (180 - 2*α) = 0",
        # From step 8:
        "MeasureOfAngle(B,O,C) - (180 - 2*β) = 0",
        # ... many other derived equations
    }
}
```

---

### **Step 9 Verification (FIRST ERROR)**

**Student Claim:**
```python
step9_claim = {
    "claim_cdl": "Equal(MeasureOfAngle(AOB), 90)",
    "theorem_name": "inscribed_angle_theorem",
    "depends_on": [1,2,3,4,5,6,7,8]
}
```

**Verification:**
```python
def verify_step9():
    # 1. Match theorem
    matched = fuzzy_match("inscribed_angle_theorem", theorems)
    # Finds: "inscribed_angle_theorem"
    
    # 2. Check prerequisites
    theorem_def = solver.parsed_theorem_GDL["inscribed_angle_theorem"]
    # Requires: Arc connecting points, inscribed angle, central angle relationship
    
    # 3. Extract parameters
    # Student claims: central angle AOB = 90°
    # But theorem requires: inscribed angle + arc + central angle relation
    
    # 4. Check what the theorem ACTUALLY produces
    # Prerequisites for inscribed angle theorem:
    #   - Need an inscribed angle (vertex on circle)
    #   - Need a central angle (vertex at center)
    #   - Relationship: inscribed = (1/2) * central
    
    # 5. Apply theorem with correct parameters
    # AOB is a straight line (diameter) → central angle = 180°
    # NOT an inscribed angle scenario!
    
    # Try to apply theorem
    update = solver.apply_theorem(
        t_name="inscribed_angle_theorem",
        t_para=("A", "O", "B", "C"),  # Attempting to fit parameters
        t_branch=None
    )
    
    if not update:
        # Theorem prerequisites NOT met!
        return INVALID(
            error_type="invalid_theorem",
            reason="Inscribed angle theorem does not apply - AOB is a diameter (straight line, 180°), not an inscribed angle",
            confidence=0.92
        )
    
    # 6. Even if theorem applied, check if conclusion matches
    # The correct derivation would give angle AOB = 180° (straight line)
    # Student claimed 90° → WRONG CONCLUSION
    
    claimed_equation = "MeasureOfAngle(A,O,B) - 90 = 0"
    actual_equation = "MeasureOfAngle(A,O,B) - 180 = 0"  # What KB actually has
    
    exists = solver.problem.condition.has("Equation", claimed_equation)
    # exists = FALSE ❌
    
    return INVALID(
        error_type="wrong_conclusion",
        reason="Angle AOB is 180° (straight line on diameter), not 90°",
        expected_value=180,
        claimed_value=90,
        confidence=0.95
    )
```

**Result:** ❌ **INVALID** - Step 9 is WRONG

**Deduction Calculation:**
```python
deduction = calculate_deduction("wrong_conclusion", step9_claim)
# Returns:
{
    "deducted_points": 20,  # Interstep logic error (criteria 3c)
    "deduction_reason": "Step 9: Incorrect conclusion - angle AOB equals 180° as it is a straight line (diameter), but student claimed 90°. Inscribed angle theorem misapplied.",
    "deduction_confidence_score": 0.95,
    "deduction_step": "step 9",
    "formalgeo_evidence": {
        "theorem_attempted": "inscribed_angle_theorem",
        "actual_value": 180,
        "claimed_value": 90,
        "kb_state": "MeasureOfAngle(A,O,B) = 180 exists in knowledge base from diameter property"
    }
}
```

**CRITICAL: Knowledge Base NOT Updated**
```python
# Because step 9 is invalid, we DO NOT add the wrong equation to KB
KB_after_step9 = KB_after_step8  # Unchanged!

# This prevents cascading errors from corrupting the knowledge base
```

---

### **Step 10 Verification (Cascading Error)**

**Student Claim:**
```python
step10_claim = {
    "claim_cdl": "Equal(MeasureOfAngle(ACB), 45)",
    "theorem_name": "angle_sum_in_quadrilateral",
    "depends_on": [9]  # Depends on WRONG step 9!
}
```

**Verification:**
```python
def verify_step10():
    # 1. Check dependency validity
    if step9_result.is_valid == False:
        # Dependency failed! Flag as cascading error
        return INVALID(
            error_type="cascading_error",
            reason="Step 10 depends on invalid step 9. Cannot verify based on incorrect premise.",
            dependency_chain=[9],
            confidence=0.85,
            note="This step may be logically sound IF step 9 were correct, but since step 9 is wrong, this conclusion is also wrong."
        )
    
    # 2. Try to verify independently (ignoring bad dependency)
    # Check if angle ACB = 45° can be derived from VALID steps 1-8
    
    # Search KB for angle ACB value
    angle_acb_equations = search_kb(solver, "MeasureOfAngle(A,C,B)")
    
    # 3. Use equation solver to find actual value
    from formalgeo.core import EquationKiller
    
    target_eq = symbols('MeasureOfAngle_ACB') - 45  # Student's claim
    result, premise = EquationKiller.solve_target(target_eq, solver.problem)
    
    if result is not None and rough_equal(result, 0):
        # Value 45° is derivable from current KB
        return VALID_BUT_WRONG_JUSTIFICATION(
            reason="Conclusion 45° cannot be derived from current valid state. Actual value is 90°."
        )
    else:
        # Value 45° is NOT derivable
        actual_value = EquationKiller.solve_for(
            symbols('MeasureOfAngle_ACB'),
            solver.problem
        )
        
        return INVALID(
            error_type="cascading_error",
            reason=f"Step 10: Claimed angle ACB = 45°, but correct value is {actual_value}°. Error caused by incorrect angle AOB = 90° in step 9.",
            actual_value=actual_value,
            claimed_value=45,
            root_cause_step=9,
            confidence=0.88
        )
```

**Result:** ❌ **INVALID (Cascading Error)**

**Deduction Calculation:**
```python
# Important: Different deduction strategy for cascading errors!

def calculate_cascading_deduction(step, root_cause_step):
    """
    For cascading errors, we have options:
    
    Option A: Deduct points for each wrong step (harsh)
    Option B: Deduct once for root cause, mark cascading steps as "contaminated" (lenient)
    Option C: Deduct for root cause + partial deduction for cascading (balanced)
    """
    
    # Recommended: Option C (Balanced)
    if step.error_type == "cascading_error":
        return {
            "deducted_points": 10,  # Half penalty (10 instead of 20)
            "deduction_reason": f"Step {step.step_id}: Incorrect conclusion (angle ACB = 45° vs actual 90°) resulting from error in step {root_cause_step}",
            "deduction_confidence_score": 0.85,
            "deduction_step": f"step {step.step_id}",
            "note": "Partial deduction - error cascaded from step 9. Student's reasoning from step 9 was logically consistent but based on wrong premise.",
            "is_cascading": True,
            "root_cause": f"step {root_cause_step}"
        }
```

**Final Deductions List:**
```json
{
  "deductions": [
    {
      "deducted_points": 20,
      "deduction_reason": "Step 9: Incorrect application of inscribed angle theorem. Angle AOB is 180° (straight line/diameter), not 90°.",
      "deduction_confidence_score": 0.95,
      "deduction_step": "step 9",
      "error_type": "wrong_conclusion"
    },
    {
      "deducted_points": 10,
      "deduction_reason": "Step 10: Incorrect conclusion (angle ACB = 45° vs actual 90°) resulting from error in step 9.",
      "deduction_confidence_score": 0.85,
      "deduction_step": "step 10",
      "error_type": "cascading_error",
      "root_cause": "step 9"
    }
  ],
  "total_deducted": 30,
  "total_points": 70
}
```

---

## How This Works: The Key Mechanisms

### 1. **Knowledge Base as Ground Truth**
```python
# FormalGeo maintains a provably correct knowledge base
# Each theorem application is VERIFIED before adding to KB

KB = {predicate: {items}} for all derived facts

# We check claims against this KB:
claim_is_correct = KB.has(predicate, item)
```

### 2. **Sequential State Management**
```python
# We verify steps IN ORDER
for step in student_steps:
    # Check against CURRENT KB state
    is_valid = verify_against_current_kb(step)
    
    if is_valid:
        # Apply theorem → KB grows
        KB = KB ∪ new_conclusions
    else:
        # DO NOT update KB → prevents corruption
        mark_as_error(step)
```

### 3. **Theorem Application Verification**
```python
# FormalGeo's apply_theorem() has built-in checking:

def apply_theorem(t_name, t_para, t_branch):
    # 1. Check all prerequisites exist in current KB
    for prereq in theorem.prerequisites:
        if not KB.has(prereq):
            return False  # Cannot apply
    
    # 2. Execute theorem logic (GPL - Geometry Predicate Logic)
    conclusions = execute_gpl(theorem.body, KB)
    
    # 3. Add new conclusions to KB
    for conclusion in conclusions:
        KB.add(conclusion)
    
    return True  # Successfully applied
```

### 4. **Dependency Chain Tracking**
```python
class StepResult:
    is_valid: bool
    depends_on: List[int]  # Which prior steps this depends on
    
# When we find an error:
def propagate_error(error_step_id):
    # Mark all dependent steps as potentially contaminated
    for step in remaining_steps:
        if error_step_id in step.depends_on:
            step.mark_as_cascading_error(root_cause=error_step_id)
```

---

## Why This Approach Works

### **Mathematical Rigor**
- FormalGeo uses **formal logic** (not heuristics)
- Theorem applications are **provably correct**
- Knowledge base maintains **logical consistency**

### **Step Isolation**
- Each step verified **independently** against current KB
- Invalid steps **don't corrupt** future verification
- Can identify **exact point of failure**

### **Cascading Error Detection**
- Track **dependency chains** (which steps depend on which)
- When step N fails, mark steps depending on N as **contaminated**
- Give **partial credit** for logically consistent reasoning from wrong premise

### **Concrete Evidence**
- Every verdict has **formal proof** from FormalGeo
- Can show **exact KB state** at each step
- Can identify **which prerequisite** was missing

---

## Comparison: Without FormalGeo vs With FormalGeo

### **Without FormalGeo (LLM-based)**
```python
# Step 9 verification (LLM approach):
prompt = f"""
Is this step correct?
Step 9: "∠AOB = 90° (inscribed angle theorem)"
Given previous steps: {steps_1_to_8}
"""

llm_response = await llm.chat(prompt)
# Response: "This step appears correct. The inscribed angle theorem 
#            states that an inscribed angle is half the central angle."
# 
# WRONG! LLM didn't notice AOB is the diameter, not an inscribed angle.
# Confidence: 0.7 (made up number, no formal basis)
```

### **With FormalGeo (Our approach)**
```python
# Step 9 verification (FormalGeo approach):
result = verify_step_with_formalgeo(step9, solver)

# FormalGeo checks:
# 1. Does "inscribed_angle_theorem" have prerequisites?
#    → Yes: requires inscribed angle (vertex on circle)
# 2. Is AOB an inscribed angle?
#    → No: O is the center, not on circle
# 3. Can theorem be applied?
#    → No: prerequisites not met
# 4. What IS the angle AOB?
#    → KB has: Line(A,B) is diameter → angle = 180°
# 
# RESULT: INVALID
# Reason: "Inscribed angle theorem misapplied. AOB = 180° (diameter)"
# Confidence: 0.95 (based on formal derivation)
```

---

## Summary: How We Know Steps 1-6 Are Correct and Step 7 Is Wrong

1. **Initialize KB** with problem givens (FormalGeo's construction phase)

2. **Verify Step 1** against KB:
   - Check prerequisites exist? ✓
   - Apply theorem → new conclusions added to KB
   - Check claimed conclusion exists in updated KB? ✓
   - **VALID** → KB updated

3. **Verify Step 2** against updated KB:
   - Prerequisites from Step 1 exist? ✓
   - Apply theorem → KB grows
   - Claimed conclusion exists? ✓
   - **VALID** → KB updated

4. **Verify Steps 3-6** (same process) → All **VALID**

5. **Verify Step 7**:
   - Prerequisites exist? ✓
   - Apply theorem → produces different result
   - Claimed conclusion exists in KB? ❌
   - **INVALID** → KB NOT updated, deduct 20 points

6. **Verify Step 8+** (cascade):
   - Depends on Step 7? Yes
   - Step 7 invalid? Yes
   - Mark as **cascading error**, deduct 10 points

**The KB is our "referee"** - it only contains provably correct facts, so we can definitively say which steps are right or wrong.
