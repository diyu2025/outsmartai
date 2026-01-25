import argparse
import asyncio
import json
import sys
from pathlib import Path

# Ensure backend/ is on sys.path for direct execution from tests/
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

try:
    import backend.app as app_module  # type: ignore
except ModuleNotFoundError:
    import app as app_module  # type: ignore


def summarize_verdicts(verification_results):
    true_claims = [r for r in verification_results if r.get("verdict") == "true"]
    false_claims = [r for r in verification_results if r.get("verdict") == "false"]
    unknown_claims = [r for r in verification_results if r.get("verdict") == "unknown"]

    solution_correct = len(false_claims) == 0 and len(unknown_claims) == 0 and len(true_claims) > 0
    return {
        "solution_correct": solution_correct,
        "true_count": len(true_claims),
        "false_count": len(false_claims),
        "unknown_count": len(unknown_claims),
        "false_ids": [r.get("claim_id") for r in false_claims],
        "unknown_ids": [r.get("claim_id") for r in unknown_claims],
    }


async def run_pipeline(image_path: Path, problem_id: int):
    image_bytes = image_path.read_bytes()
    llm_service = app_module.LLMService()
    pipeline = app_module.GradingPipeline(llm_service)

    analysis = await llm_service.analyze_image(image_bytes)
    text_description = analysis.get("text_description", "")
    drawing_description = analysis.get("drawing_description", "")

    grading = await pipeline.grade(
        problem_id=str(problem_id) if isinstance(problem_id, int) else problem_id,
        text_description=text_description,
        drawing_description=drawing_description,
        image_data=image_bytes,
        student_modified_drawing_description=None,
        expected_score=None,
    )

    summary = summarize_verdicts(grading.get("verification_results", []))
    return {"analysis": analysis, "grading": grading, "summary": summary}


def main():
    parser = argparse.ArgumentParser(description="Run A1/A2/H1 pipeline on a geometry solution image.")
    parser.add_argument("--image", required=True, help="Path to the prepared geometry problem/solution image (PNG).")
    parser.add_argument("--problem-id", type=int, default=1, help="Problem id label for bookkeeping.")
    args = parser.parse_args()

    result = asyncio.run(run_pipeline(Path(args.image), args.problem_id))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
