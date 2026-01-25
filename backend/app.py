#!/usr/bin/env python3

import os
import io
import base64
import re
import json
import asyncio
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Dict, List, Any, Optional, Tuple
from flask import Flask, request, jsonify
from flask_cors import CORS
from PIL import Image
from dotenv import load_dotenv, find_dotenv

# Load environment variables (search up the directory tree so running from `backend/` still finds repo-root `.env`)
load_dotenv(find_dotenv())

app = Flask(__name__)
CORS(app)

# Configuration
LLM_PROVIDER = os.getenv('LLM_PROVIDER', 'mock')
LLM_API_KEY = os.getenv('LLM_API_KEY')

# Unified data protocol models -------------------------------------------------


@dataclass
class Step:
    step_id: int
    raw_text: str
    normalized_text: str
    tokens: List[str]
    span_refs: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Claim:
    claim_id: str
    type: str
    args: List[str]
    depends_on: List[str]
    evidence: Dict[str, Any]
    confidence_hint: str = "medium"
    source: str = "student"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class VerificationResult:
    claim_id: str
    verdict: str  # true|false|unknown
    reason_code: str
    missing: List[str]
    used_facts: List[str]
    proof_trace: List[str]
    evidence_strength: str = "weak"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RubricItem:
    rubric_item_id: str
    description: str
    linked_claims: List[str]
    max_score: int
    partial_score: int


@dataclass
class RubricScore:
    rubric_item_id: str
    earned: int
    max: int
    linked_claims: List[str]
    notes: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


class StepExtractorAgent:
    """A1. Step Extractor Agent (LLM-driven)"""

    SYS_PROMPT = """
You are A1 Step Extractor Agent in a grading pipeline. Given a math problem description, student drawing description, and the student's full answer text, extract an ordered list of granular steps.
Return STRICT JSON with fields:
{
  "steps": [
    {"step_id": int, "raw_text": string, "normalized_text": string, "tokens": [string], "span_refs": [{"source":"student_text","start":int,"end":int}]}
  ],
  "symbols_map": {"symbol": [step_ids]}
}
- Keep original wording in raw_text; normalized_text should be lightly cleaned.
- Do NOT invent steps; only split what exists.
- Tokens should keep math tokens (e.g., ∠ACB, OA, x, y, =, +).
    """.strip()

    def __init__(self, llm_service: "LLMService"):
        self.llm_service = llm_service

    async def run(self, text_description: str, drawing_description: str, image_data: Optional[bytes]) -> Tuple[List[Step], Dict[str, List[int]]]:
        messages = [
            {"role": "system", "content": self.SYS_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "problem_and_solution_text": text_description,
                        "drawing_description": drawing_description,
                    }
                ),
            },
        ]
        llm_resp = await self.llm_service.chat(messages, image_data=image_data)
        result = self._parse_steps(llm_resp)
        print("\n" + "="*80)
        print("[A1] StepExtractorAgent Output:")
        print(f"Extracted {len(result[0])} steps")
        for step in result[0]:
            print(f"  Step {step.step_id}: {step.raw_text}")
        print(f"Symbol map: {result[1]}")
        print("="*80 + "\n")
        return result

    def _parse_steps(self, llm_resp: Any) -> Tuple[List[Step], Dict[str, List[int]]]:
        payload = llm_resp if isinstance(llm_resp, dict) else {}
        raw_steps = payload.get("steps", [])
        steps: List[Step] = []
        symbol_map: Dict[str, List[int]] = payload.get("symbols_map", {})
        for item in raw_steps:
            try:
                step = Step(
                    step_id=int(item.get("step_id")),
                    raw_text=item.get("raw_text", ""),
                    normalized_text=item.get("normalized_text") or _normalize_text(item.get("raw_text", "")),
                    tokens=item.get("tokens", []),
                    span_refs=item.get("span_refs", []),
                )
                steps.append(step)
            except Exception:
                continue
        # Fallback if LLM returns nothing
        if not steps and isinstance(llm_resp, str):
            lines = [line.strip() for line in llm_resp.splitlines() if line.strip()]
            for idx, line in enumerate(lines, start=1):
                steps.append(
                    Step(
                        step_id=idx,
                        raw_text=line,
                        normalized_text=_normalize_text(line),
                        tokens=re.findall(r"[A-Za-z]+|∠[A-Za-z]+|[0-9]+|[=+\\-*/]+", line),
                        span_refs=[{"source": "student_text", "start": 0, "end": len(line)}],
                    )
                )
        return steps, symbol_map


class ClaimGeneratorAgent:
    """A2. Claim Generator Agent (LLM-driven)"""

    SYS_PROMPT = """
You are A2 Claim Generator Agent. Convert student steps plus problem givens into atomic, verifiable claims.
Return STRICT JSON:
{
  "givens": [...],               // carry through official givens (do not invent)
  "student_diagram_claims": [...], // claims drawn/assumed by student diagram, mark with depends_on=[]
  "claims": [                    // per-step atomic claims for verification
    {"claim_id": str, "type": str, "args": [str], "depends_on": [str], "evidence": {"from_step": int}, "confidence_hint": "low|medium|high"}
  ]
}
Rules:
- Claim IDs should be deterministic: use S{step_id}C{index}.
- Keep givens untouched; do NOT hallucinate new givens.
- If a claim relies on a student-added construction, set depends_on to the relevant student_diagram_claim IDs.
- Prefer primitive predicates: RADIUS_EQUAL, ISOSCELES_BASE_ANGLES, ANGLE_SUM, ANGLE_SUM_180, RIGHT_ANGLE, PARALLEL, PERPENDICULAR, COLLINEAR, etc.
    """.strip()

    def __init__(self, llm_service: "LLMService", givens_registry: Dict[str, List[Claim]]):
        self.llm_service = llm_service
        self.givens_registry = givens_registry

    async def run(
        self,
        problem_id: str,
        steps: List[Step],
        student_modified_drawing_description: Optional[str] = None,
        image_data: Optional[bytes] = None,
    ) -> Dict[str, List[Claim]]:
        givens = [g.to_dict() for g in self.givens_registry.get(problem_id, [])]
        messages = [
            {"role": "system", "content": self.SYS_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "problem_id": problem_id,
                        "givens": givens,
                        "steps": [s.to_dict() for s in steps],
                        "student_modified_drawing_description": student_modified_drawing_description,
                    }
                ),
            },
        ]
        llm_resp = await self.llm_service.chat(messages, image_data=image_data)
        result = self._parse_claims(llm_resp, problem_id)
        print("\n" + "="*80)
        print("[A2] ClaimGeneratorAgent Output:")
        print(f"Givens: {len(result['givens'])} claims")
        for claim in result['givens']:
            print(f"  {claim.claim_id}: {claim.type} {claim.args}")
        print(f"Student diagram claims: {len(result['student_diagram_claims'])} claims")
        for claim in result['student_diagram_claims']:
            print(f"  {claim.claim_id}: {claim.type} {claim.args}")
        print(f"Student claims: {len(result['claims'])} claims")
        for claim in result['claims']:
            print(f"  {claim.claim_id}: {claim.type} {claim.args} (depends_on: {claim.depends_on})")
        print("="*80 + "\n")
        return result

    def _parse_claims(self, llm_resp: Any, problem_id: str) -> Dict[str, List[Claim]]:
        payload = llm_resp if isinstance(llm_resp, dict) else {}
        claims_list: List[Claim] = []
        student_diagram_claims_list: List[Claim] = []

        for claim_dict in payload.get("claims", []):
            try:
                claims_list.append(
                    Claim(
                        claim_id=str(claim_dict.get("claim_id")),
                        type=str(claim_dict.get("type")),
                        args=claim_dict.get("args", []),
                        depends_on=claim_dict.get("depends_on", []),
                        evidence=claim_dict.get("evidence", {}),
                        confidence_hint=claim_dict.get("confidence_hint", "medium"),
                        source=claim_dict.get("source", "student"),
                    )
                )
            except Exception:
                continue

        for claim_dict in payload.get("student_diagram_claims", []):
            try:
                student_diagram_claims_list.append(
                    Claim(
                        claim_id=str(claim_dict.get("claim_id")),
                        type=str(claim_dict.get("type")),
                        args=claim_dict.get("args", []),
                        depends_on=claim_dict.get("depends_on", []),
                        evidence=claim_dict.get("evidence", {}),
                        confidence_hint=claim_dict.get("confidence_hint", "low"),
                        source="student_diagram",
                    )
                )
            except Exception:
                continue

        # Attach givens from registry if LLM omitted
        givens = self.givens_registry.get(problem_id, [])

        return {
            "givens": givens,
            "student_diagram_claims": student_diagram_claims_list,
            "claims": claims_list,
        }


