# SENTIO Brand Guidelines

> 요양병원 AI 낙상 감지 시스템의 브랜드 아이덴티티 가이드

---

## 1. Brand Overview

### Brand Name
- **정식 표기**: `SENTIO`
- **소문자 표기 금지**: ~~sentio~~, ~~Sentio~~ (단독 텍스트 표기 시)
- **대문자 필수**: 항상 전체 대문자로 표기

### Tagline
```
Sense · Protect · Care
```
- 항상 **대문자**, letter-spacing `0.35em`으로 표기
- 폰트: 시스템 sans-serif, `font-bold`, `text-[10px]`

### Brand Personality
| 키워드 | 설명 |
|--------|------|
| **감지(Sense)** | AI가 사람의 움직임을 실시간으로 감지하는 핵심 역할 |
| **보호(Protect)** | 낙상 위험으로부터 환자를 안전하게 지키는 의지 |
| **돌봄(Care)** | 고령자와 의료진을 위한 인간 중심 설계 |
| **신뢰(Trust)** | 의료 현장에서 24시간 작동하는 시스템의 안정감 |

---

## 2. Logo

### 2.1 Primary Logo (Pulse Icon + Wordmark)

```
  ┌──────────┐
  │  Pulse   │  SENTIO
  │   Icon   │  SENSE · PROTECT · CARE
  └──────────┘
```

**수평(horizontal)** 배치가 기본이며, **수직(vertical)** 배치도 지원합니다.

### 2.2 Pulse Icon (Symbol Mark)

동심원 파동(Pulse Wave)이 중앙에서 바깥으로 퍼지는 형태. AI가 사람을 감지하고 신호를 보내는 과정을 시각화합니다.

```
SVG viewBox: 0 0 100 100

[Outer Ring]
cx=50 cy=50 r=40  stroke: gradient(indigo→cyan), opacity 0.3, fill: none

[Middle Ring]
cx=50 cy=50 r=27  stroke: gradient(indigo→cyan), opacity 0.6, fill: none

[Inner Ring]
cx=50 cy=50 r=14  stroke: gradient(indigo→cyan), opacity 0.9, fill: none

[Center Dot]
cx=50 cy=50 r=6   fill: white, opacity 1.0
```

**디자인 의미**:
- **동심원 파동**: 센서가 공간을 스캔하고 위험을 감지하는 레이더 패턴
- **중앙 점**: 감지의 원점, AI의 집중 지점
- **퍼져나가는 원**: 감지 신호가 실시간으로 전달되는 과정

### 2.3 Favicon

동심원 2개 + 중앙 점의 단순화 버전.

```svg
<circle cx="50" cy="50" r="38" stroke="url(#grad)" stroke-width="4" fill="none" opacity="0.4"/>
<circle cx="50" cy="50" r="22" stroke="url(#grad)" stroke-width="4" fill="none" opacity="0.7"/>
<circle cx="50" cy="50" r="8" fill="white" opacity="0.95"/>
```

파일: `frontend/public/favicon.svg`

### 2.4 Logo Component API

프로덕션에서 사용하는 React 컴포넌트:

```tsx
import { Logo } from "@/components/ui/Logo";

// 기본 (수직, medium)
<Logo />

// 수평 배치, 작은 사이즈
<Logo orientation="horizontal" size="sm" />

// 아이콘만 (텍스트 없음)
<Logo showText={false} size="lg" />
```

| Prop | Type | Default | Description |
|------|------|---------|-------------|
| `size` | `"sm" \| "md" \| "lg"` | `"md"` | 아이콘 크기 |
| `showText` | `boolean` | `true` | 워드마크 표시 여부 |
| `orientation` | `"vertical" \| "horizontal"` | `"vertical"` | 배치 방향 |
| `className` | `string` | - | 추가 CSS 클래스 |

**Size Map**:

| Size | Icon | Text | Tracking |
|------|------|------|----------|
| `sm` | 40x40px | `text-xl` | `0.15em` |
| `md` | 64x64px | `text-2xl` | `tight` |
| `lg` | 96x96px | `text-3xl` | `tight` |

