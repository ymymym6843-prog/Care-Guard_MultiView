"""
Skeleton Blackbox - 관절 좌표 블랙박스

최근 20초(~600프레임) 관절 좌표를 메모리에 임시 보관합니다.
DANGER 이벤트 발생 시 JSON으로 덤프하여 사후 분석에 활용합니다.
원본 영상은 절대 저장하지 않으며, 비식별 좌표 데이터만 기록합니다.
"""

import hashlib
import json
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger("app.services.skeleton_blackbox")


@dataclass
class PersonSnapshot:
    """개인별 스냅샷 (비식별 데이터만)"""
    track_id: str               # 비식별 추적 ID (환자 실명 아님)
    landmarks: list[list[float]]  # 33개 관절 [[x, y, z, visibility], ...]
    posture: str                # "standing", "sitting", "lying"
    confidence: float           # 낙상 확신도


@dataclass
class FrameRecord:
    """프레임 단위 기록"""
    timestamp: float            # Unix timestamp
    persons: list[PersonSnapshot] = field(default_factory=list)


class SkeletonBlackbox:
    """
    최근 N초(기본 20초, ~600프레임@30fps) 관절 좌표를 메모리에 임시 보관.
    DANGER 이벤트 발생 시 JSON으로 덤프.
    """

    def __init__(self, buffer_seconds: int = 20, fps: int = 30):
        self._buffer_seconds = buffer_seconds
        self._fps = fps
        self._buffer: deque[FrameRecord] = deque(maxlen=buffer_seconds * fps)
        self._incident_dir = Path("incidents")
        self._incident_dir.mkdir(exist_ok=True)

    @property
    def enabled(self) -> bool:
        return getattr(settings, "SKELETON_BLACKBOX_ENABLED", True)

    def record(self, timestamp: float, persons: list[PersonSnapshot]) -> None:
        """프레임별 전체 인원 좌표 기록"""
        if not self.enabled:
            return
        self._buffer.append(FrameRecord(
            timestamp=timestamp,
            persons=persons,
        ))

    def dump_incident(
        self,
        event_id: str,
        trigger_person: str = "",
        trigger_type: str = "DANGER",
    ) -> Path | None:
        """
        DANGER 이벤트 시 호출.
        버퍼 전체를 JSON 파일로 저장.
        저장 데이터: 좌표 + posture + confidence (원본 프레임 없음)
        """
        if not self._buffer:
            logger.warning("블랙박스 버퍼 비어있음, 덤프 건너뜀: event=%s", event_id)
            return None

        now_str = time.strftime("%Y%m%d_%H%M%S")
        incident_id = f"fall_{now_str}"

        # 프레임 데이터 변환
        buffer_list = list(self._buffer)
        start_ts = buffer_list[0].timestamp
        frames_data = []
        for record in buffer_list:
            frame_entry = {
                "t": round(record.timestamp - start_ts, 3),
                "persons": [],
            }
            for person in record.persons:
                frame_entry["persons"].append({
                    "id": person.track_id,
                    "posture": person.posture,
                    "confidence": round(person.confidence, 4),
                    "landmarks": person.landmarks,
                })
            frames_data.append(frame_entry)

        # 전체 JSON 구성
        incident_data = {
            "incident_id": incident_id,
            "triggered_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            "trigger_person": trigger_person,
            "trigger_type": trigger_type,
            "buffer_start": time.strftime(
                "%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(start_ts)
            ),
            "buffer_end": time.strftime(
                "%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(buffer_list[-1].timestamp)
            ),
            "fps": self._fps,
            "total_frames": len(frames_data),
            "frames": frames_data,
            "privacy_notice": (
                "이 파일은 비식별 관절 좌표만 포함하며, "
                "원본 영상은 저장되지 않았습니다."
            ),
        }

        # 해시 필드를 먼저 삽입 (플레이스홀더), 직렬화, 해시 계산, 최종 치환
        incident_data["system_trace_hash"] = ""
        json_str = json.dumps(incident_data, ensure_ascii=False, indent=2)
        data_hash = hashlib.sha256(json_str.encode()).hexdigest()
        incident_data["system_trace_hash"] = f"sha256:{data_hash[:12]}"

        # 파일 저장
        self._incident_dir.mkdir(exist_ok=True)
        out_path = self._incident_dir / f"{incident_id}.json"
        out_path.write_text(
            json.dumps(incident_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        logger.info(
            "블랙박스 덤프 완료: %s (%d프레임, hash=%s)",
            out_path, len(frames_data), data_hash[:12],
        )
        return out_path

    def get_buffer_stats(self) -> dict:
        """현재 버퍼 상태"""
        if not self._buffer:
            return {
                "frame_count": 0,
                "time_range_sec": 0.0,
                "person_count": 0,
                "buffer_capacity": self._buffer.maxlen,
            }

        buffer_list = list(self._buffer)
        time_range = buffer_list[-1].timestamp - buffer_list[0].timestamp
        all_person_ids = set()
        for record in buffer_list:
            for person in record.persons:
                all_person_ids.add(person.track_id)

        return {
            "frame_count": len(buffer_list),
            "time_range_sec": round(time_range, 2),
            "person_count": len(all_person_ids),
            "buffer_capacity": self._buffer.maxlen,
        }

    def clear(self) -> None:
        """버퍼 초기화"""
        self._buffer.clear()

    def list_incidents(self) -> list[dict]:
        """저장된 사건 목록"""
        incidents = []
        if not self._incident_dir.exists():
            return incidents

        for f in sorted(self._incident_dir.glob("fall_*.json"), reverse=True):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                incidents.append({
                    "incident_id": data.get("incident_id", f.stem),
                    "triggered_at": data.get("triggered_at", ""),
                    "trigger_person": data.get("trigger_person", ""),
                    "trigger_type": data.get("trigger_type", ""),
                    "total_frames": data.get("total_frames", 0),
                    "file": str(f),
                })
            except (json.JSONDecodeError, OSError):
                continue
        return incidents

    def get_incident(self, incident_id: str) -> dict | None:
        """사건 상세 데이터 조회"""
        file_path = self._incident_dir / f"{incident_id}.json"
        if not file_path.exists():
            return None
        try:
            return json.loads(file_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None


# 싱글턴
skeleton_blackbox = SkeletonBlackbox(
    buffer_seconds=getattr(settings, "SKELETON_BLACKBOX_SECONDS", 20),
    fps=30,
)