class FormalGeoVerifier:
    """H1-Geo using FormalGeo/FGPS APIs when available."""

    def __init__(self, llm_service: "LLMService"):
        self.formalizer = GeometryFormalizerAgent(llm_service)
        try:
            from formalgeo.solver import Interactor  # type: ignore

            self.Interactor = Interactor
            self.available = True
        except Exception as e:
            print(f"FormalGeo not available: {e}")
            self.available = False
            self.Interactor = None

    async def formalize(
        self,
        text_description: str,
        drawing_description: str,
        image_data: Optional[bytes],
        claims: Optional[List[Claim]] = None,
        givens: Optional[List[Claim]] = None,
        student_diagram_claims: Optional[List[Claim]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not self.available:
            return None
        result = await self.formalizer.run(
            text_description,
            drawing_description,
            image_data,
            claims=claims,
            givens=givens,
            student_diagram_claims=student_diagram_claims,
        )
        print("\n" + "="*80)
        print("[GeometryFormalizerAgent] Output:")
        print(f"construction_cdl: {result.get('construction_cdl', [])}")
        print(f"text_cdl: {result.get('text_cdl', [])}")
        print(f"claim_cdl: {result.get('claim_cdl', [])}")
        print(f"goal_cdl: {result.get('goal_cdl')}")
        print("="*80 + "\n")
        return result

    def verify(self, gdl_payload: Optional[Dict[str, Any]], claim: Claim) -> VerificationResult:
        if not self.available:
            return self._unknown(claim, "FORMALGEO_NOT_AVAILABLE")

        if not gdl_payload or not all(k in gdl_payload for k in ["predicate_GDL", "theorem_GDL", "problem_CDL"]):
            return self._unknown(claim, "MISSING_GDL")

        try:
            solver = self._build_solver(gdl_payload)
            if solver is None or solver.problem is None:
                return self._unknown(claim, "FORMALGEO_INIT_FAILED")

            mapping = self._claim_to_predicate_item(claim)
            if not mapping:
                return self._unknown(claim, "FORMALGEO_MAPPING_UNSUPPORTED")

            predicate, item = mapping
            exists = solver.problem.condition.has(predicate, item)
            return VerificationResult(
                claim_id=claim.claim_id,
                verdict="true" if exists else "unknown",
                reason_code="ENTAILS" if exists else "NOT_DERIVABLE",
                missing=[] if exists else ["Predicate not derivable"],
                used_facts=[],
                proof_trace=[],
                evidence_strength="strong" if exists else "weak",
            )
        except Exception as e:
            return self._unknown(claim, f"FORMALGEO_ERROR: {e}")

    def _build_solver(self, gdl_payload: Dict[str, Any]):
        try:
            interactor = self.Interactor(gdl_payload["predicate_GDL"], gdl_payload["theorem_GDL"])
            interactor.load_problem(gdl_payload["problem_CDL"])
            return interactor
        except Exception as e:
            print(f"FormalGeo solver init failed: {e}")
            return None

    # may use LLM to do the claim to predicate convertion.
    def _claim_to_predicate_item(self, claim: Claim) -> Optional[Tuple[str, Any]]:
        # Minimal adapter: map common claim types to FormalGeo predicates
        if claim.type == "RADIUS_EQUAL":
            args = [tuple(a) if isinstance(a, (list, tuple)) else (a,) for a in claim.args]
            if len(args) >= 2:
                return "Equal", tuple((("LengthOfLine", seg) for seg in args[:2]))
        if claim.type == "ANGLE_SUM":
            return None
        if claim.type == "RIGHT_ANGLE":
            arg = claim.args[0] if claim.args else None
            if arg and len(arg) >= 3:
                return "RightTriangle", tuple(arg[:3])
        return None

    def _unknown(self, claim: Claim, reason: str) -> VerificationResult:
        return VerificationResult(
            claim_id=claim.claim_id,
            verdict="unknown",
            reason_code=reason,
            missing=[],
            used_facts=[],
            proof_trace=[],
            evidence_strength="weak",
        )


class AlgebraVerifier:
    """H1-Alg stub; returns unknown with precondition awareness."""

    SUPPORTED_TYPES = {"ANGLE_SUM_180"}

    def verify(self, claim: Claim, verified: Dict[str, VerificationResult]) -> VerificationResult:
        dependencies_ok = all(
            verified.get(dep) and verified[dep].verdict == "true" for dep in claim.depends_on
        ) if claim.depends_on else True

        if dependencies_ok:
            return VerificationResult(
                claim_id=claim.claim_id,
                verdict="unknown",
                reason_code="NOT_IMPLEMENTED",
                missing=[],
                used_facts=claim.depends_on,
                proof_trace=[],
                evidence_strength="weak",
            )
        return VerificationResult(
            claim_id=claim.claim_id,
            verdict="unknown",
            reason_code="MISSING_PRECONDITION",
            missing=claim.depends_on,
            used_facts=[],
            proof_trace=[],
            evidence_strength="weak",
        )


class MathVerifier:
    """H1 Router -> Geo/Alg plugins with FormalGeo step-by-step grading"""

    def __init__(self, llm_service: "LLMService"):
        self.geo = FormalGeoVerifier(llm_service)
        self.alg = AlgebraVerifier()
        
        # Initialize FormalGeo step grader
        try:
            from graders.formalgeo_grader import FormalGeoStepGrader
            self.step_grader = None  # Will be initialized per problem
            self.FormalGeoStepGrader = FormalGeoStepGrader
            self.step_grading_available = True
            print("[MathVerifier] FormalGeo step grading enabled")
        except ImportError as e:
            print(f"[MathVerifier] FormalGeo step grading not available: {e}")
            self.step_grader = None
            self.FormalGeoStepGrader = None
            self.step_grading_available = False

    async def verify_all(
        self,
        givens: List[Claim],
        student_diagram_claims: List[Claim],
        claims: List[Claim],
        text_description: str,
        drawing_description: str,
        image_data: Optional[bytes],
        use_step_grading: bool = True,
    ) -> List[VerificationResult]:
        verified: Dict[str, VerificationResult] = {}
        gdl_payload = await self.geo.formalize(
            text_description,
            drawing_description,
            image_data,
            claims=claims,
            givens=givens,
            student_diagram_claims=student_diagram_claims,
        )

        # NEW: Try step-by-step grading with FormalGeo
        if use_step_grading and self.step_grading_available and gdl_payload:
            if all(k in gdl_payload for k in ["predicate_GDL", "theorem_GDL", "problem_CDL"]):
                print("\n[MathVerifier] Using FormalGeo step-by-step grading")
                try:
                    step_grading_result = await self._grade_with_formalgeo(
                        gdl_payload=gdl_payload,
                        claims=claims,
                        givens=givens,
                        student_diagram_claims=student_diagram_claims
                    )
                    
                    if step_grading_result:
                        # Convert step grading results to VerificationResult format
                        return self._convert_step_grading_to_verification(step_grading_result, claims)
                except Exception as e:
                    print(f"[MathVerifier] Step grading failed: {e}")
                    print("[MathVerifier] Falling back to claim-by-claim verification")

        # Fallback to original claim-by-claim verification
        for claim in givens:
            verified[claim.claim_id] = VerificationResult(
                claim_id=claim.claim_id,
                verdict="true",
                reason_code="GIVEN",
                missing=[],
                used_facts=[],
                proof_trace=[],
                evidence_strength="strong",
            )

        for sd_claim in student_diagram_claims:
            verified[sd_claim.claim_id] = VerificationResult(
                claim_id=sd_claim.claim_id,
                verdict="unknown",
                reason_code="STUDENT_DIAGRAM",
                missing=[],
                used_facts=[],
                proof_trace=[],
                evidence_strength="weak",
            )

        for claim in claims:
            plugin = self._route(claim)
            if isinstance(plugin, FormalGeoVerifier):
                verified[claim.claim_id] = plugin.verify(gdl_payload, claim)
            else:
                verified[claim.claim_id] = plugin.verify(claim, verified)

        print("\n" + "="*80)
        print("[H1] MathVerifier Output:")
        print(f"Total verification results: {len(verified)}")
        for claim_id, result in verified.items():
            print(f"  {claim_id}: {result.verdict} ({result.reason_code})")
        print("="*80 + "\n")
        return list(verified.values())

    async def _grade_with_formalgeo(
        self,
        gdl_payload: Dict[str, Any],
        claims: List[Claim],
        givens: List[Claim],
        student_diagram_claims: List[Claim]
    ) -> Optional[Dict[str, Any]]:
        """
        Use FormalGeo step-by-step grading
        
        Returns:
            Grading report dictionary or None if grading fails
        """
        if not self.FormalGeoStepGrader:
            return None
        
        # Initialize step grader with predicate and theorem GDL
        step_grader = self.FormalGeoStepGrader(
            predicate_gdl=gdl_payload["predicate_GDL"],
            theorem_gdl=gdl_payload["theorem_GDL"]
        )
        
        if not step_grader.available:
            return None
        
        # Use the CDL claims from GeometryFormalizerAgent instead of trying to convert
        claim_cdl_list = gdl_payload.get("claim_cdl", [])
        
        # Convert CDL claims to step format expected by step grader
        student_steps = []
        for i, claim_cdl in enumerate(claim_cdl_list):
            # Try to match CDL to original claims for depends_on info
            original_claim = claims[i] if i < len(claims) else None
            
            step_dict = {
                "step_id": i + 1,
                "claim_cdl": claim_cdl,
                "theorem_name": original_claim.evidence.get("theorem_name", "") if original_claim else "",
                "depends_on": original_claim.depends_on if original_claim and hasattr(original_claim, 'depends_on') else [],
            }
            student_steps.append(step_dict)
        
        print(f"[MathVerifier] Converted {len(student_steps)} CDL claims to steps for FormalGeo grading")
        
        # Run step-by-step grading
        grading_report = await step_grader.grade_geometry_solution(
            gdl_payload=gdl_payload,
            student_steps=student_steps,
            grading_criteria=None
        )
        
        # Store report for later retrieval
        self._last_formalgeo_report = grading_report.to_dict() if grading_report else None
        
        return self._last_formalgeo_report
    
    def _claim_to_cdl(self, claim: Claim) -> str:
        """
        Convert Claim object to CDL format string
        
        Args:
            claim: Claim object
            
        Returns:
            CDL string representation
        """
        # Simple conversion - may need enhancement based on claim types
        claim_type = claim.type
        args = claim.args
        
        # Map claim types to CDL predicates
        type_mapping = {
            "RADIUS_EQUAL": lambda args: f"Equal(LengthOfLine({args[0]}),LengthOfLine({args[1]}))",
            "ISOSCELES_BASE_ANGLES": lambda args: f"IsoscelesTriangle({args[0]})",
            "RIGHT_ANGLE": lambda args: f"Equal(MeasureOfAngle({args[0]}),90)",
            "ANGLE_SUM": lambda args: f"AngleSum({','.join(args)})",
            "PARALLEL": lambda args: f"ParallelBetweenLine({args[0]},{args[1]})",
            "PERPENDICULAR": lambda args: f"PerpendicularBetweenLine({args[0]},{args[1]})",
        }
        
        if claim_type in type_mapping:
            return type_mapping[claim_type](args)
        
        # Default: use claim type as predicate with args
        return f"{claim_type}({','.join(str(a) for a in args)})"
    
    def _convert_step_grading_to_verification(
        self,
        step_grading: Dict[str, Any],
        original_claims: List[Claim]
    ) -> List[VerificationResult]:
        """
        Convert FormalGeo step grading results to VerificationResult format
        
        Args:
            step_grading: Grading report from FormalGeoStepGrader
            original_claims: Original claim objects
            
        Returns:
            List of VerificationResult objects
        """
        verification_results = []
        
        step_feedback = step_grading.get("step_feedback", [])
        
        for i, feedback in enumerate(step_feedback):
            # Find matching claim
            claim = original_claims[i] if i < len(original_claims) else None
            claim_id = claim.claim_id if claim else f"S{feedback['step_id']}"
            
            # Convert to VerificationResult
            result = VerificationResult(
                claim_id=claim_id,
                verdict="true" if feedback["is_valid"] else "false",
                reason_code=feedback.get("error_type", "VERIFIED") if not feedback["is_valid"] else "FORMALGEO_VERIFIED",
                missing=[feedback.get("error_details", "")] if not feedback["is_valid"] else [],
                used_facts=[],
                proof_trace=[feedback.get("theorem_applied", "")] if feedback.get("theorem_applied") else [],
                evidence_strength="strong" if feedback["is_valid"] else "weak"
            )
            verification_results.append(result)
        
        return verification_results

    def _route(self, claim: Claim):
        if claim.type in {"RADIUS_EQUAL", "ISOSCELES_BASE_ANGLES", "ANGLE_SUM", "RIGHT_ANGLE", "TEXT_ASSERTION"}:
            return self.geo
        if claim.type in self.alg.SUPPORTED_TYPES:
            return self.alg
        return self.geo


class RubricScorerAgent:
    """A3. Rubric Scorer Agent (LLM-driven)"""

    SYS_PROMPT = """
You are A3 Rubric Scorer Agent. Given rubric items and verification results (true/false/unknown), assign earned points per item.
Return STRICT JSON:
{
  "scores": [
    {"rubric_item_id": str, "earned": int, "max": int, "linked_claims": [str], "notes": str}
  ],
  "total": int,
  "maximum": int
}
Rules:
- If all linked claims are true: full points.
- If any linked claim is false: zero unless rubric explicitly allows otherwise.
- If all linked claims are unknown/missing: give at most partial_score (provided).
    """.strip()

    def __init__(self, llm_service: "LLMService", rubric_registry: Dict[str, List[RubricItem]]):
        self.llm_service = llm_service
        self.rubric_registry = rubric_registry

    async def run(
        self,
        problem_id: str,
        verification_results: List[VerificationResult],
    ) -> Tuple[List[RubricScore], int, int]:
        rubric_items = self.rubric_registry.get(problem_id, [])
        messages = [
            {"role": "system", "content": self.SYS_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "rubric_items": [asdict(r) for r in rubric_items],
                        "verification_results": [r.to_dict() for r in verification_results],
                    }
                ),
            },
        ]
        llm_resp = await self.llm_service.chat(messages)
        result = self._parse_scores(llm_resp, rubric_items)
        print("\n" + "="*80)
        print("[A3] RubricScorerAgent Output:")
        print(f"Total score: {result[1]}/{result[2]}")
        for score in result[0]:
            print(f"  {score.rubric_item_id}: {score.earned}/{score.max} - {score.notes}")
        print("="*80 + "\n")
        return result

    def _parse_scores(
        self, llm_resp: Any, rubric_items: List[RubricItem]
    ) -> Tuple[List[RubricScore], int, int]:
        payload = llm_resp if isinstance(llm_resp, dict) else {}
        scores: List[RubricScore] = []
        total = 0
        maximum = sum(item.max_score for item in rubric_items)

        for score_dict in payload.get("scores", []):
            try:
                score = RubricScore(
                    rubric_item_id=score_dict.get("rubric_item_id"),
                    earned=int(score_dict.get("earned", 0)),
                    max=int(score_dict.get("max", 0)),
                    linked_claims=score_dict.get("linked_claims", []),
                    notes=score_dict.get("notes", ""),
                )
                scores.append(score)
                total += score.earned
            except Exception:
                continue

        if not scores:
            for item in rubric_items:
                scores.append(
                    RubricScore(
                        rubric_item_id=item.rubric_item_id,
                        earned=item.partial_score,
                        max=item.max_score,
                        linked_claims=item.linked_claims,
                        notes="Fallback partial credit.",
                    )
                )
                total += item.partial_score

        return scores, total, maximum


