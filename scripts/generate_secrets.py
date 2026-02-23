#!/usr/bin/env python3
"""
SENTIO 시크릿 키 생성 스크립트

JWT_SECRET_KEY와 INTERNAL_STREAM_KEY를 안전하게 생성합니다.
생성된 값을 .env.docker 또는 .env 파일에 설정하세요.
"""

import secrets


def main():
    jwt_key = secrets.token_urlsafe(48)
    stream_key = secrets.token_urlsafe(32)

    print("=== SENTIO Secret Keys ===")
    print()
    print(f"JWT_SECRET_KEY={jwt_key}")
    print(f"INTERNAL_STREAM_KEY={stream_key}")
    print()
    print("위 값을 .env.docker 또는 .env 파일에 복사하세요.")
    print("프로덕션 환경에서는 반드시 이 스크립트로 새 키를 생성하세요.")


if __name__ == "__main__":
    main()
