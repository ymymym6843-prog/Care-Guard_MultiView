"""
Gemini API를 사용한 발표자료용 이미지 생성
"""
import requests
import base64
import json
import os
from pathlib import Path

API_KEY = "AIzaSyBPZ06GvA8t41xhuYC_4Rf43uoUSSxgu1A"
OUTPUT_DIR = Path(__file__).parent.parent / "docs" / "01_presentation" / "gen_images"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def generate_image(prompt, filename):
    """Gemini Imagen API로 이미지 생성"""
    # Gemini 2.5 Flash Image 모델 사용
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent?key={API_KEY}"

    payload = {
        "contents": [{"parts": [{"text": f"Generate a high-quality, professional presentation image (16:9 aspect ratio): {prompt}"}]}],
        "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]}
    }

    print(f"Generating: {filename}...")
    try:
        resp = requests.post(url, json=payload, timeout=120)
        if resp.status_code == 200:
            data = resp.json()
            for cand in data.get("candidates", []):
                for part in cand.get("content", {}).get("parts", []):
                    if "inlineData" in part:
                        img_b64 = part["inlineData"]["data"]
                        img_bytes = base64.b64decode(img_b64)
                        mime = part["inlineData"].get("mimeType", "image/png")
                        ext = "png" if "png" in mime else "jpg"
                        out_path = OUTPUT_DIR / filename.replace(".png", f".{ext}")
                        with open(out_path, "wb") as f:
                            f.write(img_bytes)
                        print(f"  OK: {out_path.name} ({len(img_bytes)/1024:.0f}KB)")
                        return True
            print(f"  No image in response: {json.dumps(data, indent=2)[:500]}")
        else:
            print(f"  HTTP {resp.status_code}: {resp.text[:300]}")
    except Exception as e:
        print(f"  Error: {e}")
    return False


# 생성할 이미지 목록
IMAGES = [
    {
        "prompt": "A modern hospital corridor with elderly patients sitting in a waiting room. One elderly person is falling down while a nurse at a distant station cannot see them. Clean, professional medical illustration style with blue and white tones. No text overlay.",
        "filename": "slide2_hospital_fall.png"
    },
    {
        "prompt": "A futuristic AI monitoring dashboard on a large screen showing multiple CCTV camera feeds of a hospital. Green bounding boxes around people walking normally, one screen shows a red alert with a person fallen on the ground. Dark themed UI with blue and cyan accents. Professional tech visualization.",
        "filename": "slide3_ai_dashboard.png"
    },
    {
        "prompt": "Split screen comparison: Left side shows a radar sensor device mounted on ceiling (labeled style). Right side shows a regular CCTV security camera with AI overlay showing skeleton keypoints on a person. Professional product comparison style, clean white background.",
        "filename": "slide6_competitor_compare.png"
    },
    {
        "prompt": "Infographic showing elderly care market growth. A shield icon protecting elderly people, surrounded by hospital buildings and technology elements. Korean healthcare theme with blue, cyan, and green colors. Professional business presentation style. No text.",
        "filename": "slide8_market.png"
    },
]

def main():
    print(f"Output dir: {OUTPUT_DIR}")
    success = 0
    for img in IMAGES:
        if generate_image(img["prompt"], img["filename"]):
            success += 1
    print(f"\nDone: {success}/{len(IMAGES)} images generated")

if __name__ == "__main__":
    main()