class RefereeAgent:
    """A4. Referee Agent (LLM-driven)"""

    SYS_PROMPT = """
You are A4 Referee Agent. When grading outputs show disagreement (unknown claims or score mismatch), provide a short adjudication.
Return STRICT JSON:
{
  "referee_needed": bool,
  "notes": string,
  "unknown_claim_ids": [string]
}
Focus on whether missing preconditions could be resolved and whether a cautious override is justified.
    """.strip()

    def __init__(self, llm_service: "LLMService"):
        self.llm_service = llm_service

    async def run(
        self,
        rubric_scores: List[RubricScore],
        verification_results: List[VerificationResult],
        expected_score: Optional[int] = None,
    ) -> Dict[str, Any]:
        unknown_claims = [r for r in verification_results if r.verdict == "unknown"]
        trigger_disagreement = expected_score is not None and sum(rs.earned for rs in rubric_scores) != expected_score

        if not unknown_claims and not trigger_disagreement:
            return {"referee_needed": False, "notes": "No disagreement detected.", "unknown_claim_ids": []}

        messages = [
            {"role": "system", "content": self.SYS_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "rubric_scores": [r.to_dict() for r in rubric_scores],
                        "verification_results": [r.to_dict() for r in verification_results],
                        "expected_score": expected_score,
                    }
                ),
            },
        ]
        llm_resp = await self.llm_service.chat(messages)
        if isinstance(llm_resp, dict):
            result = {
                "referee_needed": bool(llm_resp.get("referee_needed", True)),
                "notes": llm_resp.get("notes", ""),
                "unknown_claim_ids": llm_resp.get("unknown_claim_ids", []),
            }
        else:
            result = {"referee_needed": True, "notes": "Fallback referee: unable to parse response.", "unknown_claim_ids": [r.claim_id for r in unknown_claims]}
        print("\n" + "="*80)
        print("[A4] RefereeAgent Output:")
        print(f"Referee needed: {result['referee_needed']}")
        print(f"Notes: {result['notes']}")
        print(f"Unknown claim IDs: {result['unknown_claim_ids']}")
        print("="*80 + "\n")
        return result


DEFAULT_GIVENS: Dict[str, List[Claim]] = {
    "diameter_right_angle": [
        Claim(
            claim_id="G1",
            type="DIAMETER",
            args=["AB"],
            depends_on=[],
            evidence={"source": "problem"},
            confidence_hint="high",
            source="problem",
        ),
        Claim(
            claim_id="G2",
            type="CENTER",
            args=["O"],
            depends_on=[],
            evidence={"source": "problem"},
            confidence_hint="high",
            source="problem",
        ),
        Claim(
            claim_id="G3",
            type="POINT_ON_CIRCLE",
            args=["C"],
            depends_on=[],
            evidence={"source": "problem"},
            confidence_hint="high",
            source="problem",
        ),
    ]
}

