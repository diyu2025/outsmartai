# FormalGeo-Integrated Step-by-Step Grading Algorithm

## Overview
This document describes a comprehensive grading algorithm that uses FormalGeo's theorem proving capabilities to verify student geometry solutions with step-by-step accuracy checking and detailed feedback.

## Architecture Integration

```
┌─────────────────────────────────────────────────────────────────┐
│                    Existing Pipeline                             │
├─────────────────────────────────────────────────────────────────┤
│ Image Input → StepExtractorAgent → ClaimGeneratorAgent →        │
│               GeometryFormalizerAgent → CDL/GDL Output          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│              NEW: FormalGeo Step Grader                          │
├─────────────────────────────────────────────────────────────────┤
│ 1. Initialize FormalGeo Solver with Problem CDL/GDL             │
│ 2. Verify Each Student Step Sequentially                        │
│ 3. Track Theorem Applications & Validity                        │
│ 4. Identify Missing/Incorrect/Redundant Steps                   │
│ 5. Generate Detailed Deduction Report                           │
└─────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. FormalGeoStepGrader Class

**Purpose**: Orchestrates step-by-step verification using FormalGeo's Interactor API.

**Key Methods**:
```python
class FormalGeoStepGrader:
    def __init__(self, predicate_gdl, theorem_gdl):
        """Initialize with FormalGeo's predicate and theorem definitions"""
        
    def load_problem(self, problem_cdl):
        """Load the original problem state"""
        
    def verify_step_sequence(self, student_steps, student_claims):
        """Main grading method - verify all steps sequentially"""
        
    def verify_single_step(self, step, claim, current_state):
        """Verify if a single step is valid given current knowledge base"""
        
    def apply_theorem_if_valid(self, theorem_name, parameters, branch=None):
        """Try to apply theorem and check if it produces claimed conclusion"""
        
    def check_conclusion_derivable(self, conclusion_predicate, conclusion_item):
        """Check if conclusion exists in current problem state"""
        
    def identify_missing_steps(self, current_state, goal_state):
        """Find what steps are needed to reach goal from current state"""
```

### 2. Step Verification Algorithm

#### Input Structure
From GeometryFormalizerAgent, we receive:
```json
{
  "construction_cdl": ["Shape(AB,BC,CA)", "Cocircular(O,ABC)"],
  "text_cdl": ["Equal(LengthOfLine(AB),LengthOfLine(AC))", ...],
  "claim_cdl": ["Equal(MeasureOfAngle(ABC),MeasureOfAngle(ACB))"],
  "goal_cdl": "Value(MeasureOfAngle(BAC))",
  "student_steps": [
    {
      "step_id": 1,
      "claim": "OA = OB = OC (radii of circle)",
      "claim_cdl": "Equal(LengthOfLine(OA),LengthOfLine(OB))",
      "theorem_name": "radius_equal",
      "confidence": "high"
    },
    {
      "step_id": 2,
      "claim": "Triangle ABC is isosceles",
      "claim_cdl": "IsoscelesTriangle(ABC)",
      "theorem_name": "two_sides_equal_definition",
      "depends_on": [1],
      "confidence": "medium"
    }
  ]
}
```

#### Verification Process

**Phase 1: Problem Initialization**
```python
def initialize_problem(gdl_payload):
    """
    Initialize FormalGeo solver with problem givens
    
    Returns:
        - solver: Interactor instance
        - initial_conditions: Set of all predicates from construction_cdl + text_cdl
        - goal: Goal predicate to prove/solve
    """
    solver = Interactor(gdl_payload["predicate_GDL"], gdl_payload["theorem_GDL"])
    solver.load_problem(gdl_payload["problem_CDL"])
    
    # Capture initial state
    initial_conditions = {
        predicate: set(solver.problem.condition.get_items_by_predicate(predicate))
        for predicate in solver.problem.condition.items_group.keys()
    }
    
    return solver, initial_conditions, solver.problem.goal
```

**Phase 2: Sequential Step Verification**
```python
def verify_step_sequence(solver, student_steps, grading_criteria):
    """
    Verify each step sequentially, tracking state changes
    
    For each step:
    1. Check if claimed theorem is applicable
    2. Verify prerequisites exist
    3. Apply theorem and check if conclusion matches claim
    4. Track new knowledge added
    5. Identify errors with detailed reasons
    """
    step_results = []
    current_state = capture_solver_state(solver)
    
    for step in student_steps:
        result = verify_single_step(
            solver=solver,
            step=step,
            current_state=current_state,
            grading_criteria=grading_criteria
        )
        step_results.append(result)
        
        # Update state if step was valid
        if result.is_valid:
            current_state = capture_solver_state(solver)
    
    return step_results
