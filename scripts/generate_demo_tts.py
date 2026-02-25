"""
데모 백업 영상용 TTS 나레이션 생성
Voice: Kore (한국어 여성) - 프로모 영상과 동일
"""
import requests
import base64
import json
import os
import sys
import wave
from pathlib import Path

API_KEY = "AIzaSyC4QWE49V0HK3PfC0CKi2DsI812VD8POD4"
OUTPUT_DIR = Path(__file__).parent.parent / "docs" / "01_presentation" / "demo_tts"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MODEL = "gemini-2.5-flash-preview-tts"
VOICE = "Kore"

# 데모 백업 영상 나레이션 (~45초)
# 영상 녹화 흐름: 대시보드 → 낙상감지 → 블러모드 → 이벤트/통계
TTS_LINES = [
    # Scene 1: 대시보드 그리드 뷰 (0~12초)
    {
        "id": "demo_01_dashboard",
        "text": "이것이 SENTIO의 실제 운영 화면입니다. 다중 카메라로 모든 구역을 한눈에 모니터링하고, 각 인원의 자세와 위험도가 실시간으로 표시됩니다.",
        "start": 0.0,
        "end": 11.0,
    },
    # Scene 2: 낙상 감지 시연 (12~24초)
    {
        "id": "demo_02_detection",
        "text": "낙상이 발생하면, 상태가 안전에서 위험으로 즉시 전환되고, 알림이 자동 생성됩니다. 위치와 시간, 신뢰도까지 한 번에 확인할 수 있습니다.",
        "start": 12.0,
        "end": 24.0,
    },
    # Scene 3: 프라이버시 블러 모드 (25~34초)
    {
        "id": "demo_03_privacy",
        "text": "프라이버시 보호를 위한 블러 모드에서도, 얼굴 없이 골격 정보만으로 정확한 감지가 가능합니다.",
        "start": 25.0,
        "end": 34.0,
    },
    # Scene 4: 이벤트 기록 + 통계 (35~45초)
    {
        "id": "demo_04_stats",
        "text": "모든 이벤트는 자동으로 기록되어, 언제 어디서 어떤 유형인지 추적되고, 통계 페이지에서 시간대별, 구역별 패턴을 분석할 수 있습니다.",
        "start": 35.0,
        "end": 45.0,
    },
]

# 자막 데이터 (TTS와 동기화)
SUBTITLES = [
    {"start": 0.0,  "end": 5.5,  "text": "이것이 SENTIO의 실제 운영 화면입니다."},
    {"start": 5.5,  "end": 8.5,  "text": "다중 카메라로 모든 구역을 한눈에 모니터링하고,"},
    {"start": 8.5,  "end": 11.0, "text": "각 인원의 자세와 위험도가 실시간으로 표시됩니다."},
    {"start": 12.0, "end": 16.0, "text": "낙상이 발생하면, 상태가 안전에서 위험으로 즉시 전환되고,"},
    {"start": 16.0, "end": 19.0, "text": "알림이 자동 생성됩니다."},
    {"start": 19.0, "end": 24.0, "text": "위치와 시간, 신뢰도까지 한 번에 확인할 수 있습니다."},
    {"start": 25.0, "end": 29.5, "text": "프라이버시 보호를 위한 블러 모드에서도,"},
    {"start": 29.5, "end": 34.0, "text": "얼굴 없이 골격 정보만으로 정확한 감지가 가능합니다."},
    {"start": 35.0, "end": 39.0, "text": "모든 이벤트는 자동으로 기록되어,"},
    {"start": 39.0, "end": 42.0, "text": "언제 어디서 어떤 유형인지 추적되고,"},
    {"start": 42.0, "end": 45.0, "text": "통계 페이지에서 시간대별, 구역별 패턴을 분석할 수 있습니다."},
]


def generate_tts(text: str, filename: str) -> str | None:
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

                        out_path = OUTPUT_DIR / f"{filename}.wav"

                        if audio_bytes[:4] == b"RIFF":
                            with open(out_path, "wb") as f:
                                f.write(audio_bytes)
                        else:
                            with wave.open(str(out_path), 'wb') as wf:
                                wf.setnchannels(1)
                                wf.setsampwidth(2)
                                wf.setframerate(24000)
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


def save_subtitles():
    """자막 데이터를 JSON으로 저장"""
    srt_path = OUTPUT_DIR / "subtitles.json"
    with open(srt_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_duration": 45.0,
            "tts_files": [
                {"id": t["id"], "file": f"{t['id']}.wav", "start": t["start"], "end": t["end"]}
                for t in TTS_LINES
            ],
            "subtitles": SUBTITLES,
        }, f, ensure_ascii=False, indent=2)
    print(f"\nSubtitles saved: {srt_path}")


def main():
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

    # 자막 JSON 항상 저장
    save_subtitles()

    if results:
        print("\nGenerated files:")
        for fid, path in results.items():
            print(f"  {fid}: {path}")


if __name__ == "__main__":
    main()
