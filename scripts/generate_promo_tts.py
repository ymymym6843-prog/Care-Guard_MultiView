"""
Gemini TTS API를 사용한 프로모 영상 나레이션 생성
Voice: Kore (한국어 여성)
"""
import requests
import base64
import json
import os
import sys
import struct
import wave
import io
from pathlib import Path

API_KEY = "AIzaSyBPZ06GvA8t41xhuYC_4Rf43uoUSSxgu1A"
OUTPUT_DIR = Path(__file__).parent.parent / "docs" / "01_presentation" / "tts_audio"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MODEL = "gemini-2.5-flash-preview-tts"
VOICE = "Kore"

# TTS 텍스트 목록 - 장면별
TTS_LINES = [
    # Scene 1: Hook
    {"id": "s1_hook", "text": "매년, 노인 세 명 중 한 명이 넘어집니다."},
    {"id": "s1_danger", "text": "발견이 늦으면, 생명이 위험합니다."},

    # Scene 2: Problem
    {"id": "s2_stat", "text": "낙상의 47%가 대기실과 복도에서 발생합니다."},
    {"id": "s2_nurse", "text": "간호사 1명이 환자 30명을 담당합니다. 24시간 감시는 불가능합니다."},

    # Scene 3: Solution
    {"id": "s3_solution", "text": "SENTIO AI가 해결합니다."},

    # Scene 4: Demo
    {"id": "s4_realtime", "text": "기존 CCTV 영상을 AI가 실시간으로 분석합니다."},
    {"id": "s4_detect", "text": "환자가 넘어지는 순간, 자동으로 감지합니다."},
    {"id": "s4_alert", "text": "즉시 알림을 전송하여 빠르게 대응할 수 있습니다."},

    # Scene 5: Multi-angle
    {"id": "s5_angles", "text": "전방, 후방, 측면. 어떤 각도에서든 정확하게 감지합니다."},
    {"id": "s5_normal", "text": "정상 행동은 정상으로. 낙상만 정확히 구별합니다."},

    # Scene 6: Results
    {"id": "s6_verified", "text": "424개 실제 영상으로 검증된 성능입니다."},
    {"id": "s6_stats", "text": "감지율 95.2%, 정밀도 94.6%. 20건 중 19건을 정확히 감지합니다."},

    # Scene 7: Dashboard (NEW)
    {"id": "s7_dashboard", "text": "실제 대시보드에서 여러 카메라를 한눈에 모니터링합니다."},
    {"id": "s7_pip", "text": "PiP 모드로 주요 카메라를 확대하여 집중 관찰할 수 있습니다."},

    # Scene 8: Features
    {"id": "s8_features", "text": "기존 CCTV 활용, 프라이버시 보호, 다중 환자 동시 추적까지."},

    # Scene 9: Closing
    {"id": "s9_closing", "text": "넘어지기 전에, 미리 지킵니다. 전조증상 감지부터 낙상 대응까지. SENTIO AI."},
]


def generate_tts(text: str, filename: str) -> bool:
    """Gemini TTS API로 음성 생성"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"

    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": VOICE
                    }
                }
            }
        }
    }

    print(f"  Generating: {filename}...")
    try:
        resp = requests.post(url, json=payload, timeout=60)
        if resp.status_code == 200:
            data = resp.json()
            for cand in data.get("candidates", []):
                for part in cand.get("content", {}).get("parts", []):
                    if "inlineData" in part:
                        audio_b64 = part["inlineData"]["data"]
                        audio_bytes = base64.b64decode(audio_b64)
                        mime = part["inlineData"].get("mimeType", "audio/wav")

                        out_path = OUTPUT_DIR / f"{filename}.wav"

                        # Check if already valid WAV (starts with RIFF)
                        if audio_bytes[:4] == b"RIFF":
                            with open(out_path, "wb") as f:
                                f.write(audio_bytes)
                        else:
                            # Raw PCM data - wrap in WAV container
                            # Gemini TTS returns 24kHz 16-bit mono PCM
                            sample_rate = 24000
                            channels = 1
                            sample_width = 2  # 16-bit
                            with wave.open(str(out_path), 'wb') as wf:
                                wf.setnchannels(channels)
                                wf.setsampwidth(sample_width)
                                wf.setframerate(sample_rate)
                                wf.writeframes(audio_bytes)

                        final_size = os.path.getsize(out_path)
                        print(f"    OK: {out_path.name} ({final_size/1024:.0f}KB)")
                        return str(out_path)
            print(f"    No audio in response: {json.dumps(data, indent=2)[:500]}")
        else:
            print(f"    HTTP {resp.status_code}: {resp.text[:300]}")
    except Exception as e:
        print(f"    Error: {e}")
    return None


def main():
    # Parse args - allow generating specific items or all
    targets = TTS_LINES
    if len(sys.argv) > 1:
        filter_ids = sys.argv[1:]
        targets = [t for t in TTS_LINES if t["id"] in filter_ids]
        if not targets:
            print(f"No matching IDs found. Available: {[t['id'] for t in TTS_LINES]}")
            return

    print(f"Output dir: {OUTPUT_DIR}")
    print(f"Model: {MODEL}, Voice: {VOICE}")
    print(f"Generating {len(targets)} TTS files...\n")

    success = 0
    results = {}
    for item in targets:
        result = generate_tts(item["text"], item["id"])
        if result:
            success += 1
            results[item["id"]] = result

    print(f"\nDone: {success}/{len(targets)} files generated")

    if results:
        print("\nGenerated files:")
        for fid, path in results.items():
            print(f"  {fid}: {path}")


if __name__ == "__main__":
    main()