```

**Phase 3: Single Step Verification**
```python
def verify_single_step(solver, step, current_state, grading_criteria):
    """
    Detailed verification of a single step
    
    Returns StepVerificationResult with:
    - is_valid: bool
    - error_type: None | "missing_premise" | "invalid_theorem" | "wrong_conclusion" | "redundant"
    - error_details: str
    - points_deducted: int
    - confidence: float
    """
    
    # Step 1: Parse the claim into FormalGeo predicate format
    claim_predicate, claim_item = parse_claim_to_predicate(step.claim_cdl)
    
    # Step 2: Check if conclusion already exists (redundant step)
    if solver.problem.condition.has(claim_predicate, claim_item):
        return StepVerificationResult(
            step_id=step.step_id,
            is_valid=True,
            is_redundant=True,
            error_type=None,
            points_deducted=0,
            note="Step is correct but redundant"
        )
    
    # Step 3: Identify and verify theorem application
    if step.theorem_name:
        theorem_result = verify_theorem_application(
            solver=solver,
            theorem_name=step.theorem_name,
            claim_predicate=claim_predicate,
            claim_item=claim_item,
            depends_on=step.depends_on
        )
        
        if not theorem_result.is_valid:
            return StepVerificationResult(
                step_id=step.step_id,
                is_valid=False,
                error_type=theorem_result.error_type,
                error_details=theorem_result.error_details,
                points_deducted=calculate_deduction(
                    error_type=theorem_result.error_type,
                    grading_criteria=grading_criteria
                ),
                confidence=0.9
            )
    
    # Step 4: Try automatic theorem search if no theorem specified
    else:
        search_result = search_for_valid_theorem(
            solver=solver,
            target_predicate=claim_predicate,
            target_item=claim_item
        )
        
        if not search_result.found:
            return StepVerificationResult(
                step_id=step.step_id,
                is_valid=False,
                error_type="not_derivable",
                error_details=f"Cannot derive {claim_predicate}{claim_item} from current state",
                points_deducted=20,
                confidence=0.85
            )
    
    # Step 5: Valid step - apply to solver and track
    solver.apply_theorem(...)  # Apply the verified theorem
    
    return StepVerificationResult(
        step_id=step.step_id,
        is_valid=True,
        theorem_applied=step.theorem_name or search_result.theorem_name,
        points_deducted=0,
        confidence=0.95
    )
```

### 3. Theorem Verification Logic

**Matching Student Theorem Names to FormalGeo GDL**
```python
def verify_theorem_application(solver, theorem_name, claim_predicate, claim_item, depends_on):
    """
    Verify if student's claimed theorem usage is correct
    
    Strategy:
    1. Fuzzy match theorem_name to FormalGeo's theorem_GDL keys
    2. Extract theorem parameters from claim_item
    3. Check prerequisites exist in current state
    4. Apply theorem and verify conclusion matches claim
    """
    
    # Step 1: Fuzzy match theorem name
    matched_theorem = fuzzy_match_theorem(
        student_name=theorem_name,
        available_theorems=solver.parsed_theorem_GDL.keys()
    )
    
    if not matched_theorem:
        return TheoremResult(
            is_valid=False,
            error_type="unknown_theorem",
            error_details=f"Cannot find theorem '{theorem_name}' in knowledge base"
        )
    
    # Step 2: Extract parameters from claim
    theorem_params = extract_theorem_parameters(
        theorem_definition=solver.parsed_theorem_GDL[matched_theorem],
        claim_item=claim_item
    )
    
    # Step 3: Check all prerequisites (depends_on)
    for dep_id in depends_on:
        if not check_dependency_exists(solver, dep_id):
            return TheoremResult(
                is_valid=False,
                error_type="missing_premise",
                error_details=f"Prerequisite step {dep_id} not established"
            )
    
    # Step 4: Try applying theorem with extracted parameters
    try:
        # Save current state
        saved_state = copy_solver_state(solver)
        
        # Try to apply theorem
        update = solver.apply_theorem(
            t_name=matched_theorem,
            t_para=theorem_params,
            t_branch=None  # Let it try all branches
        )
        
        if not update:
            # Theorem didn't apply - prerequisites not met
            restore_solver_state(solver, saved_state)
            return TheoremResult(
                is_valid=False,
                error_type="invalid_theorem",
                error_details=f"Theorem '{matched_theorem}' prerequisites not satisfied"
            )
        
        # Step 5: Check if claimed conclusion now exists
        conclusion_exists = solver.problem.condition.has(claim_predicate, claim_item)
        
        if not conclusion_exists:
            restore_solver_state(solver, saved_state)
            return TheoremResult(
                is_valid=False,
                error_type="wrong_conclusion",
                error_details=f"Theorem '{matched_theorem}' does not produce claimed result"
            )
        
        # Success!
        return TheoremResult(
            is_valid=True,
            matched_theorem=matched_theorem,
            parameters=theorem_params
        )
        
    except Exception as e:
        return TheoremResult(
            is_valid=False,
            error_type="formalgeo_error",
            error_details=str(e)
        )
