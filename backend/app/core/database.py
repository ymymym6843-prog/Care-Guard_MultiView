"""
데이터베이스 설정 및 세션 관리

SQLite와 PostgreSQL을 조건부로 지원합니다.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings
from app.core.logging_config import get_logger

logger = get_logger("app.core.database")

# SQLite vs PostgreSQL 조건부 엔진 설정
_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

if _is_sqlite:
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        connect_args={"check_same_thread": False},
    )
else:
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    """데이터베이스 테이블 생성 (개발용)

    개발 환경에서는 이 함수가 서버 시작 시 자동으로 테이블을 생성합니다.
    운영 환경에서는 `alembic upgrade head`로 마이그레이션을 적용하세요.
    """
    from app.models import event, camera, user, push_subscription, audit_log, safe_zone, false_report, room  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("데이터베이스 초기화 완료 (%s)", "SQLite" if _is_sqlite else "PostgreSQL")


async def get_db():
    """FastAPI 의존성 주입용 DB 세션"""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