### 2.5 Logo Clear Space & Misuse

**Clear Space**: 아이콘 높이의 50% 이상 여백 확보

**금지 사항**:
- 그라데이션 색상 변경
- 동심원 비율 왜곡
- 투명도/그림자 임의 적용
- 복잡한 배경 위 직접 배치 (배경 블러 필요)

---

## 3. Color System

oklch 색상 포맷 사용 (Tailwind CSS v4).

### 3.1 Primary Gradient (Logo Color)

| 용도 | Hex | oklch | CSS Variable |
|------|-----|-------|-------------|
| Gradient Start | `#6366f1` | - | - |
| Gradient End | `#06b6d4` | - | - |
| Primary (Light) | - | `oklch(0.60 0.20 250)` | `--primary` |
| Primary (Dark) | - | `oklch(0.707 0.165 255)` | `--primary` |

CSS 그라데이션:
```css
background: linear-gradient(135deg, #6366f1, #06b6d4);
/* Tailwind: bg-gradient-to-r from-indigo-500 to-cyan-400 */
```

### 3.2 Status Colors (Healthcare Semantic)

의료/재활 환경에서 즉각적으로 인지 가능한 상태 색상 체계.

#### Light Theme

| Status | Token | oklch | 용도 |
|--------|-------|-------|------|
| Safe | `--safe` | `oklch(0.656 0.190 164)` | 안전 상태, 정상 모니터링 |
| Warning | `--warning` | `oklch(0.750 0.180 80)` | 주의, 이상 자세 감지 |
| Danger | `--danger` | `oklch(0.577 0.237 25)` | 낙상 감지, 긴급 알림 |

#### Dark Theme

| Status | Token | oklch | 비고 |
|--------|-------|-------|------|
| Safe | `--safe` | `oklch(0.776 0.190 164)` | 밝기 +0.12 |
| Warning | `--warning` | `oklch(0.85 0.18 80)` | 밝기 +0.10 |
| Danger | `--danger` | `oklch(0.637 0.237 25)` | 밝기 +0.06 |

### 3.3 UI Foundation Colors

#### Light Theme

| Token | oklch | 용도 |
|-------|-------|------|
| `--background` | `oklch(0.985 0.002 248)` | 페이지 배경 |
| `--foreground` | `oklch(0.141 0.031 263)` | 기본 텍스트 |
| `--card` | `oklch(1.0 0 0)` | 카드 배경 |
| `--muted` | `oklch(0.930 0.010 255)` | 비활성 배경 |
| `--muted-foreground` | `oklch(0.460 0.030 264)` | 보조 텍스트 |
| `--border` | `oklch(0.880 0.010 255)` | 테두리 |

#### Dark Theme

| Token | oklch | 용도 |
|-------|-------|------|
| `--background` | `oklch(0.141 0.031 263)` | 페이지 배경 |
| `--foreground` | `oklch(0.985 0.002 248)` | 기본 텍스트 |
| `--card` | `oklch(0.216 0.032 264)` | 카드 배경 |
| `--muted` | `oklch(0.318 0.030 264)` | 비활성 배경 |
| `--muted-foreground` | `oklch(0.704 0.026 257)` | 보조 텍스트 |
| `--border` | `oklch(0.318 0.030 264)` | 테두리 |

### 3.4 Chart Colors

데이터 시각화에 사용되는 5색 팔레트.

| Token | Light oklch | Dark oklch | 용도 예시 |
|-------|-------------|------------|-----------|
| `--chart-1` | `oklch(0.607 0.165 255)` | `oklch(0.707 0.165 255)` | Primary 계열 |
| `--chart-2` | `oklch(0.656 0.190 164)` | `oklch(0.776 0.190 164)` | Safe 계열 |
| `--chart-3` | `oklch(0.700 0.165 76)` | `oklch(0.85 0.18 80)` | Warning 계열 |
| `--chart-4` | `oklch(0.577 0.237 25)` | `oklch(0.637 0.237 25)` | Danger 계열 |
| `--chart-5` | `oklch(0.590 0.200 310)` | `oklch(0.650 0.200 310)` | Purple 계열 |

---

