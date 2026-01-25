#!/usr/bin/env python3
"""
Simple FormalGeo Grader Test (No Flask required)

Tests the FormalGeo grader directly without the Flask app dependencies.
"""

import sys
import os
from pathlib import Path

# Add backend to path
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import asyncio
from graders.formalgeo_grader import FormalGeoStepGrader


async def test_diameter_right_angle_problem():
    """
    Test the diameter-right angle problem directly with FormalGeo
    
    Problem: Prove that angle C is a right angle
    Given: Line AB is the diameter of the circle and point C is a point on the circle
    """
    
    print("\n" + "="*80)
    print("FORMALGEO GRADER TEST: Diameter-Right Angle Problem")
    print("="*80 + "\n")
    
    # Step 1: Load FormalGeo datasets
    print("Step 1: Loading FormalGeo datasets...")
    try:
        from formalgeo.data import DatasetLoader
        
        # Try different dataset paths
        possible_paths = [
            "/Users/yud/repo/formalgeo7k/projects",
            "/Users/yud/repo/formalgeo7k/projects/formalgeo7k",
        ]
        
        dl = None
        for datasets_path in possible_paths:
            if not os.path.exists(datasets_path):
                continue
            
            try:
                # Find datasets in the directory
                dataset_name = None
                if os.path.exists(os.path.join(datasets_path, "info.json")):
                    # Direct dataset path
                    import json
                    with open(os.path.join(datasets_path, "info.json")) as f:
                        info = json.load(f)
                        dataset_name = info.get("dataset_name")
                    parent_path = os.path.dirname(datasets_path)
                else:
                    # Parent directory with multiple datasets
                    for item in os.listdir(datasets_path):
                        item_path = os.path.join(datasets_path, item)
                        if os.path.isdir(item_path) and os.path.exists(os.path.join(item_path, "info.json")):
                            dataset_name = item
                            parent_path = datasets_path
                            break
                
                if dataset_name:
                    print(f"  Found dataset: {dataset_name} in {parent_path}")
                    dl = DatasetLoader(
                        dataset_name=dataset_name,
                        datasets_path=parent_path
                    )
                    print(f"  ✓ Loaded {len(dl.theorem_GDL)} theorems")
                    break
            except Exception as e:
                print(f"  Failed to load from {datasets_path}: {e}")
                continue
        
        if not dl:
            print("  ✗ Could not load FormalGeo datasets")
            print("\n  To download datasets:")
            print("    from formalgeo.data import download_dataset")
            print("    download_dataset('formalgeo7k_v1', '/path/to/datasets')")
            return None
            
    except ImportError as e:
        print(f"  ✗ FormalGeo not available: {e}")
        return None
    
    # Step 2: Initialize grader
    print("\nStep 2: Initializing FormalGeo grader...")
    grader = FormalGeoStepGrader(
        predicate_gdl=dl.predicate_GDL,
        theorem_gdl=dl.theorem_GDL
    )
    
    if not grader.available:
        print("  ✗ Grader not available")
        return None
    
    print("  ✓ Grader initialized")
    
    # Step 3: Construct the problem
    print("\nStep 3: Constructing diameter-right angle problem...")
    
    problem_cdl = {
        "id": "diameter_right_angle",
        "construction_cdl": [
            "Cocircular(O,A,C,B)",  # Circle with center O through points A, C, B
        ],
        "text_cdl": [
            # AB is diameter
            "Collinear(A,O,B)",
        ],
        "goal_cdl": "Value(MeasureOfAngle(ACB))"
    }
    
    print("  Problem: Prove angle ACB = 90°")
    print("  Given: Circle O, diameter AB, point C on circle")
    
    # Step 4: Define student solution steps (from the image)
    print("\nStep 4: Student solution steps...")
    
    student_steps = [
        {
            "step_id": 1,
            "claim_cdl": "Equal(LengthOfLine(O,A),LengthOfLine(O,C))",
            "theorem_name": "radii_equal",
            "depends_on": []
        },
        {
            "step_id": 2,
            "claim_cdl": "Equal(LengthOfLine(O,C),LengthOfLine(O,B))",
            "theorem_name": "radii_equal",
            "depends_on": []
        },
        {
            "step_id": 3,
            "claim_cdl": "IsoscelesTriangle(A,O,C)",
            "theorem_name": "two_sides_equal",
            "depends_on": [1]
        },
        {
            "step_id": 4,
            "claim_cdl": "IsoscelesTriangle(B,O,C)",
            "theorem_name": "two_sides_equal",
            "depends_on": [2]
        },
        {
            "step_id": 5,
            "claim_cdl": "Equal(MeasureOfAngle(O,A,C),MeasureOfAngle(O,C,A))",
            "theorem_name": "isosceles_base_angles",
            "depends_on": [3]
        },
        {
            "step_id": 6,
            "claim_cdl": "Equal(MeasureOfAngle(O,B,C),MeasureOfAngle(O,C,B))",
            "theorem_name": "isosceles_base_angles",
            "depends_on": [4]
        },
    ]
    
    for step in student_steps:
        print(f"  Step {step['step_id']}: {step['claim_cdl']}")
    
    # Step 5: Grade the solution
    print("\nStep 5: Grading solution with FormalGeo...")
    
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
    
    # Step 6: Display results
    print("\n" + "="*80)
    print("GRADING RESULTS")
    print("="*80)
    
    print(f"\n📊 Score: {report.total_points}/100")
    print(f"🎯 Goal Reached: {report.goal_reached}")
    print(f"💯 Confidence: {report.confidence:.2f}")
    
    print(f"\n📝 Step-by-Step Feedback:")
    for feedback in report.step_feedback:
        status = "✓" if feedback["is_valid"] else "✗"
        step_id = feedback["step_id"]
        
        if feedback["is_valid"]:
            note = feedback.get("note", "Valid")
            print(f"  {status} Step {step_id}: {note}")
        else:
            error = feedback.get("error_details", "Invalid")
            print(f"  {status} Step {step_id}: {error}")
    
    if report.deductions:
        print(f"\n❌ Deductions ({len(report.deductions)} total):")
        for d in report.deductions:
            print(f"  - Step {d.get('deduction_step', '?')}: {d['deduction_reason']}")
            print(f"    Points: -{d['deducted_points']} (confidence: {d['deduction_confidence_score']:.2f})")
    
    if report.missing_steps:
        print(f"\n⚠️  Missing Steps:")
        for ms in report.missing_steps:
            print(f"  - {ms.get('description', 'N/A')}")
    
    print(f"\n📄 Summary:")
    print(f"  {report.summary}")
    
    print("\n" + "="*80)
    print("TEST COMPLETED")
    print("="*80 + "\n")
    
    return report


def main():
    """Run the test"""
    try:
        result = asyncio.run(test_diameter_right_angle_problem())
        
        if result:
            print(f"\n✅ Test passed! Final score: {result.total_points}/100")
            sys.exit(0)
        else:
            print(f"\n❌ Test failed - could not complete grading")
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
