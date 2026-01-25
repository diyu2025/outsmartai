#!/usr/bin/env python3
"""
Test FormalGeoStepGrader with a sample problem from formalgeo7k

This test loads a known problem and simulates student steps to verify
the grading algorithm works correctly.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from graders.formalgeo_grader import FormalGeoStepGrader


def test_basic_initialization():
    """Test 1: Can we load FormalGeo datasets?"""
    print("\n" + "="*80)
    print("TEST 1: Basic Initialization")
    print("="*80)
    
    try:
        from formalgeo.data import DatasetLoader
        
        datasets_path = "/Users/yud/repo/formalgeo7k/projects/formalgeo7k"
        print(f"Loading datasets from: {datasets_path}")
        
        dl = DatasetLoader(
            dataset_name="formalgeo7k",
            datasets_path=datasets_path
        )
        
        print(f"✓ Loaded predicate_GDL: {len(dl.predicate_GDL.keys())} categories")
        print(f"✓ Loaded theorem_GDL: {len(dl.theorem_GDL)} theorems")
        
        # Show sample theorems
        print("\nSample theorems:")
        for i, theorem_name in enumerate(list(dl.theorem_GDL.keys())[:5]):
            print(f"  {i+1}. {theorem_name}")
        
        return dl
        
    except Exception as e:
        print(f"✗ Failed to load datasets: {e}")
        return None


def test_grader_initialization(dl):
    """Test 2: Can we initialize the FormalGeoStepGrader?"""
    print("\n" + "="*80)
    print("TEST 2: FormalGeoStepGrader Initialization")
    print("="*80)
    
    try:
        grader = FormalGeoStepGrader(
            predicate_gdl=dl.predicate_GDL,
            theorem_gdl=dl.theorem_GDL
        )
        
        if grader.available:
            print("✓ FormalGeoStepGrader initialized successfully")
            print(f"✓ Has {len(grader.theorem_gdl)} theorems available")
            return grader
        else:
            print("✗ FormalGeoStepGrader not available")
            return None
            
    except Exception as e:
        print(f"✗ Failed to initialize grader: {e}")
        return None


def test_problem_loading(dl, grader):
    """Test 3: Can we load a problem from the dataset?"""
    print("\n" + "="*80)
    print("TEST 3: Problem Loading")
    print("="*80)
    
    try:
        # Load problem #1 from formalgeo7k_v1
        problem_CDL = dl.get_problem(pid=1)
        
        print(f"✓ Loaded problem {problem_CDL['id']}")
        print(f"  Problem level: {problem_CDL.get('problem_level', 'N/A')}")
        print(f"  Construction CDL: {len(problem_CDL['construction_cdl'])} items")
        print(f"  Text CDL: {len(problem_CDL['text_cdl'])} items")
        print(f"  Goal: {problem_CDL['goal_cdl']}")
        
        # Initialize problem in grader
        success = grader.initialize_problem(problem_CDL)
        
        if success:
            print("✓ Problem loaded into grader successfully")
            print(f"  Initial KB size: {len(grader.solver.problem.condition.items)} items")
            return problem_CDL
        else:
            print("✗ Failed to load problem into grader")
            return None
            
    except Exception as e:
        print(f"✗ Failed to load problem: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_simple_step_verification(grader, problem_CDL):
    """Test 4: Can we verify a simple correct step?"""
    print("\n" + "="*80)
    print("TEST 4: Simple Step Verification")
    print("="*80)
    
    try:
        # Create a simple test step based on problem #1
        # Problem #1 is about congruent triangles
        test_step = {
            "step_id": 1,
            "claim_cdl": "CongruentBetweenTriangle(R,S,T,X,Y,Z)",
            "theorem_name": "",  # This is a given, not derived
            "depends_on": []
        }
        
        print(f"Testing step: {test_step['claim_cdl']}")
        
        result = grader.verify_single_step(
            step=test_step,
            current_state=grader.get_current_state(),
            grading_criteria=None,
            previous_results=[]
        )
        
        print(f"\nResult:")
        print(f"  Valid: {result.is_valid}")
        print(f"  Redundant: {result.is_redundant}")
        print(f"  Error type: {result.error_type}")
        print(f"  Confidence: {result.confidence}")
        
        if result.is_valid or result.is_redundant:
            print("✓ Step verification works!")
        else:
            print(f"✗ Step marked as invalid: {result.error_details}")
        
        return result
        
    except Exception as e:
        print(f"✗ Step verification failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_theorem_matching(grader):
    """Test 5: Can we match informal theorem names?"""
    print("\n" + "="*80)
    print("TEST 5: Theorem Fuzzy Matching")
    print("="*80)
    
    test_cases = [
        "congruent triangle",
        "isosceles",
        "angle sum",
        "radius equal",
        "vertical angles",
    ]
    
    print("Testing fuzzy matching:")
    for informal_name in test_cases:
        matched = grader.fuzzy_match_theorem(informal_name)
        if matched:
            print(f"  ✓ '{informal_name}' → '{matched}'")
        else:
            print(f"  ✗ '{informal_name}' → No match")


async def test_full_grading(grader):
    """Test 6: Can we grade a complete solution?"""
    print("\n" + "="*80)
    print("TEST 6: Full Solution Grading")
    print("="*80)
    
    try:
        # Simulate student steps for a simple problem
        student_steps = [
            {
                "step_id": 1,
                "claim_cdl": "Equal(LengthOfLine(O,A),LengthOfLine(O,B))",
                "theorem_name": "radius_equal",
                "depends_on": []
            },
            {
                "step_id": 2,
                "claim_cdl": "IsoscelesTriangle(A,O,B)",
                "theorem_name": "isosceles_definition",
                "depends_on": [1]
            },
        ]
        
        # Note: This is a mock - would need proper GDL payload for real test
        gdl_payload = {
            "predicate_GDL": grader.predicate_gdl,
            "theorem_GDL": grader.theorem_gdl,
            "problem_CDL": {
                "construction_cdl": ["Cocircular(O,A,B,C)"],
                "text_cdl": [],
                "goal_cdl": "Value(MeasureOfAngle(ACB))"
            }
        }
        
        print(f"Grading {len(student_steps)} steps...")
        
        report = await grader.grade_geometry_solution(
            gdl_payload=gdl_payload,
            student_steps=student_steps,
            grading_criteria=None
        )
        
        print(f"\nGrading Report:")
        print(f"  Total Points: {report.total_points}/100")
        print(f"  Deductions: {len(report.deductions)}")
        print(f"  Step Feedback: {len(report.step_feedback)} steps")
        print(f"  Goal Reached: {report.goal_reached}")
        print(f"  Confidence: {report.confidence:.2f}")
        
        if report.deductions:
            print(f"\n  Deductions:")
            for d in report.deductions:
                print(f"    - {d['deduction_reason']} (-{d['deducted_points']} pts)")
        
        print("✓ Full grading completed!")
        return report
        
    except Exception as e:
        print(f"✗ Full grading failed: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("FormalGeo Step Grader Integration Tests")
    print("="*80)
    
    # Test 1: Load datasets
    dl = test_basic_initialization()
    if not dl:
        print("\n✗ Cannot proceed without datasets")
        return
    
    # Test 2: Initialize grader
    grader = test_grader_initialization(dl)
    if not grader:
        print("\n✗ Cannot proceed without grader")
        return
    
    # Test 3: Load problem
    problem_CDL = test_problem_loading(dl, grader)
    if not problem_CDL:
        print("\n✗ Cannot proceed without loaded problem")
        return
    
    # Test 4: Verify single step
    test_simple_step_verification(grader, problem_CDL)
    
    # Test 5: Theorem matching
    test_theorem_matching(grader)
    
    # Test 6: Full grading (async)
    asyncio.run(test_full_grading(grader))
    
    print("\n" + "="*80)
    print("All tests completed!")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
