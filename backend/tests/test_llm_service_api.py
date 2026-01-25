import base64
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, mock_open, patch

from PIL import Image, ImageDraw

try:
    import backend.app as app_module
except ModuleNotFoundError:
    import app as app_module


def _get_test_image_bytes() -> bytes:
    """
    Returns image bytes for tests.

    If you want to test with a real image, drop one in:
      `backend/tests/fixtures/test.png`
    or set:
      `TEST_IMAGE_PATH=/absolute/or/relative/path.png`
    """
    
    # env_path = r"C:\Users\georg\repo\outsmartai\backend\tests\data\CorrectSolution1.png"
    # env_path = r"C:\Users\georg\repo\outsmartai\backend\tests\data\WrongSolution1.png"
    # env_path = r"C:\Users\georg\repo\outsmartai\backend\tests\data\CorrectSolution2.png"
    env_path = r"/Users/yud/repo/outsmartai/backend/tests/data/CorrectSolution2.png"
    if env_path:
        fixture_path = Path(env_path).expanduser()
        if fixture_path.exists():
            return fixture_path.read_bytes()

    default_fixture = Path(__file__).resolve().parent / "fixtures" / "test.png"
    if default_fixture.exists():
        return default_fixture.read_bytes()

    image = Image.new("RGB", (120, 60), color="white")
    draw = ImageDraw.Draw(image)
    draw.text((5, 5), "Hello", fill="black")

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class LLMServiceApiTests(unittest.TestCase):
    def setUp(self) -> None:
        app_module.app.config.update(TESTING=True)
        self.client = app_module.app.test_client()

    def test_analyze_accepts_base64_image_and_calls_llm(self) -> None:
        image_bytes = _get_test_image_bytes()
        payload = {"image": base64.b64encode(image_bytes).decode("utf-8")}

        fake_result = {
            "text_recognition": "ok",
            "visual_elements": "ok",
            "content_analysis": "ok",
            "suggestions": ["ok"],
            "confidence": 0.9,
        }

        with patch.object(app_module, "save_image_backup", return_value="dummy.png"), patch.object(
            app_module.llm_service, "analyze_image", new_callable=AsyncMock
        ) as analyze_mock, patch.object(app_module.os, "makedirs"), patch(
            "builtins.open", mock_open()
        ):
            analyze_mock.return_value = fake_result

            response = self.client.post("/analyze", json=payload)

        print(f'response:{response}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), fake_result)
        analyze_mock.assert_awaited_once()
        self.assertEqual(analyze_mock.call_args.args[0], image_bytes)

    @unittest.skipUnless(
        os.getenv("RUN_LLM_INTEGRATION") == "1",
        "Set RUN_LLM_INTEGRATION=1 (and LLM_PROVIDER/LLM_API_KEY) to run the real LLM integration test.",
    )
    def test_analyze_triggers_real_llm_when_enabled(self) -> None:
        provider = os.getenv("LLM_PROVIDER", "mock")
        api_key = os.getenv("LLM_API_KEY")
        if provider == "mock":
            self.skipTest("LLM_PROVIDER=mock; set to openai/anthropic/google to run integration test.")
        if not api_key:
            self.skipTest("LLM_API_KEY is missing; set it to run integration test.")

        # app.py reads env at import-time; re-initialize the service with the current env.
        app_module.LLM_PROVIDER = provider
        app_module.LLM_API_KEY = api_key
        app_module.llm_service = app_module.LLMService()

        image_bytes = _get_test_image_bytes()
        payload = {"image": base64.b64encode(image_bytes).decode("utf-8")}

        with patch.object(app_module, "save_image_backup", return_value="dummy.png"), patch.object(
            app_module.os, "makedirs"
        ), patch("builtins.open", mock_open()), patch.object(
            app_module.LLMService, "_get_mock_response", side_effect=AssertionError("Unexpected fallback to mock response")
        ):
            response = self.client.post("/analyze", json=payload)

        self.assertEqual(response.status_code, 200)
        result = response.get_json()

        if os.getenv("PRINT_LLM_RESPONSE") == "1":
            print(json.dumps(result, indent=2, ensure_ascii=False), flush=True)
        response_out = os.getenv("LLM_RESPONSE_OUT")
        if response_out:
            out_path = Path(response_out).expanduser()
            out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

        self.assertIsInstance(result, dict)
        # self.assertIn("text_recognition", result)
        # self.assertIn("visual_elements", result)
        # self.assertIn("content_analysis", result)
        # self.assertIn("suggestions", result)
        # self.assertIn("confidence", result)

    # def test_analyze_missing_image_returns_400(self) -> None:
    #     response = self.client.post("/analyze", json={})
    #     self.assertEqual(response.status_code, 400)
    #     self.assertIn("error", response.get_json())

    # def test_analyze_invalid_base64_returns_400(self) -> None:
    #     response = self.client.post("/analyze", json={"image": "not_base64$$$"})
    #     self.assertEqual(response.status_code, 400)
    #     self.assertIn("Invalid base64 image data", response.get_json().get("error", ""))

    # def test_analyze_invalid_image_returns_400(self) -> None:
    #     payload = {"image": base64.b64encode(b"not an image").decode("utf-8")}
    #     with patch.object(app_module.os, "makedirs"), patch("builtins.open", mock_open()):
    #         response = self.client.post("/analyze", json=payload)
    #     self.assertEqual(response.status_code, 400)
    #     self.assertIn("Invalid image format", response.get_json().get("error", ""))

    # def test_process_image_accepts_multipart_and_calls_llm(self) -> None:
    #     image_bytes = _get_test_image_bytes()

    #     fake_analysis = {
    #         "text_recognition": "ok",
    #         "visual_elements": "ok",
    #         "content_analysis": "ok",
    #         "suggestions": ["ok"],
    #         "confidence": 0.9,
    #     }

    #     data = {"image": (io.BytesIO(image_bytes), "test.png")}

    #     with patch.object(app_module, "save_image_backup", return_value="dummy.png"), patch.object(
    #         app_module.llm_service, "analyze_image", new_callable=AsyncMock
    #     ) as analyze_mock:
    #         analyze_mock.return_value = fake_analysis

    #         response = self.client.post("/api/process-image", data=data, content_type="multipart/form-data")

    #     self.assertEqual(response.status_code, 200)
    #     response_json = response.get_json()
    #     self.assertTrue(response_json["success"])
    #     self.assertEqual(response_json["analysis"], fake_analysis)
    #     analyze_mock.assert_awaited_once()
    #     self.assertEqual(analyze_mock.call_args.args[0], image_bytes)

    # def test_process_image_missing_file_returns_400(self) -> None:
    #     response = self.client.post("/api/process-image", data={}, content_type="multipart/form-data")
    #     self.assertEqual(response.status_code, 400)
    #     self.assertFalse(response.get_json().get("success", True))


if __name__ == "__main__":
    unittest.main()