```

**Fuzzy Theorem Matching**
```python
def fuzzy_match_theorem(student_name, available_theorems):
    """
    Match student's informal theorem name to formal GDL theorem
    
    Examples:
    - "radius equal" → "radius_equal" 
    - "isosceles base angles" → "isosceles_triangle_property_angle_equal"
    - "angle sum 180" → "triangle_angle_sum"
    - "SAS congruence" → "congruent_triangle_judgment_sas"
    
    Strategy:
    1. Normalize names (lowercase, remove special chars)
    2. Check exact match
    3. Check substring match
    4. Use keyword matching with theorem descriptions
    5. Use LLM as fallback for semantic matching
    """
    
    normalized_student = normalize_theorem_name(student_name)
    
    # Exact match
    if normalized_student in available_theorems:
        return normalized_student
    
    # Substring match
    for theorem in available_theorems:
        if normalized_student in theorem or theorem in normalized_student:
            return theorem
    
    # Keyword-based matching
    matches = []
    student_keywords = set(normalized_student.split('_'))
    for theorem in available_theorems:
        theorem_keywords = set(theorem.split('_'))
        overlap = student_keywords & theorem_keywords
        if len(overlap) >= 2:  # At least 2 keywords match
            matches.append((theorem, len(overlap)))
    
    if matches:
        # Return best match
        return max(matches, key=lambda x: x[1])[0]
    
    # Fallback: Use LLM for semantic matching
    return llm_match_theorem(student_name, available_theorems)
```

### 4. Point Deduction Logic (Following GRADING PROCEDURE)

```python
def calculate_deduction(error_type, step, grading_criteria):
    """
    Calculate point deduction based on grading procedure
    
    Criteria from app.py lines 860-864:
    3a. Missing obvious steps: Allow if valid and common
    3b. Global misalignment: -100 points (all points)
    3c. Interstep logic error: -20 points per flaw
    3d. Intrastep computation error: -10 points per mistake
    """
    
    deductions = {
        # Global errors (3b)
        "global_misalignment": {
            "points": 100,
            "reason": "Solution does not serve the purpose of solving the problem",
            "confidence": 0.95
        },
        
        # Interstep errors (3c)
        "missing_premise": {
            "points": 20,
            "reason": f"Step {step.step_id} lacks necessary prerequisite - logical gap in reasoning",
            "confidence": 0.90
        },
        "invalid_theorem": {
            "points": 20,
            "reason": f"Step {step.step_id} incorrectly applies theorem - prerequisites not met",
            "confidence": 0.88
        },
        "wrong_conclusion": {
            "points": 20,
            "reason": f"Step {step.step_id} draws incorrect conclusion from theorem application",
            "confidence": 0.92
        },
        "not_derivable": {
            "points": 20,
            "reason": f"Step {step.step_id} claims result that cannot be derived from current state",
            "confidence": 0.85
        },
        
        # Intrastep errors (3d)
        "computation_error": {
            "points": 10,
            "reason": f"Step {step.step_id} contains local computational or algebraic error",
            "confidence": 0.88
        },
        "syntax_error": {
            "points": 10,
            "reason": f"Step {step.step_id} has incorrect mathematical notation or format",
            "confidence": 0.85
        },
        
        # No deduction
        "redundant": {
            "points": 0,
            "reason": f"Step {step.step_id} is correct but redundant",
            "confidence": 0.80
        }
    }
    
    return deductions.get(error_type, {
        "points": 10,
        "reason": f"Step {step.step_id} has unspecified error",
        "confidence": 0.70
    })
