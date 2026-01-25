#!/usr/bin/env /Users/yud/repo/outsmartai/.venv/bin/python

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from graders.formalgeo_grader import FormalGeoStepGrader

# Load GDL
gdl_path = os.path.join(os.path.dirname(__file__), "gdl")
with open(os.path.join(gdl_path, "predicate_GDL.json")) as f:
    predicate_gdl = json.load(f)
with open(os.path.join(gdl_path, "theorem_GDL.json")) as f:
    theorem_gdl = json.load(f)

print("✅ GDL loaded")
print(f"  Predicate GDL keys: {list(predicate_gdl.keys())}")
print(f"  Theorem GDL count: {len(theorem_gdl)}")

# Initialize grader
grader = FormalGeoStepGrader(predicate_gdl, theorem_gdl)
print(f"\n✅ FormalGeoStepGrader initialized")
print(f"  Available: {grader.available}")

# Test problem CDL (simple circle problem)
problem_cdl = {
    "problem_id": 1,
    "problem_level": 1,
    "problem_img": "",
    "construction_cdl": [
        "Shape(AB,BC,CA)",
        "Cocircular(O,ABC)"
    ],
    "text_cdl": [
        "IsCentreOfCircle(O,O)",
        "IsDiameterOfCircle(AB,O)"
    ],
    "image_cdl": [],
    "goal_cdl": "Equal(MeasureOfAngle(ACB),90)",
    "problem_answer": "90"
}

print(f"\n🔧 Initializing problem...")
success = grader.initialize_problem(problem_cdl)
print(f"  Initialization: {'✅ SUCCESS' if success else '❌ FAILED'}")

if success:
    print(f"  KB items: {len(grader.solver.problem.condition.items)}")
    
    # Test parsing a simple claim
    test_claims = [
        "Equal(LengthOfLine(OA),LengthOfLine(OC))",
        "Equal(MeasureOfAngle(OAC),MeasureOfAngle(OCA))",
    ]
    
    for claim_cdl in test_claims:
        print(f"\n🧪 Testing claim: {claim_cdl}")
        try:
            from formalgeo.parse import parse_theorem_seqs
            parsed_list = parse_theorem_seqs([claim_cdl], grader.parsed_predicate_GDL)
            
            if not parsed_list:
                print(f"  ❌ parse_theorem_seqs returned empty list")
                continue
                
            parsed = parsed_list[0]
            print(f"  ✅ Parsed: {parsed}")
            print(f"    Name: {parsed.name}")
            print(f"    Items: {parsed.items}")
            
            # Check if in KB
            found = False
            for item in parsed.items:
                if grader.solver.problem.condition.has(parsed.name, item):
                    print(f"    ✅ Found in KB: {parsed.name}{item}")
                    found = True
                else:
                    print(f"    ❌ Not in KB: {parsed.name}{item}")
            
            if not found:
                print(f"    ⚠️  Claim not derivable from current KB")
                
        except Exception as e:
            print(f"  ❌ Parse error: {e}")
            import traceback
            traceback.print_exc()

print(f"\n✅ Test complete")
