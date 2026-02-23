"""
Gemini API를 사용하여 SENTIO 프레젠테이션용 이미지를 생성합니다.
gemini-2.5-flash-image 모델 사용.
"""
import base64
import os
from pathlib import Path
from google import genai
from google.genai import types

API_KEY = os.environ.get("GEMINI_API_KEY", "")
OUTPUT_DIR = Path(__file__).parent / "gen_images"
OUTPUT_DIR.mkdir(exist_ok=True)

client = genai.Client(api_key=API_KEY)

IMAGES = [
    {
        "name": "slide2_hospital_fall",
        "prompt": (
            "Generate a photorealistic image: A wide shot of a dimly lit modern hospital corridor. "
            "An elderly patient wearing a hospital gown has fallen on the clean white floor near a waiting bench. "
            "Cinematic lighting with cool blue tones, conveying urgency and the need for monitoring. "
            "Professional medical environment. 16:9 wide landscape format. No text or watermarks."
        ),
    },
    {
        "name": "slide5_ai_pose_analysis",
        "prompt": (
            "Generate a digital art image: A futuristic AI human pose detection visualization. "
            "A translucent human figure standing in the center with glowing teal and blue "
            "keypoint dots at all major joints connected by luminous lines. "
            "Dark navy background with subtle digital grid. "
            "Neural network nodes floating around the figure. "
            "High-tech medical AI concept art. 16:9 wide landscape format. No text."
        ),
    },
    {
        "name": "slide8_privacy_shield",
        "prompt": (
            "Generate a digital art image: Data privacy and cybersecurity concept. "
            "A large glowing blue translucent shield with a padlock symbol in the center. "
            "Streams of small floating numbers and data particles flowing behind the shield. "
            "Dark navy-blue background. Futuristic and minimal design. "
            "16:9 wide landscape format. No text."
        ),
    },
    {
        "name": "slide3_smart_cctv",
        "prompt": (
            "Generate a digital art image: A sleek modern white CCTV security camera mounted on a ceiling. "
            "Futuristic holographic AI overlay projecting from the camera lens downward. "
            "The hologram shows wireframe human body skeleton outlines being analyzed. "
            "Dark room environment with teal and blue accent lighting. "
            "16:9 wide landscape format. No text."
        ),
    },
]


def generate_image(prompt: str, name: str) -> str | None:
    """Gemini 2.5 Flash Image 모델로 이미지를 생성합니다."""
    print(f"\n[생성중] {name}...")
    print(f"  프롬프트: {prompt[:80]}...")

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash-image",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE", "TEXT"],
            ),
        )

        # 응답에서 이미지 파트 찾기
        if response.candidates and response.candidates[0].content:
            for part in response.candidates[0].content.parts or []:
                if part.inline_data and part.inline_data.mime_type and part.inline_data.mime_type.startswith("image/"):
                    img_bytes = part.inline_data.data
                    if img_bytes:
                        filepath = OUTPUT_DIR / f"{name}.png"
                        with open(filepath, "wb") as f:
                            f.write(img_bytes)
                        print(f"  [완료] {filepath} ({len(img_bytes):,} bytes)")

                        b64 = base64.b64encode(img_bytes).decode()
                        b64_path = OUTPUT_DIR / f"{name}.b64"
                        with open(b64_path, "w") as f:
                            f.write(b64)
                        return str(filepath)

        print("  [실패] 이미지가 생성되지 않았습니다.")
        if response.candidates and response.candidates[0].content:
            for part in response.candidates[0].content.parts or []:
                if part.text:
                    print(f"  응답: {part.text[:300]}")
        return None

    except Exception as e:
        print(f"  [에러] {e}")
        return None


def main():
    print("=" * 60)
    print("SENTIO 프레젠테이션 이미지 생성 (gemini-2.5-flash-image)")
    print("=" * 60)

    results = {}
    for img_config in IMAGES:
        result = generate_image(img_config["prompt"], img_config["name"])
        results[img_config["name"]] = result

    print("\n" + "=" * 60)
    print("생성 결과:")
    for name, path in results.items():
        status = "OK" if path else "FAILED"
        print(f"  [{status}] {name}: {path or 'N/A'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