```

### 5. Missing Step Detection

```python
def identify_missing_steps(solver, student_steps, goal):
    """
    After verifying all student steps, check if goal is reached
    If not, identify what's missing
    
    Strategy:
    1. Check if goal is satisfied in current state
    2. If not, use FormalGeo's backward search to find gap
    3. Report missing steps
    """
    
    # Check goal
    solver.problem.check_goal()
    
    if solver.problem.goal.solved:
        return {
            "goal_reached": True,
            "missing_steps": []
        }
    
    # Use backward search to identify missing reasoning
    from formalgeo.solver import BackwardSearcher
    
    backward = BackwardSearcher(
        solver.parsed_predicate_GDL,
        solver.parsed_theorem_GDL
    )
    backward.load_problem(solver.problem)
    
    # Search for path to goal
    gap_analysis = backward.search_gap(
        current_state=solver.problem.condition,
        goal=solver.problem.goal
    )
    
    return {
        "goal_reached": False,
        "missing_steps": gap_analysis.missing_theorems,
        "deduction_points": len(gap_analysis.missing_theorems) * 20,
        "deduction_reason": f"Solution incomplete - missing {len(gap_analysis.missing_theorems)} critical step(s) to reach goal"
    }
```

### 6. Complete Grading Flow

```python
async def grade_geometry_solution(gdl_payload, student_steps, grading_criteria):
    """
    Main grading orchestrator
    
    Returns comprehensive grading report with:
    - total_points: int (0-100)
    - deductions: List[Deduction]
    - step_feedback: List[StepFeedback]
    - missing_steps: List[str]
    - confidence: float
    """
    
    # Phase 1: Initialize
    grader = FormalGeoStepGrader(
        gdl_payload["predicate_GDL"],
        gdl_payload["theorem_GDL"]
    )
    solver = grader.load_problem(gdl_payload["problem_CDL"])
    
    # Phase 2: Verify steps sequentially
    step_results = []
    for step in student_steps:
        result = grader.verify_single_step(
            step=step,
            current_state=grader.get_current_state()
        )
        step_results.append(result)
        
        # Early termination if global error
        if result.error_type == "global_misalignment":
            return GradingReport(
                total_points=0,
                deductions=[result.to_deduction()],
                step_feedback=step_results,
                confidence=0.95
            )
    
    # Phase 3: Check for missing steps
    missing_analysis = grader.identify_missing_steps(
        student_steps=student_steps,
        goal=solver.problem.goal
    )
    
    # Phase 4: Calculate final score
    total_deducted = sum(r.points_deducted for r in step_results)
    if missing_analysis["missing_steps"]:
        total_deducted += missing_analysis["deduction_points"]
    
    total_points = max(0, 100 - total_deducted)
    
    # Phase 5: Compile deductions following step 5 of GRADING PROCEDURE
    deductions = compile_deductions(step_results, missing_analysis)
    deductions = filter_low_confidence_deductions(deductions, threshold=0.5)
    deductions = remove_obvious_statement_deductions(deductions, student_steps)
    
    return GradingReport(
        total_points=total_points,
        deductions=deductions,
        step_feedback=[r.to_feedback() for r in step_results],
        missing_steps=missing_analysis["missing_steps"],
        confidence=calculate_overall_confidence(step_results),
        summary=generate_summary(step_results, missing_analysis)
    )
```

## Integration with Existing Pipeline

### Modify GeometryFormalizerAgent Output
```python
class GeometryFormalizerAgent:
    async def run(self, ...):
        # Existing formalization
        resp = await self.llm_service.chat(...)
        
        # NEW: Ensure we load FormalGeo datasets
        from formalgeo.data import DatasetLoader
        
        dl = DatasetLoader(
            dataset_name="formalgeo7k_v2",
            datasets_path="/Users/yud/repo/formalgeo7k/datasets"
        )
        
        # Use dataset's predicate and theorem GDL
        resp["predicate_GDL"] = dl.predicate_GDL
        resp["theorem_GDL"] = dl.theorem_GDL
        
        return resp
```

### Add FormalGeoStepGrader to Verification Pipeline
```python
class MathVerifier:
    def __init__(self, llm_service):
        self.geo = FormalGeoVerifier(llm_service)
        self.alg = AlgebraVerifier()
        self.step_grader = FormalGeoStepGrader()  # NEW
    
    async def verify_all(self, givens, student_diagram_claims, claims, ...):
        # Existing formalization
        gdl_payload = await self.geo.formalize(...)
        
        # NEW: Use step-by-step grader
        if gdl_payload and self.step_grader.available:
            grading_report = await self.step_grader.grade_geometry_solution(
                gdl_payload=gdl_payload,
                student_steps=claims,
                grading_criteria=GRADING_CRITERIA
            )
            
            return {
                "verification_results": grading_report.step_feedback,
                "deductions": grading_report.deductions,
                "total_points": grading_report.total_points,
                "confidence": grading_report.confidence
            }
        
        # Fallback to existing verification
        return self._existing_verification(...)
