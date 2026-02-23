"""
Edge TTS 프리렌더링 스크립트

음성: ko-KR-SunHiNeural (여성, 자연스러운 한국어)

사용법:
  python scripts/generate_tts.py              # 전체 재생성
  python scripts/generate_tts.py --warning    # warning만 재생성
  python scripts/generate_tts.py --fall       # fall만 재생성
  python scripts/generate_tts.py --danger     # danger만 재생성
"""

import argparse
import asyncio
import os
import sys

import edge_tts

VOICE = "ko-KR-SunHiNeural"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "public", "audio")

ALERTS = {
    "warning": {
        "filename": "alert_warning.mp3",
        "text": "주의! 낙상 위험 감지!",
        "rate": "+20%",
        "pitch": "+5Hz",
    },
    "fall": {
        "filename": "alert_fall.mp3",
        "text": "경고! 낙상 발생!",
        "rate": "+30%",
        "pitch": "+10Hz",
    },
    "danger": {
        "filename": "alert_danger.mp3",
        "text": "긴급! 낙상 발생! 즉시 확인하세요!",
        "rate": "+25%",
        "pitch": "+15Hz",
    },
}


async def generate_audio(key: str, alert: dict) -> bool:
    """단일 알림 음성 생성"""
    print(f"[{key}] 생성 중: {alert['filename']}...")

    try:
        out_path = os.path.join(OUTPUT_DIR, alert["filename"])

        communicate = edge_tts.Communicate(
            text=alert["text"],
            voice=VOICE,
            rate=alert.get("rate", "+0%"),
            pitch=alert.get("pitch", "+0Hz"),
        )
        await communicate.save(out_path)

        size_kb = os.path.getsize(out_path) / 1024
        print(f"  -> {out_path} ({size_kb:.1f} KB)")
        return True

    except Exception as e:
        print(f"  [{key}] 생성 실패: {e}")
        return False


async def main():
    parser = argparse.ArgumentParser(description="Edge TTS 알림 음성 생성")
    parser.add_argument("--warning", action="store_true", help="warning(전조)만 생성")
    parser.add_argument("--fall", action="store_true", help="fall(실제 낙상)만 생성")
    parser.add_argument("--danger", action="store_true", help="danger(위험)만 생성")
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"출력 디렉토리: {OUTPUT_DIR}")
    print(f"음성: {VOICE}\n")

    # 특정 항목만 또는 전체
    targets = {}
    if args.warning:
        targets["warning"] = ALERTS["warning"]
    if args.fall:
        targets["fall"] = ALERTS["fall"]
    if args.danger:
        targets["danger"] = ALERTS["danger"]
    if not targets:
        targets = ALERTS

    results = {}
    for key, alert in targets.items():
        results[key] = await generate_audio(key, alert)

    print()
    all_ok = all(results.values())
    if all_ok:
        print("완료! 모든 음성 파일이 생성되었습니다.")
    else:
        failed = [k for k, v in results.items() if not v]
        print(f"일부 실패: {', '.join(failed)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
