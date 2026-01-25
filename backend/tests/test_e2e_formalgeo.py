#!/usr/bin/env python3
"""
End-to-End Integration Test for FormalGeo Grading Pipeline

This test runs the complete multi-agent grading pipeline with FormalGeo step grading
on the diameter-right angle problem.
"""

import asyncio
import base64
import json
import os
import sys
from pathlib import Path

# Add backend to path
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import app as app_module


def load_test_image(image_path: str) -> bytes:
    """Load test image from file"""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Test image not found: {image_path}")
    return path.read_bytes()


async def test_full_grading_pipeline_with_formalgeo():
    """
    Test the complete grading pipeline:
    1. Image Analysis (LLM extracts text and drawing description)
    2. StepExtractorAgent (extracts steps from solution)
    3. ClaimGeneratorAgent (converts steps to claims)
    4. GeometryFormalizerAgent (formalizes to CDL/GDL)
    5. FormalGeoStepGrader (verifies steps with theorem prover)
    6. RubricScorerAgent (calculates final score)
    """
    
    print("\n" + "="*80)
    print("END-TO-END FORMALGEO GRADING PIPELINE TEST")
    print("Problem: Prove angle C is a right angle (diameter-inscribed angle)")
    print("="*80 + "\n")
    
    # Load test image
    image_path = "/Users/yud/repo/outsmartai/backend/tests/data/diameter_right_angle.png"
    try:
        image_bytes = load_test_image(image_path)
        print(f"✓ Loaded test image: {image_path}")
        print(f"  Image size: {len(image_bytes)} bytes")
    except FileNotFoundError as e:
        print(f"✗ {e}")
        print("\nNote: Save the diameter-right angle problem image to:")
        print(f"  {image_path}")
        return None
    
    # Initialize pipeline
    llm_service = app_module.LLMService()
    pipeline = app_module.GradingPipeline(llm_service)
    
    print("\n" + "-"*80)
    print("PHASE 1: Image Analysis")
    print("-"*80)
    
    # Step 1: Analyze image
    analysis = await llm_service.analyze_image(image_bytes)
    
    print(f"\nText Description:")
    print(f"  {analysis.get('text_description', 'N/A')[:200]}...")
    print(f"\nDrawing Description:")
    print(f"  {analysis.get('drawing_description', 'N/A')[:200]}...")
    print(f"\nSteps Extracted: {len(analysis.get('steps', []))}")
    
    # Step 2: Run grading pipeline
    print("\n" + "-"*80)
    print("PHASE 2: Multi-Agent Grading Pipeline")
    print("-"*80)
    
    grading_result = await pipeline.grade(
        problem_id="diameter_right_angle",
        text_description=analysis.get("text_description", ""),
        drawing_description=analysis.get("drawing_description", ""),
        image_data=image_bytes,
        student_modified_drawing_description=None,
        expected_score=None,
    )
    
    # Display results
    print("\n" + "="*80)
    print("GRADING RESULTS")
    print("="*80)
    
    print(f"\n📊 Final Score: {grading_result.get('score_total', 0)}/{grading_result.get('score_max', 100)}")
    print(f"🎯 Confidence: {grading_result.get('referee', {}).get('notes', 'N/A')}")
    
    print(f"\n📝 Steps Analyzed: {len(grading_result.get('steps', []))}")
    for i, step in enumerate(grading_result.get('steps', [])[:5], 1):
        print(f"  {i}. {step.get('raw_text', 'N/A')[:60]}...")
    
    print(f"\n🔍 Claims Generated: {len(grading_result.get('claims', []))}")
    for i, claim in enumerate(grading_result.get('claims', [])[:5], 1):
        print(f"  {i}. [{claim.get('claim_id')}] {claim.get('type')} - {claim.get('args', [])}")
    
    print(f"\n✅ Verification Results:")
    verification_results = grading_result.get('verification_results', [])
    true_count = sum(1 for r in verification_results if r.get('verdict') == 'true')
    false_count = sum(1 for r in verification_results if r.get('verdict') == 'false')
    unknown_count = sum(1 for r in verification_results if r.get('verdict') == 'unknown')
    
    print(f"  True: {true_count}")
    print(f"  False: {false_count}")
    print(f"  Unknown: {unknown_count}")
    
    if false_count > 0:
        print(f"\n❌ Failed Claims:")
        for result in verification_results:
            if result.get('verdict') == 'false':
                print(f"  - {result.get('claim_id')}: {result.get('reason_code')}")
                if result.get('missing'):
                    print(f"    Missing: {result.get('missing')}")
    
    print(f"\n💯 Rubric Scores:")
    for score in grading_result.get('rubric_scores', []):
        print(f"  [{score.get('rubric_item_id')}] {score.get('earned')}/{score.get('max')} - {score.get('notes')}")
    
    # Check if FormalGeo grading was used
    formalgeo_used = any(
        r.get('reason_code') == 'FORMALGEO_VERIFIED' 
        for r in verification_results
    )
    
    print(f"\n🔧 FormalGeo Step Grading: {'✓ ENABLED' if formalgeo_used else '✗ NOT USED'}")
    
    # Save results
    output_path = Path(__file__).parent / "output" / "e2e_grading_result.json"
    output_path.parent.mkdir(exist_ok=True)
    output_path.write_text(json.dumps({
        "analysis": analysis,
        "grading": grading_result
    }, indent=2, ensure_ascii=False))
    
    print(f"\n💾 Full results saved to: {output_path}")
    
    print("\n" + "="*80)
    print("TEST COMPLETED")
    print("="*80 + "\n")
    
    return {
        "analysis": analysis,
        "grading": grading_result,
        "formalgeo_used": formalgeo_used
    }