```

## Output Format

```json
{
  "grading": {
    "total_points": 70,
    "deductions": [
      {
        "deducted_points": 20,
        "deduction_reason": "Step 4: Invalid theorem application - theorem 'vertical_angles_equal' prerequisites not satisfied in current state",
        "deduction_confidence_score": 0.90,
        "deduction_step": "step 4",
        "error_type": "invalid_theorem",
        "formalgeo_details": {
          "attempted_theorem": "vertical_angles_equal",
          "missing_prerequisites": ["Line(AB) and Line(CD) must intersect"],
          "current_state_predicates": ["Line(AB)", "Line(CD)", "Parallel(AB,CD)"]
        }
      },
      {
        "deducted_points": 10,
        "deduction_reason": "Step 6: Local computational error - claimed angle measure 45° but derivation yields 50°",
        "deduction_confidence_score": 0.88,
        "deduction_step": "step 6",
        "error_type": "computation_error"
      }
    ],
    "step_feedback": [
      {
        "step_id": 1,
        "is_valid": true,
        "theorem_applied": "radius_equal",
        "note": "Correctly identified radii equality",
        "confidence": 0.95
      },
      {
        "step_id": 2,
        "is_valid": true,
        "is_redundant": false,
        "theorem_applied": "isosceles_triangle_definition",
        "note": "Valid application of isosceles triangle property",
        "confidence": 0.92
      },
      {
        "step_id": 3,
        "is_valid": true,
        "theorem_applied": "isosceles_base_angles_equal",
        "note": "Correctly derived base angles equality",
        "confidence": 0.94
      },
      {
        "step_id": 4,
        "is_valid": false,
        "error_type": "invalid_theorem",
        "error_details": "Theorem 'vertical_angles_equal' cannot be applied - lines AB and CD are parallel, not intersecting",
        "points_deducted": 20,
        "confidence": 0.90
      }
    ],
    "missing_steps": [
      {
        "theorem": "triangle_angle_sum",
        "description": "Must use angle sum property to find remaining angle",
        "points_deducted": 0,
        "note": "This step is required to complete the solution"
      }
    ],
    "goal_reached": false,
    "confidence_score": 0.89,
    "summary": "Student demonstrated good understanding of isosceles triangle properties and correctly identified radius equality. However, there was an incorrect application of vertical angles theorem at step 4, where the prerequisite of intersecting lines was not met. The solution is incomplete as the final angle calculation using triangle angle sum is missing."
  }
}
```

## Key Advantages

1. **Rigorous Verification**: Uses FormalGeo's theorem prover instead of LLM heuristics
2. **Step-by-Step Tracking**: Maintains solver state throughout verification
3. **Precise Error Identification**: Pinpoints exact logical/computational errors
4. **Theorem Flexibility**: Fuzzy matching allows informal theorem names
5. **Partial Credit**: Tracks which steps are correct even if solution incomplete
6. **Actionable Feedback**: Identifies missing steps needed to complete proof
7. **Reproducible Grading**: Deterministic verification (no LLM variability in core logic)
8. **Standards-Aligned**: Implements exact grading criteria from GRADING PROCEDURE

## Implementation Checklist

- [ ] Create `FormalGeoStepGrader` class in new file `backend/graders/formalgeo_grader.py`
- [ ] Implement `verify_single_step()` with theorem matching
- [ ] Add fuzzy theorem name matching utilities
- [ ] Implement point deduction calculator following GRADING PROCEDURE
- [ ] Add missing step detection using backward search
- [ ] Create state snapshot/restore utilities for solver
- [ ] Integrate with existing `MathVerifier` in `app.py`
- [ ] Update `GeometryFormalizerAgent` to load FormalGeo datasets
- [ ] Add comprehensive logging for debugging
- [ ] Write unit tests with sample problems from formalgeo7k
- [ ] Add confidence score calibration based on test results
- [ ] Document theorem name mapping table

## Testing Strategy

1. **Unit Tests**: Test each verification method with known valid/invalid steps
2. **Integration Tests**: Run on formalgeo7k_v2 problems with annotated solutions
3. **Error Injection**: Deliberately introduce errors to test deduction accuracy
4. **Theorem Matching**: Test fuzzy matching with various informal names
5. **Edge Cases**: Test incomplete solutions, redundant steps, alternative valid paths