DEFAULT_RUBRICS: Dict[str, List[RubricItem]] = {
    "diameter_right_angle": [
        RubricItem(
            rubric_item_id="R1",
            description="Recognize radii equality / isosceles setup",
            linked_claims=["S1C1", "S2C2"],
            max_score=2,
            partial_score=1,
        ),
        RubricItem(
            rubric_item_id="R2",
            description="Angle split via OC",
            linked_claims=["S4C1"],
            max_score=2,
            partial_score=1,
        ),
        RubricItem(
            rubric_item_id="R3",
            description="Interior angle sum reasoning",
            linked_claims=["S5C1"],
            max_score=2,
            partial_score=1,
        ),
        RubricItem(
            rubric_item_id="R4",
            description="Conclude angle ACB is right angle",
            linked_claims=["S6C1"],
            max_score=2,
            partial_score=1,
        ),
    ]
}


class GradingPipeline:
    """End-to-end orchestrator"""

    def __init__(self, llm_service: "LLMService"):
        self.llm_service = llm_service
        self.step_agent = StepExtractorAgent(llm_service)
        self.claim_agent = ClaimGeneratorAgent(llm_service, DEFAULT_GIVENS)
        self.math_verifier = MathVerifier(llm_service)
        self.rubric_scorer = RubricScorerAgent(llm_service, DEFAULT_RUBRICS)
        self.referee = RefereeAgent(llm_service)

    async def grade(
        self,
        problem_id: str,
        text_description: str,
        drawing_description: str,
        image_data: Optional[bytes],
        student_modified_drawing_description: Optional[str] = None,
        expected_score: Optional[int] = None,
        use_formalgeo: bool = True,
    ) -> Dict[str, Any]:
        steps, symbol_map = await self.step_agent.run(text_description, drawing_description, image_data)
        claim_payload = await self.claim_agent.run(problem_id, steps, student_modified_drawing_description, image_data=image_data)
        
        # NEW: Store formalgeo grading report separately
        formalgeo_report = None
        
        verification_results = await self.math_verifier.verify_all(
            claim_payload["givens"],
            claim_payload["student_diagram_claims"],
            claim_payload["claims"],
            text_description=text_description,
            drawing_description=drawing_description,
            image_data=image_data,
            use_step_grading=use_formalgeo,
        )
        
        # Check if FormalGeo grading was used
        formalgeo_used = any(
            r.reason_code == "FORMALGEO_VERIFIED" 
            for r in verification_results
        )
        
        # If FormalGeo was used, get the detailed report
        if formalgeo_used and hasattr(self.math_verifier, '_last_formalgeo_report'):
            formalgeo_report = self.math_verifier._last_formalgeo_report
        
        # Use FormalGeo score if available, otherwise use rubric scoring
        if formalgeo_report:
            # Use FormalGeo's score as the primary score
            total = formalgeo_report.get('total_points', 0)
            maximum = 100
            rubric_scores = []  # Skip rubric scoring when using FormalGeo
            referee_notes = {"referee_needed": False, "notes": "Using FormalGeo grading", "unknown_claim_ids": []}
        else:
            # Fallback to rubric scoring
            rubric_scores, total, maximum = await self.rubric_scorer.run(problem_id, verification_results)
            referee_notes = await self.referee.run(rubric_scores, verification_results, expected_score)

        result = {
            "problem_id": problem_id,
            "steps": [s.to_dict() for s in steps],
            "claims": [c.to_dict() for c in claim_payload["claims"]],
            "givens": [g.to_dict() for g in claim_payload["givens"]],
            "student_diagram_claims": [c.to_dict() for c in claim_payload["student_diagram_claims"]],
            "verification_results": [r.to_dict() for r in verification_results],
            "rubric_scores": [r.to_dict() for r in rubric_scores],
            "score_total": total,
            "score_max": maximum,
            "referee": referee_notes,
            "symbols_map": symbol_map,
            "formalgeo_used": formalgeo_used,
        }
        
        # Add FormalGeo detailed report if available
        if formalgeo_report:
            result["formalgeo_grading"] = formalgeo_report
        
        return result


