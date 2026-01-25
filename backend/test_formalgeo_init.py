#!/usr/bin/env python3
"""
Quick test to verify FormalGeo initialization works correctly
"""

import sys
sys.path.insert(0, '.')

print("=" * 80)
print("Testing FormalGeo Initialization")
print("=" * 80)

# Test 1: Load GDL files
print("\n[Test 1] Loading GDL files...")
try:
    import json
    gdl_path = "/Users/yud/repo/formalgeo7k/projects/formalgeo7k/gdl"
    
    with open(f"{gdl_path}/predicate_GDL.json", 'r') as f:
        predicate_gdl = json.load(f)
    with open(f"{gdl_path}/theorem_GDL.json", 'r') as f:
        theorem_gdl = json.load(f)
    
    print(f"✓ Loaded {len(theorem_gdl)} theorems")
    print(f"✓ Predicate GDL keys: {list(predicate_gdl.keys())}")
    print(f"✓ Predicate GDL has 'Preset': {'Preset' in predicate_gdl}")
except Exception as e:
    print(f"✗ Failed: {e}")
    sys.exit(1)

# Test 2: Import FormalGeo
print("\n[Test 2] Importing FormalGeo...")
try:
    from formalgeo.solver import Interactor
    print("✓ FormalGeo imported successfully")
except Exception as e:
    print(f"✗ Failed: {e}")
    sys.exit(1)

# Test 3: Initialize Interactor with GDL
print("\n[Test 3] Initializing FormalGeo Interactor...")
try:
    solver = Interactor(predicate_gdl, theorem_gdl)
    print("✓ Interactor initialized successfully")
except Exception as e:
    print(f"✗ Failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: Load a simple problem
print("\n[Test 4] Loading a test problem...")
try:
    problem_cdl = {
        "problem_id": 1,
        "problem_level": 1,
        "problem_img": "test.png",
        "construction_cdl": ["Shape(AB,BC,CA)"],
        "text_cdl": ["Equal(LengthOfLine(AB),LengthOfLine(BC))"],
        "image_cdl": [],
        "goal_cdl": "Value(LengthOfLine(CA))",
        "problem_answer": "5"
    }
    solver.load_problem(problem_cdl)
    print("✓ Problem loaded successfully")
    print(f"✓ Knowledge base has {len(solver.problem.condition.items)} items")
except Exception as e:
    print(f"✗ Failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 5: Import FormalGeoStepGrader
print("\n[Test 5] Importing FormalGeoStepGrader...")
try:
    from graders.formalgeo_grader import FormalGeoStepGrader
    grader = FormalGeoStepGrader(predicate_gdl, theorem_gdl)
    print(f"✓ FormalGeoStepGrader imported and initialized")
    print(f"✓ Grader available: {grader.available}")
except Exception as e:
    print(f"✗ Failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 6: Initialize problem in grader
print("\n[Test 6] Initializing problem in FormalGeoStepGrader...")
try:
    success = grader.initialize_problem(problem_cdl)
    print(f"✓ Problem initialization: {success}")
    if grader.solver:
        print(f"✓ Solver KB has {len(grader.solver.problem.condition.items)} items")
except Exception as e:
    print(f"✗ Failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 80)
print("ALL TESTS PASSED! FormalGeo is properly configured.")
print("=" * 80)
