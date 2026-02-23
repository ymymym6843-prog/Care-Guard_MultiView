"""
PDF 리포트 생성 서비스

낙상 이벤트 통계를 PDF 형식으로 출력합니다.
reportlab 미설치 시 graceful degradation으로 JSON 리포트를 반환합니다.
"""
# pyright: reportPossiblyUnboundVariable=false

import io
from datetime import datetime, timedelta, timezone

from app.core.logging_config import get_logger

logger = get_logger("app.services.report")

# reportlab 가용 여부
_REPORTLAB_AVAILABLE = False
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors
    _REPORTLAB_AVAILABLE = True
except ImportError:
    logger.info("reportlab 미설치 - PDF 리포트 비활성화")


class ReportService:
    """낙상 이벤트 리포트 생성"""

    @property
    def pdf_available(self) -> bool:
        return _REPORTLAB_AVAILABLE

    def generate_pdf(
        self,
        summary: dict,
        daily_stats: list[dict],
        title: str = "SENTIO 낙상 이벤트 리포트",
    ) -> bytes:
        """PDF 리포트 생성

        Args:
            summary: 통계 요약 데이터
            daily_stats: 일별 통계 데이터
            title: 리포트 제목

        Returns:
            bytes: PDF 바이너리 데이터
        """
        if not _REPORTLAB_AVAILABLE:
            raise RuntimeError("reportlab이 설치되지 않았습니다")

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20 * mm, bottomMargin=20 * mm)
        styles = getSampleStyleSheet()
        elements = []

        # 제목
        elements.append(Paragraph(title, styles["Title"]))
        elements.append(Spacer(1, 10 * mm))

        # 생성 일시
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        elements.append(Paragraph(f"Generated: {now}", styles["Normal"]))
        elements.append(Spacer(1, 5 * mm))

        # 요약 테이블
        summary_data = [
            ["항목", "값"],
            ["조회 기간", f"{summary.get('period_days', 30)}일"],
            ["총 이벤트", str(summary.get("total_events", 0))],
            ["위험(danger)", str(summary.get("danger_events", 0))],
            ["주의(warning)", str(summary.get("warning_events", 0))],
            ["확인 완료", str(summary.get("acknowledged", 0))],
            ["확인율", f"{summary.get('acknowledgment_rate', 0)}%"],
            ["평균 응답 시간", f"{summary.get('avg_response_seconds', 0)}초"],
        ]

        t = Table(summary_data, colWidths=[120, 100])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.beige, colors.white]),
        ]))
        elements.append(t)
        elements.append(Spacer(1, 10 * mm))

        # 일별 통계 테이블
        if daily_stats:
            elements.append(Paragraph("일별 이벤트 현황", styles["Heading2"]))
            elements.append(Spacer(1, 3 * mm))

            daily_data = [["날짜", "Warning", "Danger", "합계"]]
            for day in daily_stats[-14:]:  # 최근 14일
                daily_data.append([
                    day.get("date", ""),
                    str(day.get("warning", 0)),
                    str(day.get("danger", 0)),
                    str(day.get("total", 0)),
                ])

            t2 = Table(daily_data, colWidths=[100, 70, 70, 70])
            t2.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ]))
            elements.append(t2)

        doc.build(elements)
        return buffer.getvalue()

    def generate_json_report(self, summary: dict, daily_stats: list[dict]) -> dict:
        """JSON 형식 리포트 (PDF 미지원 시 폴백)"""
        return {
            "title": "SENTIO 낙상 이벤트 리포트",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
            "daily_stats": daily_stats,
        }


# 싱글톤
report_service = ReportService()
