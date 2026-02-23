"""
HL7 FHIR 연동 서비스

낙상 이벤트를 FHIR Observation 리소스로 변환하여
EMR/HIS 시스템에 전송합니다.

FHIR R4 스펙을 따릅니다: https://www.hl7.org/fhir/observation.html
"""

import json
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger("app.services.fhir")


class FHIRService:
    """HL7 FHIR Observation 연동"""

    def __init__(self):
        self._base_url: str = ""  # FHIR 서버 URL (설정에서 주입)
        self._api_key: str = ""
        self._client: httpx.AsyncClient | None = None

    def configure(self, base_url: str, api_key: str = "") -> None:
        """FHIR 서버 연결 설정"""
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        # 재사용 가능한 HTTP 클라이언트 (커넥션 풀링)
        self._client = httpx.AsyncClient(
            timeout=10.0,
            limits=httpx.Limits(max_connections=5, max_keepalive_connections=2),
        )
        logger.info("FHIR 서비스 설정: %s", self._base_url)

    @property
    def enabled(self) -> bool:
        return bool(self._base_url)

    def create_fall_observation(
        self,
        *,
        event_id: int,
        timestamp: datetime,
        alert_level: str,
        duration: float,
        confidence: float,
        person_id: str = "",
        camera_id: str = "default",
    ) -> dict[str, Any]:
        """낙상 이벤트를 FHIR Observation 리소스로 변환

        Returns:
            dict: FHIR Observation 리소스 (JSON-serializable)
        """
        return {
            "resourceType": "Observation",
            "status": "final",
            "category": [
                {
                    "coding": [
                        {
                            "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                            "code": "activity",
                            "display": "Activity",
                        }
                    ]
                }
            ],
            "code": {
                "coding": [
                    {
                        "system": "http://snomed.info/sct",
                        "code": "129839007",
                        "display": "Fall - Loss of Balance",
                    }
                ],
                "text": "낙상 감지 이벤트",
            },
            "effectiveDateTime": timestamp.isoformat(),
            "issued": datetime.now(timezone.utc).isoformat(),
            "valueString": alert_level,
            "component": [
                {
                    "code": {
                        "coding": [{"system": "urn:sentio", "code": "duration"}],
                        "text": "낙상 지속 시간",
                    },
                    "valueQuantity": {
                        "value": round(duration, 1),
                        "unit": "s",
                        "system": "http://unitsofmeasure.org",
                        "code": "s",
                    },
                },
                {
                    "code": {
                        "coding": [{"system": "urn:sentio", "code": "confidence"}],
                        "text": "감지 신뢰도",
                    },
                    "valueQuantity": {
                        "value": round(confidence, 3),
                        "unit": "%",
                        "system": "http://unitsofmeasure.org",
                        "code": "%",
                    },
                },
                {
                    "code": {
                        "coding": [{"system": "urn:sentio", "code": "camera_id"}],
                        "text": "카메라 ID",
                    },
                    "valueString": camera_id,
                },
                {
                    "code": {
                        "coding": [{"system": "urn:sentio", "code": "person_id"}],
                        "text": "인원 추적 ID",
                    },
                    "valueString": person_id,
                },
            ],
            "identifier": [
                {
                    "system": "urn:sentio:event",
                    "value": str(event_id),
                }
            ],
        }

    async def send_observation(self, observation: dict) -> bool:
        """FHIR 서버에 Observation 전송

        Returns:
            bool: 전송 성공 여부
        """
        if not self.enabled:
            logger.debug("FHIR 서비스 미설정 - 전송 건너뜀")
            return False

        url = f"{self._base_url}/Observation"
        headers = {
            "Content-Type": "application/fhir+json",
            "Accept": "application/fhir+json",
        }
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            client = self._client or httpx.AsyncClient(timeout=10.0)
            response = await client.post(
                url,
                json=observation,
                headers=headers,
            )

            if response.status_code in (200, 201):
                logger.info("FHIR Observation 전송 성공: %s", observation.get("identifier", [{}])[0].get("value"))
                return True
            else:
                logger.warning(
                    "FHIR 전송 실패: status=%d, body=%s",
                    response.status_code,
                    response.text[:200],
                )
                return False
        except Exception as e:
            logger.error("FHIR 전송 오류: %s", e)
            return False


# 싱글톤
fhir_service = FHIRService()
