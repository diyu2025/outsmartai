#!/bin/bash
#
# Run End-to-End Test for Diameter-Right Angle Problem
#
# This script runs the complete grading pipeline:
# 1. Image Analysis (LLM)
# 2. Step Extraction (A1 Agent)
# 3. Claim Generation (A2 Agent)
# 4. Formalization (GeometryFormalizerAgent)
# 5. Verification (FormalGeoStepGrader)
# 6. Rubric Scoring (A3 Agent)
# 7. Referee (A4 Agent)
#

set -e  # Exit on error

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
BACKEND_DIR="/Users/yud/repo/outsmartai/backend"
FORMALGEO_VENV="/Users/yud/repo/FormalGeo/.venv/bin/python"
DEFAULT_IMAGE="tests/data/CorrectSolution2.png"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  E2E Test: Diameter-Right Angle Problem with FormalGeo        ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if in correct directory
if [ ! -f "app.py" ]; then
    echo -e "${RED}❌ Error: Must run from backend directory${NC}"
    echo "   cd /Users/yud/repo/outsmartai/backend"
    exit 1
fi

# Check environment variables
echo -e "${YELLOW}📋 Configuration:${NC}"
echo "   Backend dir: $BACKEND_DIR"
echo "   Python: $FORMALGEO_VENV"
echo "   LLM Provider: ${LLM_PROVIDER:-mock}"
echo "   LLM API Key: ${LLM_API_KEY:+Set ✓}"

if [ -z "$LLM_API_KEY" ]; then
    echo ""
    echo -e "${YELLOW}⚠️  WARNING: LLM_API_KEY not set${NC}"
    echo "   The test will run with MOCK LLM (fake data)"
    echo ""
    echo "   For real grading, set:"
    echo "     export LLM_PROVIDER=openai"
    echo "     export LLM_API_KEY=your_key"
    echo ""
    read -p "Continue with mock? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 0
    fi
fi

# Select image
IMAGE="${1:-$DEFAULT_IMAGE}"

if [ ! -f "$IMAGE" ]; then
    echo -e "${RED}❌ Error: Image not found: $IMAGE${NC}"
    echo ""
    echo "Available images:"
    ls -1 tests/data/*.png 2>/dev/null || echo "  No images found"
    echo ""
    echo "Usage: $0 [image_path]"
    exit 1
fi

echo ""
echo -e "${GREEN}✓ Using image: $IMAGE${NC}"
echo ""

# Run the test
echo -e "${BLUE}🚀 Starting E2E test...${NC}"
echo ""

$FORMALGEO_VENV tests/test_e2e_diameter.py --image "$IMAGE"

TEST_EXIT_CODE=$?

echo ""
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ Test completed successfully!${NC}"
else
    echo -e "${RED}❌ Test failed with exit code $TEST_EXIT_CODE${NC}"
fi

exit $TEST_EXIT_CODE
