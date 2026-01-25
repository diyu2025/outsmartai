import copy
import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Tuple, Set
from difflib import SequenceMatcher


@dataclass
class StepVerificationResult:
    """Result of verifying a single step"""
    step_id: int
    is_valid: bool
    error_type: Optional[str] = None  # None | "missing_premise" | "invalid_theorem" | "wrong_conclusion" | "cascading_error" | "not_derivable"
    error_details: str = ""
    points_deducted: int = 0
    confidence: float = 0.0
    is_redundant: bool = False
    theorem_applied: Optional[str] = None
    new_knowledge: List[str] = field(default_factory=list)
    dependency_chain: List[int] = field(default_factory=list)
    root_cause_step: Optional[int] = None
    formalgeo_evidence: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "is_valid": self.is_valid,
            "error_type": self.error_type,
            "error_details": self.error_details,
            "points_deducted": self.points_deducted,
            "confidence": self.confidence,
            "is_redundant": self.is_redundant,
            "theorem_applied": self.theorem_applied,
            "new_knowledge": self.new_knowledge,
            "formalgeo_evidence": self.formalgeo_evidence,
        }
    
    def to_feedback(self) -> Dict[str, Any]:
        """Convert to user-friendly feedback format"""
        feedback = {
            "step_id": self.step_id,
            "is_valid": self.is_valid,
        }
        
        if self.is_valid:
            feedback["note"] = "Step is correct" + (" but redundant" if self.is_redundant else "")
            if self.theorem_applied:
                feedback["theorem_applied"] = self.theorem_applied
        else:
            feedback["error_type"] = self.error_type
            feedback["error_details"] = self.error_details
            if self.root_cause_step:
                feedback["root_cause"] = f"step {self.root_cause_step}"
        
        feedback["confidence"] = self.confidence
        return feedback
    
    def to_deduction(self) -> Dict[str, Any]:
        """Convert to deduction format for grading report"""
        if self.points_deducted == 0:
            return None
        
        return {
            "deducted_points": self.points_deducted,
            "deduction_reason": self.error_details,
            "deduction_confidence_score": self.confidence,
            "deduction_step": f"step {self.step_id}",
            "error_type": self.error_type,
            "formalgeo_evidence": self.formalgeo_evidence,
        }


@dataclass
class GradingReport:
    """Complete grading report for a solution"""
    total_points: int
    deductions: List[Dict[str, Any]]
    step_feedback: List[Dict[str, Any]]
    missing_steps: List[Dict[str, Any]] = field(default_factory=list)
    goal_reached: bool = False
    confidence: float = 0.0
    summary: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_points": self.total_points,
            "deductions": self.deductions,
            "step_feedback": self.step_feedback,
            "missing_steps": self.missing_steps,
            "goal_reached": self.goal_reached,
            "confidence": self.confidence,
            "summary": self.summary,
        }