## 4. Typography

### 4.1 Font Stack

```css
/* Sans-serif (본문, UI) */
--font-sans: "Pretendard Variable", Pretendard, "Noto Sans KR",
  ui-sans-serif, system-ui, sans-serif;

/* Monospace (코드, 수치) */
--font-mono: "JetBrains Mono", ui-monospace, SFMono-Regular, monospace;
```

| 폰트 | 용도 | 로딩 방식 |
|------|------|-----------|
| Pretendard Variable | 주 UI 폰트 (한/영) | CDN |
| Noto Sans KR | 한글 폴백 | Google Fonts |
| JetBrains Mono | 수치, 코드, 타임스탬프 | 시스템 폴백 |

### 4.2 Type Scale

| 용도 | Class | Weight | 사용처 |
|------|-------|--------|--------|
| 긴급 알림 제목 | `text-4xl` (36px) | `font-black` (900) | DangerAlertDialog |
| 페이지 제목 | `text-3xl` (30px) | `font-black` (900) | 페이지 헤더 |
| 로고 텍스트 (lg) | `text-3xl` (30px) | `font-black` (900) | Logo 컴포넌트 |
| 섹션 제목 | `text-2xl` (24px) | `font-bold` (700) | 카드 헤더 |
| 카드 제목 | `text-lg` (18px) | `font-semibold` (600) | CardTitle |
| 본문 | `text-base` (16px) | `font-normal` (400) | 일반 텍스트 |
| 보조 텍스트 | `text-sm` (14px) | `font-normal` (400) | 설명, 메타데이터 |
| 태그라인 | `text-[10px]` | `font-bold` (700) | Logo subtitle |
| 캡션 | `text-xs` (12px) | `font-normal` (400) | 타임스탬프, 라벨 |

### 4.3 Font Feature Settings

```css
body {
  font-feature-settings: "rlig" 1, "calt" 1;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}
```

---

## 5. Spacing & Layout

### 5.1 Border Radius

```css
--radius: 0.625rem;  /* 10px */

--radius-sm: calc(var(--radius) - 4px);   /* 6px  */
--radius-md: calc(var(--radius) - 2px);   /* 8px  */
--radius-lg: var(--radius);               /* 10px */
--radius-xl: calc(var(--radius) + 4px);   /* 14px */
```

### 5.2 Glass Morphism

프로젝트 전반에서 사용하는 유리질감 패널 스타일.

```css
.glass-panel {
  background: hsl(var(--background) / 0.8);
  backdrop-filter: blur(24px);
  border: 1px solid hsl(var(--border) / 0.5);
  box-shadow: 0 20px 25px -5px rgb(0 0 0 / 0.1);
}

.glass-card {
  background: hsl(var(--card) / 0.6);
  backdrop-filter: blur(12px);
  border: 1px solid hsl(var(--border) / 0.5);
  transition: all 300ms;
}
```

---

## 6. Motion & Animation

### 6.1 Page Transitions

```css
/* 페이지 진입 (아래에서 위로) */
@keyframes enter-up {
  from { opacity: 0; transform: translateY(10px); }
  to   { opacity: 1; transform: translateY(0); }
}
/* duration: 500ms, easing: cubic-bezier(0.16, 1, 0.3, 1) */

/* 스케일 진입 */
@keyframes enter-scale {
  from { opacity: 0; transform: scale(0.95); }
  to   { opacity: 1; transform: scale(1); }
}
/* duration: 300ms */
```

### 6.2 Alert Animations (Healthcare Critical)

| Animation | Class | Duration | 용도 |
|-----------|-------|----------|------|
| Danger Pulse | `.animate-danger-pulse` | 0.5s infinite | 낙상 감지 시 배경 깜빡임 |
| Border Flash | `.animate-border-flash` | 1.0s infinite | 영상 피드 테두리 경고 |
| Alert Shake | `.animate-alert-shake` | 0.6s once | 알림 다이얼로그 등장 시 진동 |

### 6.3 Reduced Motion