async def test_formalgeo_integration_only():
    """
    Test just the FormalGeo integration with a manually constructed problem.
    
    This bypasses the LLM agents and directly tests the FormalGeo grading.
    """
    
    print("\n" + "="*80)
    print("FORMALGEO INTEGRATION TEST (Bypassing LLM Agents)")
    print("="*80 + "\n")
    
    # Check if FormalGeo is available
    try:
        from formalgeo.data import DatasetLoader
        
        datasets_path = "/Users/yud/repo/formalgeo7k/projects"
        print(f"Loading FormalGeo datasets from: {datasets_path}")
        
        # Try to find and load dataset
        import os
        dataset_dirs = []
        if os.path.exists(datasets_path):
            for item in os.listdir(datasets_path):
                item_path = os.path.join(datasets_path, item)
                if os.path.isdir(item_path) and os.path.exists(os.path.join(item_path, "info.json")):
                    dataset_dirs.append(item)
        
        if not dataset_dirs:
            print(f"✗ No FormalGeo datasets found in {datasets_path}")
            print("\nTo download datasets:")
            print("  from formalgeo.data import download_dataset")
            print("  download_dataset('formalgeo7k_v1', '/path/to/datasets')")
            return None
        
        print(f"✓ Found datasets: {dataset_dirs}")
        
        # Load first available dataset
        dataset_name = dataset_dirs[0]
        dl = DatasetLoader(
            dataset_name=dataset_name,
            datasets_path=datasets_path
        )
        
        print(f"✓ Loaded {len(dl.theorem_GDL)} theorems from {dataset_name}")
        
        # Initialize FormalGeo grader
        from graders.formalgeo_grader import FormalGeoStepGrader
        
        grader = FormalGeoStepGrader(
            predicate_gdl=dl.predicate_GDL,
            theorem_gdl=dl.theorem_GDL
        )
        
        if not grader.available:
            print("✗ FormalGeo grader not available")
            return None
        
        print("✓ FormalGeo grader initialized")
        
        # Manually construct the diameter-right angle problem
        problem_cdl = {
            "id": "test_diameter_right_angle",
            "construction_cdl": [
                "Shape(AO,OB)",  # Diameter AB
                "Cocircular(O,A,B,C)",  # Circle with center O through points A, B, C
            ],
            "text_cdl": [
                # AB is diameter
                "Equal(LengthOfLine(AO),LengthOfLine(OB))",
                "Equal(LengthOfLine(AO),LengthOfLine(OC))",
            ],
            "goal_cdl": "Value(MeasureOfAngle(ACB))"
        }
        
        # Student solution steps
        student_steps = [
            {
                "step_id": 1,
                "claim_cdl": "Equal(LengthOfLine(O,A),LengthOfLine(O,C))",
                "theorem_name": "radii are equal",
                "depends_on": []
            },
            {
                "step_id": 2,
                "claim_cdl": "Equal(LengthOfLine(O,B),LengthOfLine(O,C))",
                "theorem_name": "radii are equal",
                "depends_on": []
            },
            {
                "step_id": 3,
                "claim_cdl": "IsoscelesTriangle(A,O,C)",
                "theorem_name": "two sides equal means isosceles",
                "depends_on": [1]
            },
            {
                "step_id": 4,
                "claim_cdl": "IsoscelesTriangle(B,O,C)",
                "theorem_name": "two sides equal means isosceles",
                "depends_on": [2]
            },
        ]
        
        print(f"\n📝 Testing with {len(student_steps)} student steps")
        
        # Grade the solution
        gdl_payload = {
            "predicate_GDL": dl.predicate_GDL,
            "theorem_GDL": dl.theorem_GDL,
            "problem_CDL": problem_cdl
        }
        
        report = await grader.grade_geometry_solution(
            gdl_payload=gdl_payload,
            student_steps=student_steps,
            grading_criteria=None
        )
        
        print(f"\n✅ GRADING REPORT")
        print(f"  Total Points: {report.total_points}/100")
        print(f"  Goal Reached: {report.goal_reached}")
        print(f"  Confidence: {report.confidence:.2f}")
        
        print(f"\n📊 Step Feedback:")
        for feedback in report.step_feedback:
            status = "✓" if feedback["is_valid"] else "✗"
            print(f"  {status} Step {feedback['step_id']}: {feedback.get('note', feedback.get('error_details', 'N/A'))}")
        
        if report.deductions:
            print(f"\n❌ Deductions:")
            for d in report.deductions:
                print(f"  - {d['deduction_reason']} (-{d['deducted_points']} pts)")
        
        print(f"\n📝 Summary: {report.summary}")
        
        return report
        
    except Exception as e:
        print(f"✗ FormalGeo integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Run all end-to-end tests"""
    
    # Test 1: FormalGeo integration only (no LLM required)
    print("\n" + "="*80)
    print("TEST 1: FormalGeo Integration (Direct)")
    print("="*80)
    
    result1 = asyncio.run(test_formalgeo_integration_only())
    
    # Test 2: Full pipeline (requires LLM and image)
    if os.getenv("RUN_FULL_E2E") == "1":
        print("\n" + "="*80)
        print("TEST 2: Full E2E Pipeline (LLM + FormalGeo)")
        print("="*80)
        
        result2 = asyncio.run(test_full_grading_pipeline_with_formalgeo())
    else:
        print("\n" + "="*80)
        print("TEST 2: Full E2E Pipeline (SKIPPED)")
        print("="*80)
        print("\nTo run full pipeline test:")
        print("  1. Save the test image to: /Users/yud/repo/outsmartai/backend/tests/data/diameter_right_angle.png")
        print("  2. Set environment variables:")
        print("     export RUN_FULL_E2E=1")
        print("     export LLM_PROVIDER=openai")
        print("     export LLM_API_KEY=your_key")
        print("  3. Run: python tests/test_e2e_formalgeo.py")


if __name__ == "__main__":
    main()