class LLMService:
    def __init__(self):
        self.provider = LLM_PROVIDER
        self.api_key = LLM_API_KEY

    async def chat(self, messages: List[Dict[str, Any]], model: str = "gpt-5.2", temperature: float = 0.0, image_data: Optional[bytes] = None) -> Dict[str, Any]:
        """Generic chat interface for A1-A4 agents."""
        if not self.api_key or self.provider == 'mock':
            return self._mock_chat(messages)
        try:
            if self.provider == 'openai':
                return await self._chat_openai(messages, model=model, temperature=temperature, image_data=image_data)
            else:
                raise ValueError(f"Unsupported LLM provider for chat: {self.provider}")
        except Exception as e:
            print(f"LLM chat error: {e}")
            return self._mock_chat(messages)

    async def analyze_image(self, image_data: bytes) -> Dict[str, Any]:
        """Analyze image with configured LLM provider"""
        if not self.api_key or self.provider == 'mock':
            print("No API key provided or using mock provider, returning mock response")
            return self._get_mock_response()
        
        try:
            if self.provider == 'openai':
                return await self._analyze_with_openai(image_data)
            elif self.provider == 'anthropic':
                return await self._analyze_with_anthropic(image_data)
            elif self.provider == 'google':
                return await self._analyze_with_google(image_data)
            else:
                raise ValueError(f"Unsupported LLM provider: {self.provider}")
                
        except Exception as e:
            print(f"LLM API error: {e}")
            print("Falling back to mock response")
            return self._get_mock_response()

    async def _chat_openai(self, messages: List[Dict[str, Any]], model: str = "gpt-5.2", temperature: float = 0.0, image_data: Optional[bytes] = None) -> Dict[str, Any]:
        from openai import OpenAI
        client = OpenAI(api_key=self.api_key, timeout=600.0)  # Increased to 10 minutes
        formatted_messages = []
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, list):
                content_parts = content
            else:
                content_parts = [{"type": "text", "text": content}]
            if image_data and msg.get("role") == "user":
                image_format = self._detect_image_format(image_data)
                b64 = base64.b64encode(image_data).decode("utf-8")
                content_parts = content_parts + [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/{image_format};base64,{b64}", "detail": "high"},
                    }
                ]
            formatted_messages.append({"role": msg.get("role"), "content": content_parts})

        response = client.chat.completions.create(
            model=model,
            messages=formatted_messages,
            max_completion_tokens=4000,
            temperature=temperature,
        )
        content = response.choices[0].message.content
        try:
            return json.loads(content)
        except Exception:
            return {"raw": content}

    async def _analyze_with_openai(self, image_data: bytes) -> Dict[str, Any]:
        """Analyze image using OpenAI GPT-4 Vision"""
        try:
            # Detect image format
            image_format = self._detect_image_format(image_data)
            base64_image = base64.b64encode(image_data).decode('utf-8')
            # debugging purposes
            # print(f"Image format: {image_format}")
            # print(f"Base64 image: {base64_image}")
            # save base64_image to a file
            # with open('se_image.txt', 'w') as f:
            #     f.write(base64_image)
            from openai import OpenAI
            # Initialize client with explicit parameters
            client = OpenAI(
                api_key=self.api_key,
                timeout=600.0  # Increased to 10 minutes for vision API
            )

            sys_prompt = '''
You are a experienced 1 to 12 grade math teacher that are good at reading images created from hand written notes and analyzing diagrams to understand the content of the notes that can properly evaluate if the problem was done correctly.

**INPUT DEFINITION**
The image will contain a black inked portion describing the problem which could contain both text defining what the problem is as well as given parameters concerning the problem along with an accompanying image like a graph, shape, or chart; 
and the second portion is a grey inked solution for this problem that could contain a text response as well as grey colored drawings upon the problem's graphs, shapes, and charts.
Prepare a summary of all text elements to be later used for the OUTPUT of "text_description" and all drawing elements to be used later in the OUTPUT "drawing_description" respectively.

**GRADING PROCEDURE**
These two sections needs to be carefully evaluated on if the math problem that is written in black ink was done correctly, following below steps:
  1. Perform a detailed text recognition of ALL content on the image.  The problem portion will be formally printed, but be aware the solution portion is from hand writing and may require careful examination and recognization
    1a. Perform another detailed recognition of ALL other non-text based content on the image such as any additional graphs, shapes, or charts
  2. Try to understand the content based on the mathmetical context of this problem.  Understand what the problem is about and the available solutions to the problem.
    2a. If there is any additional elements like a graph, shape, or chart they are IMPORTANT to the evalution of the solution
  3. Pay attention to the solution to reasoning through the steps in it, following below three citeria to give a points based grading out of 100:
    3a. When evaluating solution, allow for some steps in the reasoning to be skipped if the transition is valid and common at this level or if the reasoning can be easily inferred from the existing context and graphics. When drawings, graphs, or charts are present, obvious observations do not need to be explicitly stated in the steps. 
    3b. From a global perspective, all the steps as a whole must serve the purpose of solving the problem. Solution must be relavent with regard to the problem. The reasoning process must align with the purpose of resolving the problem. If this criteria is not followed then take away all 100 points.
    3c. From an interstep perspective, the decution and deriviateion from one step to the next must be logical, reasonable, coherent, correct, accurate and relavent to the problem. When drawings, graphs, or charts are present, interstep logics must be assessed together with the drawings, graphs, or charts, to make sure the reasoning is consistent, relavent, and correct. For every logical flaw and violation of this critieria take away 20 points.
    3d. From an Intrastep perspective, make sure local computation, logic, or syntax are correct and accurate within each step. When drawings, graphs, or charts are present, make sure evaluate the individual step referencing the drawings, graphs, or charts and do not limit the scope to the step itself alone. For each local mistake take away 10 points.
  4. Everytime points are taken away, present an explanation for each flaw that was detected and provide a confidence score for each deduction.  Format as JSON with: a list of 1. the points taken away, 2. the corresponding reason, and 3. the confidence score of such deduction.
  5. When the entire solution is evaluated and deduction list is generated, go over all the items in the deduction list.  Reevaluate all point deductions and remove those containing hallucination or confidence score lower than 0.5.  IMPORTANT: Remove such deduction that requires explicitly statement that is obvious when viewing from the solution context or the drawings, graphs, or charts.

**OUTPUT DEFINITION**
FORMAT
CRITICAL: generate output in STRICT JSON format without any comments, explanations, or additional 
You must respond with valid JSON in this exact format:
```json
{
    "text_description": string,
    "drawing_description": string,
    "steps":
      [
        "step1",
        "step2",
        "step3"
      ],
    "total_points": int,
    "deductions":
      [
        {
          "deducted_points": int,
          "deduction_reason": string,
          "deduction_confidence_score": float,
          "deduction_step": string
        }
      ],
    "confidence_score": float,
    "summary": string
}
```

Field Definitions:
-text_description: All text seen on the image including the problem and solution
-drawing_description: A description of all non-text elements like graphs, charts, and shapes from the problem and solution
-steps: A list of all total steps the student took during the solution DO NOT ADD ANY ADDITIONAL DESCRIPTIONS, just the exact steps that the student took.
-total_points: the total amount of points given for the solution
-deductions: A list of all total deductions with the subtracted points value along with their corresponding explanations for why the deduction occurred
-deductions_points: Either 100, 20, or 10 based on the violations
-deduction_reason: The reason for the violation that caused the points deduction
-deduction_confidence_score: Float (0.0-1.0) indicating confidence in such deduction, 1.0 meaning complete confidence in this deduction
-deduction_step: the exact step where the deduction would be made in the solution where the error occurs.
-confidence_score: Float (0.0-1.0) indicating confidence in the total grading process, 1.0 meaning complete confidence in the final grade
-summary: summarize the evalution of the solution by the student and include the strengths and weaknesses of the student, demonstrated in the solution 

EXAMPLE OUTPUT
Example 1
```json
{
    "text_description": "Problem: solve this math equation Solution Below: 1 + 1 = 2, 2 + 2 = 4, 3x + 5 = 13, 2x = 18, x = 6, 6 * 9 = 45",
    "drawing_description": "no drawings such as charts, graphs, or shapes were detected",
    "steps":
      [
        "1 + 1 = 2",
        "2 + 2 = 4",
        "3x + 5 = 13",
        "2x = 18",
        "x = 6",
        "6 * 9 = 45"
      ],
    "total_points": 70,
    "deductions":[
        {
          "deducted_points": 20,
          "deduction_reason": "the logical relationship between step 3 and step 4 were illogical and did not properly connect the line of thought from step 3-4",
          "deduction_confidence_score": 0.9
          "deduction_step": "step 4"
        }
        {
          "deducted_points" 10,
          "deduction_reason": "there was a local computational error in step 6, 6 * 9 = 54, not 45 ",
          "deduction_confidence_score": 0.88
          "deduction_step": "step 6"
        }
    ],
    "confidence_score" 0.95
    "summary": "the student had a good understanding of the nature of this problem, but needs further background knowledge such as proficiency in the multiplication table and logical connection between the steps."
} 

Example 2
{
    "text_description": "Problem: Prove that angle C is a right angle, Given: Line AB is the diameter of the circle and point C is a point on the circle in between point A and point B, Solution Below: OA=OC=OB Triangle AOC and Triangle BOC are both isosceles triangles",
    "drawing_description": "There is a circle with a diameter from point A to Point B and a triangle drawn between the point A, point B, and a point C located somewhere inbetween point A and B",
     "steps":
      [
        "OA = OC = OB",
        "Triangle AOC and Triangle BOC are both isosceles triangles so",
        "angle OAC = angle OCA and angle OBC = angle OCB"
      ],
    "total_points": 100,
    "deductions":[],
    "confidence_score" 0.8
    "summary": "the student had completely understood all mathematical concepts present and solved accordingly."
} 
'''
            user_prompt = """
Please grade the problem and solution shown in the image.
"""
            
            response = client.chat.completions.create(
                model="gpt-5.2",  
                messages=[
                    {
                        "role": "system",
                        "content": sys_prompt
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": user_prompt,
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/{image_format};base64,{base64_image}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_completion_tokens=15000,
                temperature=0
            )
            
            content = response.choices[0].message.content
            return self._parse_response(content)
            
        except ImportError:
            raise Exception("OpenAI library not installed. Run: pip install openai>=1.12.0")
        except Exception as e:
            print(f"OpenAI API error details: {str(e)}")
            # Log more details about the error for debugging
            if hasattr(e, 'response'):
                print(f"API response status: {getattr(e.response, 'status_code', 'N/A')}")
                print(f"API response body: {getattr(e.response, 'text', 'N/A')}")
            raise Exception(f"OpenAI API error: {str(e)}")
    
    # async def _analyze_with_anthropic(self, image_data: bytes) -> Dict[str, Any]:
    #     """Analyze image using Anthropic Claude"""
    #     try:
    #         import anthropic
            
    #         client = anthropic.Anthropic(api_key=self.api_key)
    #         base64_image = base64.b64encode(image_data).decode('utf-8')
            
    #         response = client.messages.create(
    #             model="claude-3-5-sonnet-20241022",  # Updated to latest model
    #             max_tokens=1000,
    #             messages=[
    #                 {
    #                     "role": "user",
    #                     "content": [
    #                         {
    #                             "type": "image",
    #                             "source": {
    #                                 "type": "base64",
    #                                 "media_type": "image/png",
    #                                 "data": base64_image
    #                             }
    #                         },
    #                         {
    #                             "type": "text",
    #                             "text": "Please analyze this whiteboard drawing and provide: 1) Text recognition of any written content, 2) Description of visual elements (diagrams, shapes, arrows), 3) Content analysis and interpretation, 4) Suggestions for improvement or organization. Format your response as JSON with keys: text_recognition, visual_elements, content_analysis, suggestions (array), confidence (0-1)."
    #                         }
    #                     ]
    #                 }
    #             ]
    #         )
            
    #         content = response.content[0].text
    #         return self._parse_response(content)
            
    #     except ImportError:
    #         raise Exception("Anthropic library not installed. Run: pip install anthropic>=0.18.0")
    #     except Exception as e:
    #         raise Exception(f"Anthropic API error: {str(e)}")
    
    # async def _analyze_with_google(self, image_data: bytes) -> Dict[str, Any]:
    #     """Analyze image using Google Gemini"""
    #     import google.generativeai as genai
        
    #     genai.configure(api_key=self.api_key)
    #     model = genai.GenerativeModel('gemini-pro-vision')
        
    #     # Convert bytes to PIL Image
    #     image = Image.open(io.BytesIO(image_data))
        
    #     prompt = """Please analyze this whiteboard drawing and provide: 
    #     1) Text recognition of any written content
    #     2) Description of visual elements (diagrams, shapes, arrows)
    #     3) Content analysis and interpretation
    #     4) Suggestions for improvement or organization
        
    #     Format your response as JSON with keys: text_recognition, visual_elements, content_analysis, suggestions (array), confidence (0-1)."""
        
    #     response = model.generate_content([prompt, image])
    #     return self._parse_response(response.text)
    
    def _detect_image_format(self, image_data: bytes) -> str:
        """Detect image format from image data"""
        # Check magic bytes to determine format
        if image_data.startswith(b'\x89PNG\r\n\x1a\n'):
            return 'png'
        elif image_data.startswith(b'RIFF') and b'WEBP' in image_data[:12]:
            return 'webp'
        elif image_data.startswith(b'GIF87a') or image_data.startswith(b'GIF89a'):
            return 'gif'
        else:
            # Default to png if format cannot be determined
            return 'png'
    
    def _parse_response(self, content: str) -> Dict[str, Any]:
        """Parse LLM response into structured format"""
        import json
        
        try:
            # Try to parse as JSON first
            return json.loads(content)
        except json.JSONDecodeError:
            # If not valid JSON, create structured response from text
            return {
                # "text_recognition": self._extract_section(content, 'text'),
                # "visual_elements": self._extract_section(content, 'visual'),
                # "content_analysis": self._extract_section(content, 'analysis'),
                # "suggestions": self._extract_suggestions(content),
                # "confidence": 0.8,
                # "raw_response": content
            }
    
    def _extract_section(self, content: str, section_type: str) -> str:
        """Extract specific section from text response"""
        lines = content.split('\n')
        relevant_lines = []
        
        for line in lines:
            lower_line = line.lower()
            if section_type == 'text' and any(keyword in lower_line for keyword in ['text', 'written', 'words']):
                relevant_lines.append(line)
            elif section_type == 'visual' and any(keyword in lower_line for keyword in ['visual', 'diagram', 'shape']):
                relevant_lines.append(line)
            elif section_type == 'analysis' and any(keyword in lower_line for keyword in ['analysis', 'interpretation', 'meaning']):
                relevant_lines.append(line)
        
        return ' '.join(relevant_lines).strip() or f"No {section_type} content identified"
    
    def _extract_suggestions(self, content: str) -> List[str]:
        """Extract suggestions from text response"""
        lines = content.split('\n')
        suggestions = []
        
        for line in lines:
            if any(keyword in line.lower() for keyword in ['suggest', 'recommend', 'improve']) or \
               line.strip().startswith(('-', '•', '*')):
                suggestions.append(line.strip())
        
        return suggestions if suggestions else ['Consider adding more details to clarify the content']
    
    def _get_mock_response(self) -> Dict[str, Any]:
        """Generate mock analysis response"""
        return {
            "text_recognition": "MOCKED LLM RETURN: Mathematical equations and formulas related to calculus",
            "visual_elements": "Hand-drawn graphs, coordinate axes, and geometric shapes",
            "content_analysis": "This appears to be study notes for a calculus course, showing derivative calculations and graphical representations",
            "suggestions": [
                "Add more color coding to distinguish different concepts",
                "Include step-by-step solutions for better understanding",
                "Consider organizing formulas in a reference section"
            ],
            "confidence": 0.85,
        }

    def _mock_chat(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Deterministic mock for agent prompts."""
        # Try to infer intent from system prompt
        system_text = messages[0].get("content", "") if messages else ""
        if "Step Extractor" in system_text:
            return {
                "steps": [
                    {"step_id": 1, "raw_text": "OA = OC = OB", "normalized_text": "OA = OC = OB", "tokens": ["OA", "=", "OC", "=", "OB"], "span_refs": []},
                    {"step_id": 2, "raw_text": "Triangles AOC and BOC are isosceles", "normalized_text": "Triangles AOC and BOC are isosceles", "tokens": ["AOC", "BOC"], "span_refs": []},
                ],
                "symbols_map": {"O": [1, 2]},
            }
        if "Claim Generator Agent" in system_text:
            return {
                "givens": [],
                "student_diagram_claims": [{"claim_id": "SD1", "type": "ANGLE_SPLIT", "args": ["ACB", "ACO", "OCB"], "depends_on": [], "evidence": {"source": "student_diagram"}, "confidence_hint": "low"}],
                "claims": [
                    {"claim_id": "S1C1", "type": "RADIUS_EQUAL", "args": ["OA", "OC", "OB"], "depends_on": [], "evidence": {"from_step": 1}, "confidence_hint": "high"},
                    {"claim_id": "S2C1", "type": "ISOSCELES_BASE_ANGLES", "args": ["triangle AOC", "triangle BOC"], "depends_on": ["S1C1"], "evidence": {"from_step": 2}, "confidence_hint": "medium"},
                ],
            }
        if "Rubric Scorer Agent" in system_text:
            return {
                "scores": [
                    {"rubric_item_id": "R1", "earned": 2, "max": 2, "linked_claims": ["S1C1"], "notes": "mock full credit"},
                ],
                "total": 2,
                "maximum": 8,
            }
        if "Referee Agent" in system_text:
            return {"referee_needed": True, "notes": "mock referee", "unknown_claim_ids": []}
        if "geometry formalization agent" in system_text:
            return {
                "construction_cdl": ["Shape(AB,BC,CA)", "Cocircular(O,ABC)"],
                "text_cdl": ["IsCentreOfCircle(O,O)", "IsDiameterOfCircle(AB,O)"],
                "claim_cdl": ["Equal(LengthOfLine(OA),LengthOfLine(OC))", "Equal(MeasureOfAngle(OAC),MeasureOfAngle(OCA))"],
                "goal_cdl": "Equal(MeasureOfAngle(ACB),90)"
            }
        return {"message": "mock"}


class GeometryFormalizerAgent:
    """Agent that derives predicate_GDL, theorem_GDL, and problem_CDL from image+text and claims."""

    SYS_PROMPT = """
You are a geometry formalization agent. Given the text and drawing description of a geometry problem along with extracted claims,
produce a FormalGeo7k-style formalization following the CDL (Condition Description Language) format.

IMPORTANT: DO NOT generate predicate_GDL, theorem_GDL, or problem_CDL. Those will be provided automatically.

Output format:
{
  "construction_cdl": [string],  // Shape(), Collinear(), Cocircular() constructors
  "text_cdl": [string],          // Predicates from problem text (Equal, Perpendicular, etc.)
  "claim_cdl": [string],         // Additional predicates from student claims
  "goal_cdl": string             // What needs to be proven or calculated
}

CDL Format Rules:
1. construction_cdl: Define geometric shapes and relationships
   - Shape(AB,BC,CA) for triangles
   - Shape(AB,BC,CD,DA) for quadrilaterals
   - Collinear(ABC) for collinear points
   - Cocircular(O,ABC) for circle with center O through points A,B,C (use this for points on circle)

2. text_cdl: Encode problem givens as predicates
   - Equal(LengthOfLine(AB),LengthOfLine(CD)) for equal lengths
   - Equal(MeasureOfAngle(ABC),90) for angle measures
   - PerpendicularBetweenLine(AB,CD) for perpendicular lines
   - ParallelBetweenLine(AB,CD) for parallel lines
   - CongruentBetweenTriangle(ABC,DEF) for congruent triangles
   - IsTangentOfCircle(AB,O) for tangent line AB to circle O
   - IsCentreOfCircle(P,O) for circle center
   - IsDiameterOfCircle(AB,O) for diameter AB of circle O
   
IMPORTANT: For points on a circle, use Cocircular() in construction_cdl, NOT PointLiesOnCircle or similar.

3. claim_cdl: Convert student claims to CDL predicates
   - RADIUS_EQUAL → Equal(LengthOfLine(OA),LengthOfLine(OB))
   - ISOSCELES_BASE_ANGLES → Equal(MeasureOfAngle(ABC),MeasureOfAngle(ACB))
   - RIGHT_ANGLE → Equal(MeasureOfAngle(ABC),90)
   - ANGLE_SUM → Custom angle sum relations
   - PARALLEL → ParallelBetweenLine(AB,CD)
   - PERPENDICULAR → PerpendicularBetweenLine(AB,CD)
   
IMPORTANT: Do NOT use arithmetic expressions in CDL predicates!
  - WRONG: Equal(MeasureOfAngle(ACB),MeasureOfAngle(ACO)+MeasureOfAngle(OCB))
  - RIGHT: Describe only simple equalities like Equal(MeasureOfAngle(ABC),90) or Equal(MeasureOfAngle(ABC),MeasureOfAngle(DEF))
  - For angle sums, just skip the arithmetic - FormalGeo will infer it from theorems

4. goal_cdl: What to find or prove
   - Value(x) to find variable x
   - Value(MeasureOfAngle(ABC)) to find an angle
   - Value(LengthOfLine(AB)) to find a length

Examples from FormalGeo7k:

Example 1 (problem_id=1):
Problem: "Triangle RST is congruent to triangle XYZ, TR=x+21, ZX=2*x-14, ∠TRS=4*y-10°, ∠ZXY=3*y+5°. Find y."
{
  "construction_cdl": ["Shape(RS,ST,TR)", "Shape(XY,YZ,ZX)"],
  "text_cdl": [
    "CongruentBetweenTriangle(RST,XYZ)",
    "Equal(LengthOfLine(TR),x+21)",
    "Equal(LengthOfLine(ZX),2*x-14)",
    "Equal(MeasureOfAngle(TRS),4*y-10)",
    "Equal(MeasureOfAngle(ZXY),3*y+5)"
  ],
  "goal_cdl": "Value(y)"
}

Example 2 (problem_id=100):
Problem: "AB=z, AN=x, AY=5, YB=14, YN=y, BA⊥YA, YN⊥AN. Find y."
{
  "construction_cdl": ["Shape(AY,YN,NA)", "Shape(AN,NB,BA)", "Collinear(YNB)"],
  "text_cdl": [
    "Equal(LengthOfLine(AB),z)",
    "Equal(LengthOfLine(AN),x)",
    "Equal(LengthOfLine(AY),5)",
    "Equal(LengthOfLine(YB),14)",
    "Equal(LengthOfLine(YN),y)",
    "PerpendicularBetweenLine(BA,YA)",
    "PerpendicularBetweenLine(YN,AN)"
  ],
  "goal_cdl": "Value(y)"
}

Example 3 (problem_id=1000):
Problem: "AD=BA, CD=BC, ∠ADC=85°, ∠BAD=120°, quadrilateral ADCB is a kite. Find ∠DCB."
{
  "construction_cdl": ["Shape(AD,DC,CB,BA)"],
  "text_cdl": [
    "Equal(LengthOfLine(AD),LengthOfLine(BA))",
    "Equal(LengthOfLine(CD),LengthOfLine(BC))",
    "Equal(MeasureOfAngle(ADC),85)",
    "Equal(MeasureOfAngle(BAD),120)",
    "Kite(ADCB)"
  ],
  "goal_cdl": "Value(MeasureOfAngle(DCB))"
}

Your task:
1. Parse the problem text to extract construction_cdl and text_cdl
2. Convert each student claim to appropriate CDL predicates for claim_cdl
3. Determine the goal_cdl from the problem

Output STRICT JSON in the format specified above (only construction_cdl, text_cdl, claim_cdl, goal_cdl).
    """.strip()

    def __init__(self, llm_service: "LLMService"):
        self.llm_service = llm_service
        # Use local GDL files in backend/gdl
        self.gdl_path = os.path.join(os.path.dirname(__file__), "gdl")
        
        # Load FormalGeo GDL directly from JSON files
        self.predicate_gdl = None
        self.theorem_gdl = None
        try:
            import json
            predicate_path = os.path.join(self.gdl_path, "predicate_GDL.json")
            theorem_path = os.path.join(self.gdl_path, "theorem_GDL.json")
            
            print(f"[GeometryFormalizerAgent] Loading GDL from {self.gdl_path}")
            with open(predicate_path, 'r') as f:
                self.predicate_gdl = json.load(f)
            with open(theorem_path, 'r') as f:
                self.theorem_gdl = json.load(f)
            
            print(f"[GeometryFormalizerAgent] Loaded {len(self.theorem_gdl)} theorems")
            print(f"[GeometryFormalizerAgent] Predicate GDL keys: {list(self.predicate_gdl.keys())}")
        except Exception as e:
            print(f"[GeometryFormalizerAgent] Could not load GDL: {e}")
            print("[GeometryFormalizerAgent] Will use default/minimal GDL")

    def _normalize_triangle_label(self, raw: str) -> Optional[str]:
        text = str(raw).strip()
        if not text:
            return None
        text = text.replace("triangle", "").replace("Triangle", "").replace(" ", "")
        text = text.replace(",", "")
        text = text.strip()
        if len(text) == 3 and text.isalpha():
            return text.upper()
        return None

    def _claim_to_cdl_known(self, claim: "Claim") -> Optional[str]:
        claim_type = claim.type
        args = claim.args or []

        if claim_type == "RADIUS_EQUAL":
            if len(args) >= 2:
                return f"Equal(LengthOfLine({args[0]}),LengthOfLine({args[1]}))"
            return None

        if claim_type in {"ISOSCELES_TRIANGLE", "ISOSCELES"}:
            tri = None
            if args:
                if str(args[0]).strip().upper() == "TRIANGLE" and len(args) >= 2:
                    tri = self._normalize_triangle_label(args[1])
                else:
                    tri = self._normalize_triangle_label(args[0])
            if not tri and len(args) >= 3:
                tri = self._normalize_triangle_label("".join(str(a) for a in args[:3]))
            if tri:
                return f"IsoscelesTriangle({tri})"
            return None

        if claim_type == "ISOSCELES_BASE_ANGLES":
            if len(args) >= 2:
                return f"Equal(MeasureOfAngle({args[0]}),MeasureOfAngle({args[1]}))"
            return None

        if claim_type == "RIGHT_ANGLE":
            if args:
                return f"Equal(MeasureOfAngle({args[0]}),90)"
            return None

        if claim_type == "PARALLEL":
            if len(args) >= 2:
                return f"ParallelBetweenLine({args[0]},{args[1]})"
            return None

        if claim_type == "PERPENDICULAR":
            if len(args) >= 2:
                return f"PerpendicularBetweenLine({args[0]},{args[1]})"
            return None

        return None

    def _build_claim_cdl_from_claims(
        self,
        claims: Optional[List["Claim"]],
        resp_claim_cdl: List[str]
    ) -> List[str]:
        if not claims:
            return resp_claim_cdl

        if resp_claim_cdl and len(resp_claim_cdl) == len(claims):
            merged: List[str] = []
            for i, claim in enumerate(claims):
                cdl = self._claim_to_cdl_known(claim)
                merged.append(cdl if cdl else resp_claim_cdl[i])
            return merged

        mapped: List[str] = []
        for claim in claims:
            cdl = self._claim_to_cdl_known(claim)
            if cdl:
                mapped.append(cdl)

        # If we couldn't map most claims, fall back to LLM output
        if resp_claim_cdl and len(mapped) < max(1, len(claims) // 2):
            return resp_claim_cdl
        return mapped

    def _extract_triangles_from_cdl(self, cdl: str) -> List[str]:
        triangles: List[str] = []
        if not cdl:
            return triangles

        # IsoscelesTriangle(ABC) or IsoscelesTriangle(A,B,C)
        match = re.search(r'IsoscelesTriangle\(\s*([A-Z]{3})\s*\)', cdl)
        if match:
            triangles.append(match.group(1))
        match = re.search(r'IsoscelesTriangle\(\s*([A-Z])\s*,\s*([A-Z])\s*,\s*([A-Z])\s*\)', cdl)
        if match:
            triangles.append("".join(match.groups()))

        # RightTriangle(ABC) or RightTriangle(A,B,C)
        match = re.search(r'RightTriangle\(\s*([A-Z]{3})\s*\)', cdl)
        if match:
            triangles.append(match.group(1))
        match = re.search(r'RightTriangle\(\s*([A-Z])\s*,\s*([A-Z])\s*,\s*([A-Z])\s*\)', cdl)
        if match:
            triangles.append("".join(match.groups()))

        # CongruentBetweenTriangle(ABC,DEF)
        match = re.search(r'CongruentBetweenTriangle\(\s*([A-Z]{3})\s*,\s*([A-Z]{3})\s*\)', cdl)
        if match:
            triangles.extend([match.group(1), match.group(2)])

        return triangles

    def _ensure_triangle_constructions(self, resp: Dict[str, Any]) -> None:
        construction = resp.get("construction_cdl", []) or []
        existing = set(construction)

        candidates = resp.get("text_cdl", []) + resp.get("claim_cdl", [])
        triangles: List[str] = []
        for cdl in candidates:
            triangles.extend(self._extract_triangles_from_cdl(cdl))

        for tri in triangles:
            if len(tri) != 3:
                continue
            a, b, c = tri[0], tri[1], tri[2]
            shape = f"Shape({a}{b},{b}{c},{c}{a})"
            if shape not in existing:
                construction.append(shape)
                existing.add(shape)

        resp["construction_cdl"] = construction

    def _infer_goal_equal_from_claims(self, goal_cdl: str, claim_cdls: List[str]) -> Optional[str]:
        if not goal_cdl.startswith("Value("):
            return None
        target = goal_cdl[6:-1].strip()
        if not target:
            return None

        for claim in claim_cdls:
            m = re.match(r'Equal\(\s*([^,]+)\s*,\s*([0-9]+(?:\.[0-9]+)?)\s*\)\s*$', claim)
            if m and m.group(1).replace(" ", "") == target.replace(" ", ""):
                return f"Equal({m.group(1)},{m.group(2)})"
            m = re.match(r'Equal\(\s*([0-9]+(?:\.[0-9]+)?)\s*,\s*([^,]+)\s*\)\s*$', claim)
            if m and m.group(2).replace(" ", "") == target.replace(" ", ""):
                return f"Equal({m.group(2)},{m.group(1)})"
        return None

    async def run(
        self,
        text_description: str,
        drawing_description: str,
        image_data: Optional[bytes],
        claims: Optional[List[Claim]] = None,
        givens: Optional[List[Claim]] = None,
        student_diagram_claims: Optional[List[Claim]] = None,
    ) -> Dict[str, Any]:
        messages = [
            {"role": "system", "content": self.SYS_PROMPT},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "text_description": text_description,
                        "drawing_description": drawing_description,
                        "claims": [c.to_dict() for c in claims] if claims else [],
                        "givens": [g.to_dict() for g in givens] if givens else [],
                        "student_diagram_claims": [s.to_dict() for s in student_diagram_claims] if student_diagram_claims else [],
                    }
                ),
            },
        ]
        resp = await self.llm_service.chat(messages, image_data=image_data)
        if isinstance(resp, dict) and all(k in resp for k in ["construction_cdl", "text_cdl", "goal_cdl"]):
            resp.setdefault("claim_cdl", [])
            resp["claim_cdl"] = self._build_claim_cdl_from_claims(claims, resp.get("claim_cdl", []))
            self._ensure_triangle_constructions(resp)
            # Use loaded FormalGeo GDL if available, otherwise use defaults
            if "predicate_GDL" not in resp:
                resp["predicate_GDL"] = self.predicate_gdl if self.predicate_gdl else self._default_predicate_gdl()
            if "theorem_GDL" not in resp:
                resp["theorem_GDL"] = self.theorem_gdl if self.theorem_gdl else {}
            if "problem_CDL" not in resp:
                resp["problem_CDL"] = self._build_problem_cdl(resp)
            return resp
        
        # Fallback response with loaded GDL
        return {
            "construction_cdl": [],
            "text_cdl": [],
            "claim_cdl": [],
            "goal_cdl": None,
            "predicate_GDL": self.predicate_gdl if self.predicate_gdl else self._default_predicate_gdl(),
            "theorem_GDL": self.theorem_gdl if self.theorem_gdl else {},
            "problem_CDL": {"construction_cdl": [], "text_cdl": [], "goal_cdl": None},
        }

    def _default_predicate_gdl(self) -> Dict[str, Any]:
        """Minimal predicate GDL fallback if FormalGeo datasets not available"""
        return {
            "Preset": {
                "FixLength": ["Point", "Line", "Angle", "Circle", "Equation"],
                "VariableLength": ["Collinear", "Cocircular", "Polygon"],
                "BasicEntity": ["Point", "Line", "Arc", "Angle", "Polygon", "Circle"],
                "Construction": ["Shape", "Collinear", "Cocircular"],
            },
            "Entity": {},
            "Relation": {},
            "Attribution": {},
        }

    def _build_problem_cdl(self, resp: Dict[str, Any]) -> Dict[str, Any]:
        goal_cdl = resp.get("goal_cdl", "")
        claim_cdls = resp.get("claim_cdl", []) or []
        problem_answer = resp.get("problem_answer", "")

        inferred_equal = self._infer_goal_equal_from_claims(goal_cdl, claim_cdls)
        if inferred_equal:
            goal_cdl = inferred_equal
            problem_answer = "0"
        elif goal_cdl.startswith("Value(") and not problem_answer:
            # FormalGeo requires a non-empty answer for Value(...) goals
            problem_answer = "0"

        return {
            "problem_id": 1,
            "problem_level": 1,
            "problem_img": "",
            "construction_cdl": resp.get("construction_cdl", []),
            "text_cdl": resp.get("text_cdl", []) + resp.get("claim_cdl", []),
            "image_cdl": [],
            "goal_cdl": goal_cdl,
            "problem_answer": problem_answer
        }

# Initialize LLM service
llm_service = LLMService()
grading_pipeline = GradingPipeline(llm_service)

# Backup functionality
BACKUP_DIR = os.getenv('BACKUP_DIR', 'backups/images')

def ensure_backup_directory():
    """Ensure backup directory exists"""
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR, exist_ok=True)

def save_image_backup(image_data: bytes, filename_prefix: str = "backup") -> str:
    """Save image backup and return the backup file path"""
    ensure_backup_directory()
    
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]  # milliseconds
    backup_filename = f"{filename_prefix}_{timestamp}.png"
    backup_path = os.path.join(BACKUP_DIR, backup_filename)
    
    with open(backup_path, 'wb') as f:
        f.write(image_data)
    
    print(f"Image backup saved: {backup_path}")
    return backup_path

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'OK',
        'timestamp': datetime.now().isoformat(),
        'provider': LLM_PROVIDER,
        'has_api_key': bool(LLM_API_KEY)
    })

@app.route('/analyze', methods=['POST'])
def analyze_image():
    """Analyze whiteboard image"""
    try:
        data = request.get_json()

        if not data or 'image' not in data:
            return jsonify({
                'error': 'No image data provided'
            }), 400

        problem_id = data.get('problem_id', 'diameter_right_angle')
        student_modified_drawing_description = data.get('student_modified_drawing_description')
        expected_score = data.get('expected_score')
        
        # Decode base64 image
        try:
            image_data = base64.b64decode(data['image'])
            # Debug: save the uploaded image for inspection
            os.makedirs("uploads", exist_ok=True)
            debug_path = os.path.join("uploads", "debug_latest.png")
            with open(debug_path, "wb") as f:
                f.write(image_data)
            print(f"Saved debug image to {debug_path}")
        except Exception as e:
            return jsonify({
                'error': f'Invalid base64 image data: {str(e)}'
            }), 400
        
        # Validate image
        try:
            image = Image.open(io.BytesIO(image_data))
            image.verify()  # Verify it's a valid image
        except Exception as e:
            return jsonify({
                'error': f'Invalid image format: {str(e)}'
            }), 400
        
        # Save backup of the image before processing
        backup_path = save_image_backup(image_data, "analyzed_image")
        
        print(f"Processing image analysis request at {datetime.now()}")
        print(f"Image backup saved to: {backup_path}")
        
        # Process with LLM (note: using sync call since Flask doesn't support async by default)
        # For production, consider using Flask with async support or Celery for async processing
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            analysis_result = loop.run_until_complete(llm_service.analyze_image(image_data))
            grading_result = loop.run_until_complete(
                grading_pipeline.grade(
                    problem_id=problem_id,
                    text_description=analysis_result.get("text_description", ""),
                    drawing_description=analysis_result.get("drawing_description", ""),
                    image_data=image_data,
                    student_modified_drawing_description=student_modified_drawing_description,
                    expected_score=expected_score,
                )
            )
        finally:
            loop.close()

        return jsonify({
            "analysis": analysis_result,
            "grading": grading_result
        })
        
    except Exception as e:
        print(f"Error processing image: {e}")
        return jsonify({
            'error': f'Internal server error: {str(e)}'
        }), 500

@app.route('/api/process-image', methods=['POST'])
def process_image():
    """Process image file for AI analysis"""
    try:
        # Check if image file is in the request
        if 'image' not in request.files:
            return jsonify({
                'success': False,
                'error': 'No image file provided'
            }), 400
        
        image_file = request.files['image']
        
        if image_file.filename == '':
            return jsonify({
                'success': False,
                'error': 'No image file selected'
            }), 400
        
        # Read image data
        image_data = image_file.read()
        
        # Validate image
        try:
            image = Image.open(io.BytesIO(image_data))
            image.verify()  # Verify it's a valid image
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'Invalid image format: {str(e)}'
            }), 400
        
        # Save backup of the image before processing
        backup_path = save_image_backup(image_data, "analyzed_image")
        
        print(f"Processing image analysis request at {datetime.now()}")
        print(f"Image backup saved to: {backup_path}")
        
        # Process with LLM
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(llm_service.analyze_image(image_data))
        finally:
            loop.close()
        
        return jsonify({
            'success': True,
            'analysis': result
        })
        
    except Exception as e:
        print(f"Error processing image: {e}")
        return jsonify({
            'success': False,
            'error': f'Internal server error: {str(e)}'
        }), 500


@app.route('/api/grade-solution', methods=['POST'])
def grade_solution():
    """Run deterministic grading pipeline without image upload"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No payload provided'}), 400

        problem_id = data.get('problem_id', 'diameter_right_angle')
        text_description = data.get('student_answer_text', '')
        drawing_description = data.get('drawing_description', '')
        student_modified_drawing_description = data.get('student_modified_drawing_description')
        expected_score = data.get('expected_score')
        image_b64 = data.get('image')
        image_data = None
        if image_b64:
            try:
                image_data = base64.b64decode(image_b64)
            except Exception:
                return jsonify({'success': False, 'error': 'Invalid base64 image'}), 400

        if not text_description:
            return jsonify({'success': False, 'error': 'student_answer_text is required'}), 400

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            grading_result = loop.run_until_complete(
                grading_pipeline.grade(
                    problem_id=problem_id,
                    text_description=text_description,
                    drawing_description=drawing_description,
                    image_data=image_data,
                    student_modified_drawing_description=student_modified_drawing_description,
                    expected_score=expected_score,
                )
            )
        finally:
            loop.close()

        return jsonify({
            'success': True,
            'grading': grading_result
        })
    except Exception as e:
        print(f"Error running grading pipeline: {e}")
        return jsonify({'success': False, 'error': f'Internal server error: {str(e)}'}), 500

@app.route('/api/backup-image', methods=['POST'])
def backup_image():
    """Save image backup"""
    try:
        # Check if image file is in the request
        if 'image' not in request.files:
            return jsonify({
                'error': 'No image file provided'
            }), 400
        
        image_file = request.files['image']
        backup_type = request.form.get('backup_type', 'general')
        
        if image_file.filename == '':
            return jsonify({
                'error': 'No image file selected'
            }), 400
        
        # Read image data
        image_data = image_file.read()
        
        # Validate image
        try:
            image = Image.open(io.BytesIO(image_data))
            image.verify()  # Verify it's a valid image
        except Exception as e:
            return jsonify({
                'error': f'Invalid image format: {str(e)}'
            }), 400
        
        # Save backup
        backup_path = save_image_backup(image_data, backup_type)
        
        return jsonify({
            'success': True,
            'backup_path': backup_path,
            'message': 'Image backup saved successfully'
        })
        
    except Exception as e:
        print(f"Error saving image backup: {e}")
        return jsonify({
            'error': f'Internal server error: {str(e)}'
        }), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    port = int(os.getenv('BACKEND_PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    print(f"Starting Python backend server on port {port}")
    print(f"LLM Provider: {LLM_PROVIDER}")
    print(f"Has API Key: {bool(LLM_API_KEY)}")
    
    app.run(host='0.0.0.0', port=port, debug=debug)