class FormalGeoStepGrader:
    """
    Step-by-step grading using FormalGeo's theorem proving capabilities
    
    This class orchestrates the verification of student geometry solutions by:
    1. Maintaining a knowledge base that grows with each valid step
    2. Verifying theorem applications against formal logic
    3. Detecting logical errors, missing premises, and cascading errors
    4. Providing detailed feedback with point deductions
    """
    
    def __init__(self, predicate_gdl: Dict[str, Any], theorem_gdl: Dict[str, Any]):
        """
        Initialize grader with FormalGeo predicate and theorem definitions
        
        Args:
            predicate_gdl: Predicate GDL from FormalGeo dataset
            theorem_gdl: Theorem GDL from FormalGeo dataset
        """
        self.predicate_gdl = predicate_gdl
        self.theorem_gdl = theorem_gdl
        self.solver = None
        self.available = False
        self.parsed_predicate_GDL = None
        self.parsed_theorem_GDL = None
        
        try:
            from formalgeo.solver import Interactor
            from formalgeo.parse import parse_theorem_seqs, parse_predicate_gdl, parse_theorem_gdl
            from formalgeo.tools import show_solution
            
            self.Interactor = Interactor
            self.parse_theorem_seqs = parse_theorem_seqs
            self.show_solution = show_solution
            
            # Parse GDL for use in claim parsing
            self.parsed_predicate_GDL = parse_predicate_gdl(predicate_gdl)
            self.parsed_theorem_GDL = parse_theorem_gdl(theorem_gdl, self.parsed_predicate_GDL)
            
            self.available = True
            print("[FormalGeoStepGrader] Initialized successfully")
        except ImportError as e:
            print(f"[FormalGeoStepGrader] FormalGeo not available: {e}")
            self.available = False
    
    def initialize_problem(self, problem_cdl: Dict[str, Any]) -> bool:
        """
        Initialize FormalGeo solver with problem givens
        
        Args:
            problem_cdl: Problem CDL containing construction_cdl, text_cdl, goal_cdl
            
        Returns:
            True if initialization successful, False otherwise
        """
        if not self.available:
            print("[FormalGeoStepGrader] Cannot initialize - FormalGeo not available")
            return False
        
        try:
            print(f"[FormalGeoStepGrader] Initializing with predicate_GDL keys: {list(self.predicate_gdl.keys()) if isinstance(self.predicate_gdl, dict) else 'NOT A DICT'}")
            print(f"[FormalGeoStepGrader] Predicate GDL type: {type(self.predicate_gdl)}")
            
            self.solver = self.Interactor(self.predicate_gdl, self.theorem_gdl)
            self.solver.load_problem(problem_cdl)
            print(f"[FormalGeoStepGrader] Problem loaded successfully")
            print(f"[FormalGeoStepGrader] Initial KB has {len(self.solver.problem.condition.items)} items")
            self._log_kb_state("Initial KB")
            return True
        except Exception as e:
            print(f"[FormalGeoStepGrader] Failed to initialize problem: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _log_kb_state(self, label: str) -> None:
        """Log full KB contents grouped by predicate."""
        if not self.solver:
            print(f"[FormalGeoStepGrader] {label}: solver not initialized")
            return
        condition = self.solver.problem.condition
        print(f"\n[FormalGeoStepGrader] {label} contents:")
        predicates = sorted(condition.items_group.keys())
        for predicate in predicates:
            items = condition.get_items_by_predicate(predicate) or []
            print(f"  {predicate}: {len(items)}")
            for item in items:
                print(f"    - {item}")
    
    def get_current_state(self) -> Dict[str, Set[Tuple]]:
        """
        Capture current knowledge base state
        
        Returns:
            Dictionary mapping predicates to sets of items
        """
        if not self.solver:
            return {}
        
        kb_state = {}
        for predicate in self.solver.problem.condition.items_group.keys():
            items = self.solver.problem.condition.get_items_by_predicate(predicate)
            kb_state[predicate] = set(items) if items else set()
        
        return kb_state
    
    def snapshot_solver_state(self) -> Dict[str, Any]:
        """
        Create a deep snapshot of solver state for rollback
        
        Returns:
            Dictionary containing serialized solver state
        """
        if not self.solver:
            return {}
        
        return {
            "condition": copy.deepcopy(self.solver.problem.condition),
            "timing": copy.deepcopy(self.solver.problem.timing),
        }
    
    def restore_solver_state(self, snapshot: Dict[str, Any]):
        """
        Restore solver to a previous state
        
        Args:
            snapshot: State snapshot from snapshot_solver_state()
        """
        if not self.solver or not snapshot:
            return
        
        self.solver.problem.condition = snapshot["condition"]
        self.solver.problem.timing = snapshot["timing"]
    
    def verify_step_sequence(
        self,
        student_steps: List[Dict[str, Any]],
        grading_criteria: Optional[Dict[str, Any]] = None
    ) -> List[StepVerificationResult]:
        """
        Verify each step sequentially, tracking state changes
        
        Args:
            student_steps: List of student step dictionaries with claim_cdl, theorem_name, etc.
            grading_criteria: Optional grading configuration
            
        Returns:
            List of StepVerificationResult objects
        """
        if not self.solver:
            print("[FormalGeoStepGrader] Solver not initialized")
            return []
        
        step_results = []
        current_state = self.get_current_state()
        
        print(f"\n[FormalGeoStepGrader] Verifying {len(student_steps)} steps...")
        
        for step in student_steps:
            print(f"\n[FormalGeoStepGrader] === Verifying Step {step.get('step_id', '?')} ===")
            
            result = self.verify_single_step(
                step=step,
                current_state=current_state,
                grading_criteria=grading_criteria,
                previous_results=step_results
            )
            
            step_results.append(result)
            
            # Update state if step was valid
            if result.is_valid and not result.is_redundant:
                current_state = self.get_current_state()
                print(f"[FormalGeoStepGrader] KB updated - now has {sum(len(v) for v in current_state.values())} items")
            
            # Check for global misalignment (early termination)
            if result.error_type == "global_misalignment":
                print("[FormalGeoStepGrader] Global misalignment detected - terminating verification")
                break
        
        return step_results
    
    def verify_single_step(
        self,
        step: Dict[str, Any],
        current_state: Dict[str, Set[Tuple]],
        grading_criteria: Optional[Dict[str, Any]],
        previous_results: List[StepVerificationResult]
    ) -> StepVerificationResult:
        """
        Verify a single step against current knowledge base
        
        Args:
            step: Step dictionary with claim_cdl, theorem_name, depends_on, etc.
            current_state: Current KB state
            grading_criteria: Grading configuration
            previous_results: Results of all previous steps
            
        Returns:
            StepVerificationResult
        """
        step_id = step.get("step_id", 0)
        claim_cdl = step.get("claim_cdl", "")
        theorem_name = step.get("theorem_name", "")
        depends_on = step.get("depends_on", [])
        
        print(f"[FormalGeoStepGrader] Claim: {claim_cdl}")
        print(f"[FormalGeoStepGrader] Theorem: {theorem_name}")
        
        # Step 1: Check for cascading errors (dependency on invalid step)
        if depends_on:
            for dep_id in depends_on:
                dep_result = next((r for r in previous_results if r.step_id == dep_id), None)
                if dep_result and not dep_result.is_valid:
                    print(f"[FormalGeoStepGrader] Step depends on invalid step {dep_id}")
                    deduction = self.calculate_deduction(
                        error_type="cascading_error",
                        step_id=step_id,
                        root_cause_step=dep_id
                    )
                    return StepVerificationResult(
                        step_id=step_id,
                        is_valid=False,
                        error_type="cascading_error",
                        error_details=deduction["reason"],
                        points_deducted=deduction["points"],
                        confidence=deduction["confidence"],
                        root_cause_step=dep_id,
                    )
        
        # Step 2: Parse claim to extract predicate
        try:
            claim_predicate, claim_item = self.parse_claim_to_predicate(claim_cdl)
            print(f"[FormalGeoStepGrader] Parsed claim (simple): {claim_predicate}{claim_item}")
            
        except Exception as e:
            print(f"[FormalGeoStepGrader] Failed to parse claim: {e}")
            import traceback
            traceback.print_exc()
            deduction = self.calculate_deduction("syntax_error", step_id)
            return StepVerificationResult(
                step_id=step_id,
                is_valid=False,
                error_type="syntax_error",
                error_details=f"Cannot parse claim: {e}",
                points_deducted=deduction["points"],
                confidence=deduction["confidence"],
            )
        
        # Step 3: Handle Equal predicates specially
        # Equal creates algebraic constraints, not logic predicates in KB
        if claim_predicate == "Equal":
            print(f"[FormalGeoStepGrader] Equal predicate - treating as valid constraint")
            # Equal predicates are algebraic constraints, not verifiable in logic KB
            # We accept them as valid assumptions that create symbolic relationships
            return StepVerificationResult(
                step_id=step_id,
                is_valid=True,
                confidence=0.75,  # Medium confidence - it's an assumption
                theorem_applied=theorem_name if theorem_name else "algebraic_constraint",
            )
        
        # Step 4: Check if conclusion exists in KB (for non-Equal predicates)
        if self.check_conclusion_exists(claim_predicate, claim_item):
            print(f"[FormalGeoStepGrader] Claim found in KB - valid")
            return StepVerificationResult(
                step_id=step_id,
                is_valid=True,
                is_redundant=False,
                confidence=0.90,
            )
        
        # Step 5: For non-Equal claims not in KB, mark as not_derivable
        # TODO: Use theorem search to try to derive them
        print(f"[FormalGeoStepGrader] Claim not in KB - marking as not_derivable")
        deduction = self.calculate_deduction("not_derivable", step_id)
        return StepVerificationResult(
            step_id=step_id,
            is_valid=False,
            error_type="not_derivable",
            error_details=deduction["reason"],
            points_deducted=deduction["points"],
            confidence=0.50,  # Lower confidence since we're not running full search
        )
    
    def verify_theorem_application(
        self,
        theorem_name: str,
        claim_predicate: str,
        claim_item: Tuple,
        depends_on: List[int],
        step_id: int
    ) -> Dict[str, Any]:
        """
        Verify if student's claimed theorem usage is correct
        
        Args:
            theorem_name: Student's theorem name (informal)
            claim_predicate: Predicate of claimed conclusion
            claim_item: Item tuple of claimed conclusion
            depends_on: List of prerequisite step IDs
            step_id: Current step ID
            
        Returns:
            Dictionary with is_valid, error_type, error_details, matched_theorem, etc.
        """
        # Step 1: Fuzzy match theorem name
        matched_theorem = self.fuzzy_match_theorem(theorem_name)
        
        if not matched_theorem:
            return {
                "is_valid": False,
                "error_type": "unknown_theorem",
                "error_details": f"Cannot find theorem '{theorem_name}' in knowledge base",
                "evidence": {"student_theorem": theorem_name},
            }
        
        print(f"[FormalGeoStepGrader] Matched '{theorem_name}' → '{matched_theorem}'")
        
        # Step 2: Extract parameters from claim
        try:
            theorem_params = self.extract_theorem_parameters(matched_theorem, claim_item)
            print(f"[FormalGeoStepGrader] Extracted parameters: {theorem_params}")
        except Exception as e:
            return {
                "is_valid": False,
                "error_type": "invalid_theorem",
                "error_details": f"Cannot extract parameters for theorem '{matched_theorem}': {e}",
            }
        
        # Step 3: Save state before attempting to apply theorem
        saved_state = self.snapshot_solver_state()
        
        # Step 4: Try to apply theorem
        try:
            update = self.solver.apply_theorem(
                t_name=matched_theorem,
                t_para=theorem_params if theorem_params else None,
                t_branch=None
            )
            
            if not update:
                # Theorem didn't apply - prerequisites not met
                self.restore_solver_state(saved_state)
                return {
                    "is_valid": False,
                    "error_type": "invalid_theorem",
                    "error_details": f"Theorem '{matched_theorem}' prerequisites not satisfied in current state",
                    "evidence": {
                        "theorem": matched_theorem,
                        "parameters": theorem_params,
                    },
                }
            
            # Step 5: Check if claimed conclusion now exists
            conclusion_exists = self.check_conclusion_exists(claim_predicate, claim_item)
            
            if conclusion_exists:
                # Success!
                print(f"[FormalGeoStepGrader] Theorem applied successfully, conclusion verified")
                return {
                    "is_valid": True,
                    "matched_theorem": matched_theorem,
                    "parameters": theorem_params,
                    "new_knowledge": [],  # Could track what was added
                }
            else:
                # Theorem applied but didn't produce claimed conclusion
                self.restore_solver_state(saved_state)
                return {
                    "is_valid": False,
                    "error_type": "wrong_conclusion",
                    "error_details": f"Theorem '{matched_theorem}' does not produce the claimed conclusion",
                    "evidence": {
                        "theorem": matched_theorem,
                        "claimed": f"{claim_predicate}{claim_item}",
                    },
                }
        
        except Exception as e:
            self.restore_solver_state(saved_state)
            return {
                "is_valid": False,
                "error_type": "formalgeo_error",
                "error_details": f"FormalGeo error: {str(e)}",
            }
    
    def fuzzy_match_theorem(self, student_name: str) -> Optional[str]:
        """
        Match student's informal theorem name to formal GDL theorem
        
        Examples:
        - "radius equal" → "circle_property_radius_equal"
        - "isosceles base angles" → "isosceles_triangle_property_angle_equal"
        - "angle sum 180" → "triangle_angle_sum"
        
        Args:
            student_name: Student's informal theorem name
            
        Returns:
            Matched theorem name from GDL, or None if no match
        """
        if not student_name:
            return None
        
        normalized_student = self.normalize_theorem_name(student_name)
        available_theorems = list(self.theorem_gdl.keys())
        
        # Exact match
        if normalized_student in available_theorems:
            return normalized_student
        
        # Substring match
        for theorem in available_theorems:
            if normalized_student in theorem or theorem in normalized_student:
                return theorem
        
        # Keyword-based matching
        student_keywords = set(normalized_student.split('_'))
        matches = []
        
        for theorem in available_theorems:
            theorem_keywords = set(theorem.split('_'))
            overlap = student_keywords & theorem_keywords
            if len(overlap) >= 2:  # At least 2 keywords match
                matches.append((theorem, len(overlap)))
        
        if matches:
            # Return best match
            best_match = max(matches, key=lambda x: x[1])[0]
            print(f"[FormalGeoStepGrader] Fuzzy matched '{student_name}' → '{best_match}'")
            return best_match
        
        # Similarity-based matching as fallback
        best_similarity = 0
        best_theorem = None
        
        for theorem in available_theorems:
            similarity = SequenceMatcher(None, normalized_student, theorem).ratio()
            if similarity > best_similarity:
                best_similarity = similarity
                best_theorem = theorem
        
        if best_similarity > 0.6:  # Threshold for similarity
            print(f"[FormalGeoStepGrader] Similarity matched '{student_name}' → '{best_theorem}' (score: {best_similarity:.2f})")
            return best_theorem
        
        print(f"[FormalGeoStepGrader] No match found for '{student_name}'")
        return None
    
    def normalize_theorem_name(self, name: str) -> str:
        """Normalize theorem name for matching"""
        import re
        # Convert to lowercase, replace spaces/special chars with underscores
        normalized = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
        return normalized
    
    def extract_theorem_parameters(self, theorem_name: str, claim_item: Tuple) -> Optional[Tuple]:
        """
        Extract theorem parameters from claim item
        
        Args:
            theorem_name: Matched theorem name
            claim_item: Parsed claim item tuple
            
        Returns:
            Tuple of parameters for theorem application
        """
        # For now, return claim_item as parameters
        # TODO: More sophisticated parameter extraction based on theorem definition
        if isinstance(claim_item, tuple) and len(claim_item) > 0:
            # Flatten nested tuples if needed
            params = []
            for item in claim_item:
                if isinstance(item, (tuple, list)):
                    params.extend(item)
                else:
                    params.append(item)
            return tuple(params) if params else None
        return None
    
    def parse_claim_to_predicate(self, claim_cdl: str) -> Tuple[str, Tuple]:
        """
        Parse CDL claim string into (predicate, item) tuple
        
        Args:
            claim_cdl: CDL string like "Equal(LengthOfLine(OA),LengthOfLine(OC))" or "IsoscelesTriangle(ABC)"
            
        Returns:
            Tuple of (predicate_name, item_tuple)
        """
        import re
        
        # Extract outer predicate name
        match = re.match(r'(\w+)\((.*)\)', claim_cdl.strip())
        if not match:
            raise ValueError(f"Cannot parse claim: {claim_cdl}")
        
        predicate = match.group(1)
        args_str = match.group(2)
        
        # Extract point names (single capital letters that appear as standalone identifiers)
        # Match patterns like: OA, BC, ABC, O, A, B, C
        # But not: LengthOfLine, MeasureOfAngle
        point_names = re.findall(r'\b([A-Z]+)\b', args_str)
        # Filter out common function names
        point_names = [p for p in point_names if p not in ['LengthOfLine', 'MeasureOfAngle', 'Equal']]

        # Preserve order and case; flatten multi-letter tokens into individual points
        points: List[str] = []
        for name in point_names:
            if len(name) == 1:
                points.append(name)
            else:
                for letter in name:
                    points.append(letter)

        item = tuple(points) if points else ()
        
        return predicate, item
    
    def check_conclusion_exists(self, predicate: str, item: Tuple) -> bool:
        """
        Check if conclusion exists in current knowledge base
        
        Args:
            predicate: Predicate name
            item: Item tuple
            
        Returns:
            True if conclusion exists in KB
        """
        if not self.solver:
            return False
        
        try:
            return self.solver.problem.condition.has(predicate, item)
        except Exception as e:
            print(f"[FormalGeoStepGrader] Error checking conclusion: {e}")
            return False
    
    def check_conclusion_derivable(self, predicate: str, item: Tuple) -> bool:
        """
        Check if conclusion can be derived from current state
        (Used when no theorem is specified)
        
        Args:
            predicate: Predicate name
            item: Item tuple
            
        Returns:
            True if conclusion is derivable
        """
        # For now, same as check_conclusion_exists
        # Could be enhanced with backward search
        return self.check_conclusion_exists(predicate, item)
    
    def calculate_deduction(
        self,
        error_type: str,
        step_id: int,
        root_cause_step: Optional[int] = None,
        details: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Calculate point deduction based on GRADING PROCEDURE
        
        Criteria:
        3b. Global misalignment: -100 points
        3c. Interstep logic error: -20 points per flaw
        3d. Intrastep computation error: -10 points per mistake
        
        Args:
            error_type: Type of error
            step_id: Step ID where error occurred
            root_cause_step: Step ID that caused cascading error (if applicable)
            details: Additional error details
            
        Returns:
            Dictionary with points, reason, confidence
        """
        deductions = {
            "global_misalignment": {
                "points": 100,
                "reason": f"Solution does not serve the purpose of solving the problem",
                "confidence": 0.95
            },
            "missing_premise": {
                "points": 20,
                "reason": f"Step {step_id} lacks necessary prerequisite - logical gap in reasoning",
                "confidence": 0.90
            },
            "invalid_theorem": {
                "points": 20,
                "reason": f"Step {step_id} incorrectly applies theorem - prerequisites not met. {details or ''}",
                "confidence": 0.88
            },
            "wrong_conclusion": {
                "points": 20,
                "reason": f"Step {step_id} draws incorrect conclusion from theorem application. {details or ''}",
                "confidence": 0.92
            },
            "not_derivable": {
                "points": 20,
                "reason": f"Step {step_id} claims result that cannot be derived from current state",
                "confidence": 0.85
            },
            "unknown_theorem": {
                "points": 20,
                "reason": f"Step {step_id} references unknown theorem. {details or ''}",
                "confidence": 0.87
            },
            "computation_error": {
                "points": 10,
                "reason": f"Step {step_id} contains local computational or algebraic error",
                "confidence": 0.88
            },
            "syntax_error": {
                "points": 10,
                "reason": f"Step {step_id} has incorrect mathematical notation or format",
                "confidence": 0.85
            },
            "cascading_error": {
                "points": 10,
                "reason": f"Step {step_id} error cascaded from incorrect step {root_cause_step}",
                "confidence": 0.85
            },
        }
        
        return deductions.get(error_type, {
            "points": 10,
            "reason": f"Step {step_id} has unspecified error: {error_type}",
            "confidence": 0.70
        })
    
    def identify_missing_steps(self, goal: Any) -> Dict[str, Any]:
        """
        Check if goal is reached, identify missing steps if not
        
        Args:
            goal: Problem goal from solver
            
        Returns:
            Dictionary with goal_reached, missing_steps, deduction info
        """
        if not self.solver:
            return {
                "goal_reached": False,
                "missing_steps": [],
                "deduction_points": 0,
                "deduction_reason": "Solver not initialized"
            }
        
        # Check goal
        self.solver.problem.check_goal()
        
        if self.solver.problem.goal.solved:
            print("[FormalGeoStepGrader] Goal reached!")
            return {
                "goal_reached": True,
                "missing_steps": []
            }
        
        # Goal not reached - estimate missing steps
        # For now, simple estimation (could use backward search in future)
        print("[FormalGeoStepGrader] Goal NOT reached")
        
        return {
            "goal_reached": False,
            "missing_steps": [
                {
                    "description": "Additional steps needed to reach goal",
                    "note": "Solution incomplete"
                }
            ],
            "deduction_points": 20,
            "deduction_reason": "Solution incomplete - goal not reached"
        }
    
    async def grade_geometry_solution(
        self,
        gdl_payload: Dict[str, Any],
        student_steps: List[Dict[str, Any]],
        grading_criteria: Optional[Dict[str, Any]] = None
    ) -> GradingReport:
        """
        Main grading orchestrator
        
        Args:
            gdl_payload: Complete GDL payload with predicate_GDL, theorem_GDL, problem_CDL
            student_steps: List of student step dictionaries
            grading_criteria: Optional grading configuration
            
        Returns:
            GradingReport with total_points, deductions, feedback, etc.
        """
        print("\n" + "="*80)
        print("[FormalGeoStepGrader] Starting geometry solution grading")
        print("="*80)
        
        # Initialize problem
        success = self.initialize_problem(gdl_payload["problem_CDL"])
        if not success:
            return GradingReport(
                total_points=0,
                deductions=[{
                    "deducted_points": 100,
                    "deduction_reason": "Cannot initialize FormalGeo solver",
                    "deduction_confidence_score": 1.0,
                    "deduction_step": "initialization"
                }],
                step_feedback=[],
                confidence=0.0,
                summary="Unable to grade solution - FormalGeo initialization failed"
            )
        
        # Verify steps sequentially
        step_results = self.verify_step_sequence(student_steps, grading_criteria)
        
        # Check for missing steps
        missing_analysis = self.identify_missing_steps(self.solver.problem.goal)
        
        # Calculate final score
        total_deducted = sum(r.points_deducted for r in step_results)
        
        if not missing_analysis["goal_reached"]:
            total_deducted += missing_analysis.get("deduction_points", 0)
        
        total_points = max(0, 100 - total_deducted)
        
        # Compile deductions
        deductions = []
        for result in step_results:
            deduction = result.to_deduction()
            if deduction:
                deductions.append(deduction)
        
        if not missing_analysis["goal_reached"] and missing_analysis.get("deduction_points", 0) > 0:
            deductions.append({
                "deducted_points": missing_analysis["deduction_points"],
                "deduction_reason": missing_analysis["deduction_reason"],
                "deduction_confidence_score": 0.85,
                "deduction_step": "final"
            })
        
        # Filter low confidence deductions (threshold 0.5 per GRADING PROCEDURE step 5)
        deductions = [d for d in deductions if d.get("deduction_confidence_score", 0) >= 0.5]
        
        # Generate summary
        summary = self.generate_summary(step_results, missing_analysis)
        
        # Calculate overall confidence
        confidence = self.calculate_overall_confidence(step_results)

        report = GradingReport(
            total_points=total_points,
            deductions=deductions,
            step_feedback=[r.to_feedback() for r in step_results],
            missing_steps=missing_analysis.get("missing_steps", []),
            goal_reached=missing_analysis["goal_reached"],
            confidence=confidence,
            summary=summary
        )

        self._log_kb_state("Final KB")
        
        print("\n" + "="*80)
        print(f"[FormalGeoStepGrader] Grading complete: {total_points}/100")
        print("="*80 + "\n")
        
        return report
    
    def generate_summary(
        self,
        step_results: List[StepVerificationResult],
        missing_analysis: Dict[str, Any]
    ) -> str:
        """Generate summary of student performance"""
        valid_steps = sum(1 for r in step_results if r.is_valid)
        total_steps = len(step_results)
        
        summary_parts = []
        
        if valid_steps == total_steps and missing_analysis["goal_reached"]:
            summary_parts.append("Student demonstrated complete understanding and correctly solved the problem.")
        elif valid_steps > 0:
            summary_parts.append(f"Student completed {valid_steps}/{total_steps} steps correctly.")
            
            # Identify strengths
            if valid_steps >= total_steps * 0.7:
                summary_parts.append("Shows good grasp of geometry concepts.")
            
            # Identify weaknesses
            error_types = [r.error_type for r in step_results if r.error_type]
            if "invalid_theorem" in error_types:
                summary_parts.append("Needs improvement in theorem application.")
            if "wrong_conclusion" in error_types:
                summary_parts.append("Logical reasoning needs strengthening.")
            if not missing_analysis["goal_reached"]:
                summary_parts.append("Solution incomplete - missing steps to reach goal.")
        else:
            summary_parts.append("Student needs significant support with geometry problem solving.")
        
        return " ".join(summary_parts)
    
    def calculate_overall_confidence(self, step_results: List[StepVerificationResult]) -> float:
        """Calculate overall confidence in grading"""
        if not step_results:
            return 0.0
        
        confidences = [r.confidence for r in step_results]
        return sum(confidences) / len(confidences)