```css
@media (prefers-reduced-motion: reduce) {
  .animate-danger-pulse,
  .animate-border-flash,
  .animate-alert-shake,
  .animate-pulse,
  .animate-spin {
    animation: none !important;
  }
  * {
    transition-duration: 0.01ms !important;
    animation-duration: 0.01ms !important;
  }
}
```

---

## 7. Accessibility

### 7.1 Design Principles

| 원칙 | 구현 |
|------|------|
| 색상 + 텍스트 병용 | 상태를 색상만으로 전달하지 않음 (아이콘 + 라벨 병용) |
| 고대비 | WCAG AA 이상 대비비 준수 |
| 큰 터치 타겟 | 최소 44x44px 터치 영역 |
| 포커스 표시 | `2px solid var(--ring)` outline, `2px` offset |
| 스크린 리더 | `aria-live`, `aria-label`, `role` 속성 활용 |
| Windows 고대비 | `forced-colors: active` 미디어 쿼리 대응 |

### 7.2 Color Contrast Requirements

- **일반 텍스트**: 최소 4.5:1 대비비 (WCAG AA)
- **대형 텍스트** (18px+ bold / 24px+): 최소 3:1 대비비
- **UI 컴포넌트**: 최소 3:1 대비비
- **상태 색상**: 색상에만 의존하지 않고 아이콘/텍스트 라벨 병용

---

## 8. Theme Support

### 8.1 Dual Theme

| Mode | 기본값 | 용도 |
|------|--------|------|
| **Dark** | `<html class="dark">` | 24시간 모니터링 (눈 피로 감소) |
| **Light** | `<html>` | 밝은 환경, 문서 작업 |

다크 테마가 **기본값**입니다. 요양병원의 24시간 모니터링 환경에서 눈의 피로를 줄이기 위함입니다.

### 8.2 Theme Toggle

사용자가 헤더의 테마 토글 버튼으로 전환 가능.

---

## 9. Iconography

### 9.1 Icon Library

- **Lucide React** (`lucide-react`) 사용
- 선 두께: 기본값 (strokeWidth 2)
- 크기: `h-4 w-4` (16px) ~ `h-6 w-6` (24px)

### 9.2 Status Icons

| Status | Icon | Color Token |
|--------|------|-------------|
| Safe | `ShieldCheck` | `text-safe` |
| Warning | `AlertTriangle` | `text-warning` |
| Danger | `AlertCircle` | `text-danger` |
| Fall Detected | `PersonStanding` (커스텀) | `text-danger` |
| Monitoring | `Eye` | `text-primary` |
| Camera | `Camera` | `text-muted-foreground` |

---

## 10. File Structure

```
frontend/
  public/
    favicon.svg          # Favicon (단순화된 동심원 파동)
    icon-192x192.png     # PWA 아이콘 192x192
    icon-512x512.png     # PWA 아이콘 512x512
  src/
    components/ui/
      Logo.tsx           # 프로덕션 로고 컴포넌트
    styles/
      globals.css        # 테마 토큰, 애니메이션, 접근성
    pages/
      LogoShowcase.tsx   # 로고 컨셉 비교 페이지
```

---

## 11. Brand Application Examples

### 11.1 Login / Register Page
- 로고: `<Logo size="lg" />` (수직, 중앙 배치)
- 배경: `bg-background` (다크/라이트 자동)
- 카드: 테두리 `border-primary/20`, 배경 `bg-primary/5`

### 11.2 Header (Navigation)
- 로고: `<Logo orientation="horizontal" size="sm" showText />`
- 좌측 고정, 사이드바 너비와 정렬

### 11.3 Alert Dialog (Emergency)
- 배경: `bg-danger` 풀스크린 오버레이
- 아이콘: 동심원 파동 또는 경고 아이콘 대형 (80px+)
- 애니메이션: `animate-danger-pulse` + `animate-alert-shake`
- 텍스트: `text-4xl font-black`

### 11.4 PWA Splash / App Icon
- 배경: `#0f172a` (slate-900)
- 아이콘: 동심원 파동 SVG (favicon 기반)
- 앱 이름: "SENTIO Sense · Protect · Care"

---

*Last updated: 2026-02-13*
*Source: Logo.tsx, globals.css, favicon.svg*
