"""
Alembic 환경 설정 (async 엔진 지원)

app.config.settings.DATABASE_URL에서 DB URL을 읽어옵니다.
SQLite에서는 render_as_batch=True로 ALTER TABLE 호환성을 보장합니다.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import settings
from app.core.database import Base

# 모든 모델을 import하여 Base.metadata에 등록
from app.models import user, event, camera, push_subscription, audit_log, safe_zone, room  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# alembic.ini의 sqlalchemy.url을 앱 설정에서 동적으로 주입
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")


def run_migrations_offline() -> None:
    """오프라인 모드에서 마이그레이션 실행 (SQL 스크립트 생성)"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=_is_sqlite,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    """마이그레이션 컨텍스트 설정 및 실행"""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=_is_sqlite,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """async 엔진으로 마이그레이션 실행"""
    connectable_config = config.get_section(config.config_ini_section, {})

    # SQLite인 경우 check_same_thread 설정
    connect_args = {}
    if _is_sqlite:
        connect_args["check_same_thread"] = False

    connectable = async_engine_from_config(
        connectable_config,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """온라인 모드에서 마이그레이션 실행 (async)"""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
