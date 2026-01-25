#!/usr/bin/env python3
"""
End-to-End Test: Diameter-Right Angle Problem
Uses the actual problem image and runs full multi-agent pipeline with FormalGeo grading
"""

import sys
import os
import asyncio
import json
from pathlib import Path

# Setup paths
BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))


async def run_e2e_test(image_path: str):
    """
    Run complete E2E test with FormalGeo grading
    
    Pipeline:
    1. LLM Image Analysis → extracts problem/solution text
    2. StepExtractorAgent → parses steps from solution
    3. ClaimGeneratorAgent → converts to atomic claims
    4. GeometryFormalizerAgent → formalizes to CDL/GDL
    5. FormalGeoStepGrader → verifies with theorem prover
    6. RubricScorerAgent → calculates final score
    """
    
    print("\n" + "="*80)
    print("END-TO-END TEST: Diameter-Right Angle Problem with FormalGeo")
    print("="*80 + "\n")
    
    # Import app module
    try:
        import app as app_module
    except ImportError:
        print("❌ Cannot import app module. Make sure you're in the backend directory.")
        return None
    
    # Load image
    image_path = Path(image_path)
    if not image_path.exists():
        print(f"❌ Image not found: {image_path}")
        print("\nAvailable images in tests/data/:")
        data_dir = Path(__file__).parent / "data"
        if data_dir.exists():
            for f in data_dir.glob("*.png"):
                print(f"  - {f.name}")
        return None
    
    print(f"📷 Loading image: {image_path.name}")
    image_bytes = image_path.read_bytes()
    print(f"   Size: {len(image_bytes):,} bytes")
    
    # Check LLM configuration
    provider = os.getenv('LLM_PROVIDER', 'mock')
    api_key = os.getenv('LLM_API_KEY', '')
    
    print(f"\n🔧 Configuration:")
    print(f"   LLM Provider: {provider}")
    print(f"   API Key: {'✓ Set' if api_key else '✗ Not set'}")
    
    if provider == 'mock':
        print("\n⚠️  WARNING: Using MOCK LLM (no real API calls)")
        print("   For real grading, set:")
        print("     export LLM_PROVIDER=openai")
        print("     export LLM_API_KEY=your_key")
    
    # Initialize services
    print(f"\n🚀 Initializing grading pipeline...")
    llm_service = app_module.LLMService()
    pipeline = app_module.GradingPipeline(llm_service)
    
    # Phase 1: Image Analysis
    print("\n" + "-"*80)
    print("PHASE 1: Image Analysis (LLM)")
    print("-"*80)
    
    try:
        analysis = await llm_service.analyze_image(image_bytes)
        
        print(f"\n✅ Analysis complete!")
        print(f"\n📝 Text Description:")
        text_desc = analysis.get('text_description', 'N/A')
        print(f"   {text_desc[:150]}{'...' if len(text_desc) > 150 else ''}")
        
        print(f"\n🎨 Drawing Description:")
        draw_desc = analysis.get('drawing_description', 'N/A')
        print(f"   {draw_desc[:150]}{'...' if len(draw_desc) > 150 else ''}")
        
        if 'steps' in analysis:
            print(f"\n📋 Extracted {len(analysis['steps'])} steps")
            for i, step in enumerate(analysis['steps'][:3], 1):
                print(f"   {i}. {step[:60]}...")
        
        if 'deductions' in analysis:
            print(f"\n⚠️  Initial deductions: {len(analysis['deductions'])}")
    
    except Exception as e:
        print(f"\n❌ Image analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return None
    
    # Phase 2-7: Full Grading Pipeline
    print("\n" + "-"*80)
    print("PHASES 2-7: Multi-Agent Grading Pipeline")
    print("-"*80)
    print("\nRunning:")
    print("  → StepExtractorAgent (A1)")
    print("  → ClaimGeneratorAgent (A2)")
    print("  → GeometryFormalizerAgent")
    print("  → FormalGeoStepGrader / MathVerifier (H1)")
    print("  → RubricScorerAgent (A3)")
    print("  → RefereeAgent (A4)")
    
    try:
        grading_result = await pipeline.grade(
            problem_id="diameter_right_angle",
            text_description=analysis.get("text_description", ""),
            drawing_description=analysis.get("drawing_description", ""),
            image_data=image_bytes,
            student_modified_drawing_description=None,
            expected_score=None,
            use_formalgeo=True  # Enable FormalGeo grading
        )
        
        print("\n✅ Grading pipeline complete!")
        
    except Exception as e:
        print(f"\n❌ Grading pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        return None
    
    # Display Results
    print("\n" + "="*80)
    print("GRADING RESULTS")
    print("="*80)
    
    # Final Score
    score = grading_result.get('score_total', 0)
    max_score = grading_result.get('score_max', 100)
    print(f"\n🎯 FINAL SCORE: {score}/{max_score}")
    
    # FormalGeo Status
    formalgeo_used = grading_result.get('formalgeo_used', False)
    print(f"\n🔬 FormalGeo Grading: {'✅ USED' if formalgeo_used else '❌ NOT USED'}")
    
    # Steps
    steps = grading_result.get('steps', [])
    print(f"\n📝 Steps Extracted: {len(steps)}")
    for i, step in enumerate(steps[:5], 1):
        print(f"   {i}. {step.get('raw_text', 'N/A')[:60]}...")
    if len(steps) > 5:
        print(f"   ... and {len(steps) - 5} more")
    
    # Claims
    claims = grading_result.get('claims', [])
    print(f"\n🔍 Claims Generated: {len(claims)}")
    for i, claim in enumerate(claims[:5], 1):
        claim_id = claim.get('claim_id', '?')
        claim_type = claim.get('type', '?')
        args = claim.get('args', [])
        print(f"   {i}. [{claim_id}] {claim_type}({', '.join(str(a) for a in args[:3])})")
    if len(claims) > 5:
        print(f"   ... and {len(claims) - 5} more")
    
    # Verification Results
    verification_results = grading_result.get('verification_results', [])
    true_count = sum(1 for r in verification_results if r.get('verdict') == 'true')
    false_count = sum(1 for r in verification_results if r.get('verdict') == 'false')
    unknown_count = sum(1 for r in verification_results if r.get('verdict') == 'unknown')
    
    print(f"\n✅ Verification Summary:")
    print(f"   ✓ True:    {true_count}")
    print(f"   ✗ False:   {false_count}")
    print(f"   ? Unknown: {unknown_count}")
    
    if false_count > 0:
        print(f"\n❌ Failed Claims:")
        for result in verification_results:
            if result.get('verdict') == 'false':
                claim_id = result.get('claim_id', '?')
                reason = result.get('reason_code', 'N/A')
                print(f"   - {claim_id}: {reason}")
    
    # Rubric Scores
    rubric_scores = grading_result.get('rubric_scores', [])
    print(f"\n💯 Rubric Breakdown:")
    for score in rubric_scores:
        item_id = score.get('rubric_item_id', '?')
        earned = score.get('earned', 0)
        max_pts = score.get('max', 0)
        notes = score.get('notes', 'N/A')
        print(f"   [{item_id}] {earned}/{max_pts} - {notes}")
    
    # FormalGeo Detailed Report
    if formalgeo_used and 'formalgeo_grading' in grading_result:
        fg = grading_result['formalgeo_grading']
        
        print(f"\n" + "-"*80)
        print("FORMALGEO DETAILED GRADING REPORT")
        print("-"*80)
        
        print(f"\n📊 FormalGeo Score: {fg.get('total_points', 0)}/100")
        print(f"🎯 Goal Reached: {fg.get('goal_reached', False)}")
        print(f"💯 Confidence: {fg.get('confidence', 0):.2f}")
        
        # Step-by-step feedback
        step_feedback = fg.get('step_feedback', [])
        if step_feedback:
            print(f"\n📝 Step-by-Step Verification:")
            for feedback in step_feedback[:10]:
                step_id = feedback.get('step_id', '?')
                is_valid = feedback.get('is_valid', False)
                status = "✓" if is_valid else "✗"
                
                if is_valid:
                    theorem = feedback.get('theorem_applied', 'N/A')
                    note = feedback.get('note', 'Valid')
                    print(f"   {status} Step {step_id}: {note} (theorem: {theorem})")
                else:
                    error = feedback.get('error_details', 'Invalid')
                    print(f"   {status} Step {step_id}: {error}")
        
        # Deductions
        deductions = fg.get('deductions', [])
        if deductions:
            print(f"\n❌ Point Deductions ({len(deductions)} total):")
            for d in deductions:
                points = d.get('deducted_points', 0)
                reason = d.get('deduction_reason', 'N/A')
                step = d.get('deduction_step', '?')
                conf = d.get('deduction_confidence_score', 0)
                print(f"\n   -{points} pts | {step}")
                print(f"   Reason: {reason}")
                print(f"   Confidence: {conf:.2f}")
        
        # Missing steps
        missing = fg.get('missing_steps', [])
        if missing:
            print(f"\n⚠️  Missing Steps:")
            for ms in missing:
                print(f"   - {ms.get('description', 'N/A')}")
        
        # Summary
        summary = fg.get('summary', 'N/A')
        print(f"\n📄 Summary:")
        print(f"   {summary}")
    
    # Referee Notes
    referee = grading_result.get('referee', {})
    if referee.get('referee_needed'):
        print(f"\n⚖️  Referee Notes:")
        print(f"   {referee.get('notes', 'N/A')}")
    
    # Save results
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    
    output_file = output_dir / f"e2e_result_{image_path.stem}.json"
    output_file.write_text(json.dumps({
        "image": str(image_path),
        "analysis": analysis,
        "grading": grading_result
    }, indent=2, ensure_ascii=False))
    
    print(f"\n💾 Full results saved to:")
    print(f"   {output_file}")
    
    print("\n" + "="*80)
    print("TEST COMPLETED")
    print("="*80 + "\n")
    
    return {
        "score": score,
        "max_score": max_score,
        "formalgeo_used": formalgeo_used,
        "analysis": analysis,
        "grading": grading_result
    }


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="End-to-end test of diameter-right angle problem grading"
    )
    parser.add_argument(
        '--image',
        default='tests/data/CorrectSolution2.png',
        help='Path to problem image (default: tests/data/CorrectSolution2.png)'
    )
    parser.add_argument(
        '--provider',
        default=os.getenv('LLM_PROVIDER', 'mock'),
        help='LLM provider: openai, anthropic, google, or mock (default: mock)'
    )
    parser.add_argument(
        '--api-key',
        default=os.getenv('LLM_API_KEY', ''),
        help='LLM API key (or set LLM_API_KEY env var)'
    )
    
    args = parser.parse_args()
    
    # Set environment variables
    os.environ['LLM_PROVIDER'] = args.provider
    if args.api_key:
        os.environ['LLM_API_KEY'] = args.api_key
    
    # Run test
    result = asyncio.run(run_e2e_test(args.image))
    
    if result:
        score = result['score']
        max_score = result['max_score']
        percentage = (score / max_score * 100) if max_score > 0 else 0
        
        print(f"\n{'='*80}")
        print(f"FINAL RESULT: {score}/{max_score} ({percentage:.1f}%)")
        print(f"FormalGeo Used: {'Yes' if result['formalgeo_used'] else 'No'}")
        print(f"{'='*80}\n")
        
        sys.exit(0)
    else:
        print("\n❌ Test failed\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
