/**
 * SENTIO 프론트엔드 상수 정의
 * 
 * 애플리케이션 전체에서 사용되는 매직 넘버와 상수를 중앙 관리합니다.
 */

// === 네트워크 타임아웃 (밀리초) ===
export const AUTH_CHECK_TIMEOUT_MS = 5000;
export const SETUP_CHECK_TIMEOUT_MS = 5000;
export const DEFAULT_REQUEST_TIMEOUT_MS = 5000;

// === 재시도 설정 ===
export const MAX_SETUP_CHECK_RETRIES = 5;  // 10회에서 5회로 감소
export const RETRY_DELAY_BASE_MS = 1000;   // Exponential backoff 기본 지연
export const RETRY_DELAY_MAX_MS = 10000;    // 최대 재시도 지연

// === 카메라 갱신 간격 ===
export const CAMERA_REFRESH_INTERVAL_MS = 30000;  // 30초 (일반)
export const CAMERA_STATUS_POLL_MS = 5000;  // 5초 (대시보드 활성 상태 폴링)

// === 데모 키보드 단축키 ===
export const DEMO_KEYS = {
    WARNING: "F1",
    WARNING_PERSIST: "F2",
    DANGER: "F3",
    RECOVERY: "F4",
} as const;

// === 로컬 스토리지 키 ===
export const STORAGE_KEYS = {
    THEME: "sentio-theme",
    LANGUAGE: "sentio-language",
} as const;
