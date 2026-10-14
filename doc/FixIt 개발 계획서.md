# Fixit Image Studio: 올인원 한글 이미지 복원 및 위지윅 편집 스튜디오 개발 계획

## 1. 개요 및 배경

`fixit_bkg` 프로젝트는 지나치게 복잡한 분산 워커, 세션 암호화, Tesseract/Telea 기반의 낮은 복원 품질로 인해 개발 진척이 지연되었습니다.
본 계획은 **핵심 기능 중심의 경량화·고품질화**를 통해 새로운 `fixit` 프로젝트(`/home/icarus/projects/python/fixit`)를 신속하게 구축하고, **위지윅(WYSIWYG) 편집** 및 **객체 클릭 누끼따기(배경 제거)**를 실현하는 종합 개발 계획입니다.

> [!IMPORTANT]
> **실제 운영 배포 환경: Docker & Docker Compose 컨테이너 배포**  
> 본 시스템의 실제 프로덕션 배포는 호스트 환경 의존성을 완전히 제거하기 위해 **Docker 컨테이너(Docker Compose) 기반으로 패키징 및 배포**됩니다. 백엔드(FastAPI + AI 런타임)와 프론트엔드(Nginx + React SPA) 모두 멀티스테이지 컨테이너 이미지로 빌드되며, 운영 DB(`DB_TRIP_TRANS`) 및 영속 볼륨과 연동됩니다.

---

## 2. 핵심 아키텍처 및 기술 스택

### 2.1 아키텍처 개요
```mermaid
graph TD
    subgraph DockerEnv ["Docker 프로덕션 배포 환경 (docker-compose)"]
        subgraph WebContainer ["Web 컨테이너 (fixit-web: Nginx)"]
            UI["fixit_bkg 테마 UI (크림/베이지 모던)"]
            Canvas["위지윅 캔버스 (Konva: 박스 이동/리사이즈)"]
            Inspector["인스펙터 (크기, 장평, 자간, 행간 슬라이더)"]
            NukkiTool["객체 클릭 누끼따기 모드 (Interactive Cutout)"]
            AutoTool["원클릭 자동 복원 모드 (imgedit 원터치 실행)"]
        end

        subgraph ApiContainer ["API 컨테이너 (fixit-api: FastAPI)"]
            AuthRouter["TripCloser JWT & Luna 호환 인증"]
            OCRRouter["Dual OCR/VLM Router\n(Strata VLM ⇄ Azure GPT-6.1-sol Fallback)"]
            InpaintRouter["LamaInpainter (단색 무손상 + CPU LaMa)"]
            RenderRouter["TextRenderer (NanumSquare + 3x 슈퍼샘플링)"]
            NukkiRouter["Background Removal / Segmentation Engine"]
            AutoPipeline["imgedit End-to-End 자동화 파이프라인"]
        end
    end

    subgraph External ["외부 연동 인프라"]
        Postgres[("운영 DB: DB_TRIP_TRANS\n(192.168.209.100)")]
        VolumeStorage[("Docker Volume: ./storage, ./fonts")]
        StrataHost["로컬 Strata VLM Server\n(qwen3.8-flash-next :8080)"]
        MsdnCost["msdn-cost 추천 API\n(192.168.209.120:8100/8101)"]
        AzureGPT["Azure OpenAI Service\n(gpt-6.1-sol, reasoning_effort='medium')"]
    end

    UI --> Canvas
    Canvas --> Inspector
    WebContainer <==>|리버스 프록시 /api| ApiContainer
    ApiContainer <--> Postgres
    ApiContainer <--> VolumeStorage
    OCRRouter -.->|1차 기본 호출| StrataHost
    OCRRouter -.->|미구동 감지 시 동적 URL/Key 획득| MsdnCost
    OCRRouter ==>|Fallback 질의| AzureGPT
    AutoPipeline --> OCRRouter
    AutoPipeline --> InpaintRouter
    AutoPipeline --> RenderRouter
```

### 2.2 기술 스택
| 영역 | 기술 스택 | 비고 |
| :--- | :--- | :--- |
| **배포 환경** | **Docker, Docker Compose** | **실제 운영 배포 표준 (멀티스테이지 Nginx + Python 런타임)** |
| **Backend** | Python 3.11+, FastAPI, Uvicorn, SQLAlchemy | 경량 단일 서비스 (워커 큐 제거, 컨테이너화) |
| **Frontend** | React 19, TypeScript, Vite, Konva (`react-konva`), Lucide-React | `fixit_bkg` 디자인 시스템 100% 준용 |
| **복원 엔진** | **Strata VLM + Azure GPT-6.1-sol Fallback + LaMa + 고정밀 텍스트 렌더러** | 3종 폰트(나눔스퀘어, NotoSans, 페이퍼로지) & 0% 잔상 인페인팅 |
| **LLM 라우팅** | **msdn-cost Recommendation API (`luna` 패턴)** | 동적 Azure URL/Key 취득 + `reasoning_effort='medium'` 적용 |
| **누끼 엔진** | U2Net / RMBG / Rembg / OpenCV GrabCut 하이브리드 | 클릭 좌표 기반 고속 알파 채널 분리 |
| **DB & 인증** | PostgreSQL (`DB_TRIP_TRANS`), `bcrypt`, JWT Bearer | `luna`와 동일한 `users` 테이블 공유 |

---

## 3. 핵심 모듈별 상세 설계

### 3.1 사용자 인증 & 운영 DB 연동 (`luna` 패턴)
- **운영 DB**: `postgresql://inspection:ts2020!!@192.168.209.100:5432/DB_TRIP_TRANS`
- **공유 테이블**: `users` (`id`, `email`, `password_hash`, `name`, `department` 등)
- **프로젝트 및 버전 관리 테이블**:
  - `fixit_projects`: 프로젝트 메타데이터, 원본/배경 이미지 경로, 최근 완성본 상태(`regions_json`, `current_image_path`), 최신 `version`
  - `fixit_revisions`: 작업 스냅샷 이력 (`project_id`, `version`, `regions_json`, `image_path`, `created_at`) - 사후 롤백 지원
- **인증 메커니즘**:
  - `bcrypt.checkpw` 기반 비밀번호 검증
  - `SECRET_KEY` 및 `TRIP_CLOSER_SECRET_KEY`를 통한 JWT 토큰 서명/검증
  - 프론트엔드 헤더의 `TripCloser 로그인` 모달과 연동

### 3.2 이미지 인식에서 수정까지의 자동화 파이프라인 (`imgedit` 연동)
`imgedit` 프로젝트의 검증된 4단계 복원 파이프라인을 본 프로젝트의 백엔드 API 서비스로 완벽히 흡수·일원화합니다.

```mermaid
sequenceDiagram
    autonumber
    actor User as 사용자 (Web UI)
    participant API as fixit-api (/api/restore)
    participant VLM as Dual OCR Engine
    participant Inpaint as LamaInpainter
    participant Render as TextRenderer
    participant Disk as Storage (/app/storage)

    User->>API: POST /api/restore/auto (이미지 업로드)
    Note over API,VLM: Step 1. VLM 기반 자동 분석 및 오탈자 교정
    API->>VLM: extract_regions(image) [Strata 우선, 실패 시 Azure GPT-6.1-sol]
    VLM-->>API: List[TextRegion] (bbox, observed, corrected, typography)
    
    Note over API,Inpaint: Step 2. 스마트 하이브리드 인페인팅
    API->>Inpaint: inpaint(original_img, regions)
    Inpaint-->>API: background_inpainted.png (단색 무손상 + LaMa)
    API->>Disk: 배경 이미지 임시 저장

    Note over API,Render: Step 3. 타이포그래피 정밀 렌더링
    API->>Render: composite_onto(inpainted_img, orig_bgr, regions)
    Render-->>API: restored.png (3x 슈퍼샘플링 + 3종 폰트 지원)
    API->>Disk: 최종 복원 이미지 저장

    Note over API,Disk: Step 4. Before/After 비교 리포트 생성
    API->>Disk: 각 영역별 크롭 비교(comparison_{id}.png) 및 restoration_report.json 저장
    API-->>User: 전체 복원 결과 반환 (regions, report, image URLs)
```

1. **Step 1: 텍스트 영역 및 오탈자 정밀 검출 (`extract_regions`)**:
   - 이미지 내 텍스트 바운딩 박스(`bbox`), 배경 소거 박스(`clean_bbox`), 폰트 패밀리/웨이트, 폰트 크기, 장평(`scale_x`), 자간(`letter_spacing`), 행간(`gap_after`)을 자동 산출
   - 원본 오탈자(`observed`)를 문맥 기반 정상 한글 텍스트(`corrected`)로 자동 교정
2. **Step 2: 스마트 배경 인페인팅 (`LamaInpainter`)**:
   - 단색 카드/컨테이너 영역: 제로-블리딩 단색 채우기(Exact Background Fill)로 0% 잔상 보장
   - 그라데이션/복합 질감 배경 영역: PyTorch CPU 기반 Fast LaMa Inpainting 적용
3. **Step 3: 타이포그래피 스타일 전이 렌더링 (`TextRenderer`)**:
   - 3종 공인 폰트 패밀리(나눔스퀘어, NotoSans, 페이퍼로지) 정밀 매핑 지원
   - 3배수 슈퍼샘플링(Supersampling) 후 다운샘플링하여 안티앨리어싱 품질 극대화
   - 미세 가우시안 블러(`blur_radius: 0.35`)를 적용하여 원본 그래픽과의 이질감 없는 자연스러운 래스터 합성
4. **Step 4: 영역별 Before/After 비교 및 리포트 생성**:
   - 영역별로 원본 크롭과 복원 크롭을 나란히 배치한 비교 썸네일(`comparison_{id}.png`) 자동 생성
   - 소요 시간(`ocr`, `inpaint`, `typography_render`, `total`)과 상세 메타데이터가 담긴 `restoration_report.json` 출력

### 3.3 Strata 미구동 시 Azure GPT-6.1-sol Medium Thinking Fallback (`luna` + `msdn-cost` 패턴)
로컬 인프라의 Strata VLM (`qwen3.8-flash-next`)이 미구동 상태이거나 응답 지연/오류가 발생할 경우, **Azure OpenAI `gpt-6.1-sol` (Medium Thinking)**으로 무중단 자동 Fallback을 수행합니다.

```mermaid
graph TD
    Start["OCR/분석 요청 시작"] --> CheckStrata{"로컬 Strata VLM 구동 여부\n(http://127.0.0.1:8080/v1/models)"}
    CheckStrata -- "정상 응답 (HTTP 200)" --> UseStrata["Strata VLM 추론 실행\n(qwen3.8-flash-next-iq3_s)"]
    CheckStrata -- "미구동 / 타임아웃 / 오류" --> FetchMsdn["msdn-cost 권장 설정 조회\n(192.168.209.120:8100/8101 /api/costs/recommendation)"]
    
    FetchMsdn -- "권장 응답 수신" --> BindDynamic["동적 URL / Key / gpt-6.1-sol 바인딩"]
    FetchMsdn -- "msdn-cost 타임아웃" --> BindStatic["정적 Azure OpenAI Fallback 바인딩\n(certimind 레퍼런스 키/엔드포인트)"]
    
    BindDynamic --> CallAzureGPT["Azure OpenAI gpt-6.1-sol 호출\n(reasoning_effort='medium', Vision Chat)"]
    BindStatic --> CallAzureGPT
    
    CallAzureGPT --> ParseJSON["오탈자 및 텍스트 영역 JSON 파싱\n(observed, corrected, bbox, typography)"]
    UseStrata --> ReturnResult["TextRegion 리스트 반환"]
    ParseJSON --> ReturnResult
```

- **`msdn-cost` 기반 동적 라우팅 (`luna` 프로젝트 구현 준용)**:
  - `msdn-cost` API (`http://192.168.209.120:8100/api/costs/recommendation` 및 `8101`)에 요청하여 현재 가장 비용 최적화된 Azure OpenAI 리소스의 `url`, `key`, 가용 `models`를 동적으로 획득
  - 가용 모델 중 `gpt-6.1-sol`을 우선 타겟팅하여 바인딩
  - `msdn-cost` 추천 서버 연결 실패 시 `certimind` 및 `luna`에 내장된 Static Azure OpenAI 엔드포인트/키로 안전망 Failover
- **Medium Thinking 추론 파라미터 적용**:
  - `gpt-6.1-sol` 호출 시 `reasoning_effort="medium"` 파라미터를 활성화하여 심층 사고(Thinking Mode) 유도
  - 이미지 내 미세 텍스트 판독, 문맥 분석을 통한 고난도 한글 오탈자 교정, 바운딩 박스 정밀 좌표 계산의 정확도를 극대화
- **Failover 호환성 보장**:
  - `AzureOpenAI` 클라이언트 호출 시 API 버전 및 배포 환경에 따라 `reasoning_effort` 미지원 예외 발생 시, `luna`의 `_call_chat_completion` 예외 처리 로직에 따라 즉시 일반 파라미터로 다운그레이드 재시도

### 3.4 API 엔드포인트 상세 명세 (`fixit-api`)
| 엔드포인트 | 메서드 | 설명 |
| :--- | :--- | :--- |
| `/api/auth/login` | POST | TripCloser / Luna 호환 사용자 로그인 및 JWT 발급 |
| `/api/auth/me` | GET | 현재 로그인된 사용자 정보 조회 |
| `/api/projects` | GET / POST | 내 프로젝트 목록 조회 / 신규 프로젝트 생성 (이미지 및 초벌 분석 결과 등록) |
| `/api/projects/{id}` | GET / PUT | 특정 프로젝트 상태 상세 조회 / 현재 완성본 및 텍스트 설정(`regions_json`) 영속 저장 |
| `/api/projects/{id}/revisions` | GET | 프로젝트 버전(Revision) 변경 이력 조회 |
| `/api/projects/{id}/revisions/restore` | POST | 특정 과거 버전(Revision)으로 작업 상태 되돌리기 |
| `/api/restore/auto` | POST | **`imgedit` 기반 원터치 자동 복원** (이미지 업로드 → OCR/교정 → LaMa 인페인팅 → 렌더링 → 비교 리포트 일괄 반환) |
| `/api/restore/analyze` | POST | 1단계: VLM 자동 분석 (Strata 우선, Azure GPT-6.1-sol Fallback) → 텍스트 영역 목록 반환 |
| `/api/restore/inpaint` | POST | 2단계: 캔버스에서 지정/수정된 `clean_bbox` 기반 배경 인페인팅 단독 실행 |
| `/api/restore/render` | POST | 3단계: 사용자가 위지윅 인스펙터로 조정한 슬라이더 값(장평, 자간, 크기 등) 기반 최종 고해상도 합성 |
| `/api/restore/preview/{task_id}` | GET | 특정 작업의 중간 배경 이미지 및 단계별 복원 이미지 조회 |
| `/api/cutout/click` | POST | 캔버스 내 클릭 좌표 $(x, y)$ 기반 전경 객체 분리 누끼따기 (투명 PNG 반환) |

### 3.5 위지윅(WYSIWYG) 캔버스 상호작용 및 3대 폰트 시스템
1. **역할 분담 원칙**:
   - **프론트엔드 (React + Konva)**: 마우스 박스 드래그/리사이즈, 슬라이더 조절 실시간 미리보기 (0ms 클라이언트 GPU 렌더링)
   - **백엔드 (FastAPI + Pillow)**: 최종 `POST /api/restore/render` 요청 시 TTF 폰트 파일과 3x 슈퍼샘플링을 거친 출판급 원본 렌더링
2. **공식 지원 3대 폰트 패밀리 및 세부 웨이트**:
   | 폰트 패밀리 | 지원 Weight | 실제 TTF 파일 (`/fonts`) | 주 사용 용도 |
   | :--- | :--- | :--- | :--- |
   | **나눔스퀘어 (NanumSquare)** | `Regular`, `Bold`, `ExtraBold` | `NanumSquareR.ttf`<br>`NanumSquareB.ttf`<br>`NanumSquareEB.ttf` | 모던 인포그래픽, 핵심 타이틀, 불릿 리스트 |
   | **본고딕 (NotoSansKR)** | `Regular`, `Bold` | `NotoSansKR-Regular.ttf`<br>`NotoSansKR-Bold.ttf` | 표준 보고서, 본문 설명문, 공식 안내 문구 |
   | **페이퍼로지 (Paperlogy)** | `Regular` (4Regular), `Bold` (7Bold) | `Paperlogy-4Regular.ttf`<br>`Paperlogy-7Bold.ttf` | 감성 카드뉴스, 브랜딩 배너, 카드 헤드라인 |
3. **인스펙터 패널 슬라이더 연동**:
   - 폰트 선택: 상기 3종 패밀리 및 세부 Weight 드롭다운
   - 폰트 크기: 10pt ~ 80pt (실시간 미리보기)
   - 장평(Aspect Ratio): 0.80 ~ 1.20 (수평 압축/확장 배율)
   - 자간(Tracking): -3.0px ~ +3.0px
   - 행간(Line Gap): 0px ~ 40px
   - 텍스트 색상(컬러 피커 / HEX 입력) 및 정렬(좌/중/우, 상/중/하)
4. **영역 재인페인팅 지원**:
   - 사용자가 텍스트 박스 위치를 크게 이동할 경우, 기존 위치의 `clean_bbox`를 다시 지우고 새로운 위치에 렌더링하도록 즉각 재합성
5. **실시간 편집 되돌리기 (Undo / Redo) 및 초안 복원**:
   - **다단계 상태 스택 관리**: 캔버스 내 텍스트 박스 이동, 크기 조절, 문구 수정, 슬라이더 변경 시점마다 최대 30단계의 불변(Immutable) 상태 스택(`undo: Region[][]`, `redo: Region[][]`)을 자동 보존
   - **직관적 단축키 지원**:
     - `Ctrl + Z` / `⌘ + Z`: 이전 편집 상태로 되돌리기 (Undo)
     - `Ctrl + Shift + Z` / `⌘ + Shift + Z` 또는 `Ctrl + Y`: 다시 실행 (Redo)
     - 단, 입력창(input/textarea)에 포커스가 있을 때는 브라우저 네이티브 텍스트 Undo가 우선 동작하도록 격리
   - **상단 툴바 직관적 버튼**: 헤더에 `Undo2` / `Redo2` 버튼을 배치하여 마우스 클릭으로도 손쉽게 조작 (스택 유무에 따라 disabled 상태 시각화)
   - **저장 전 수정 모두 취소 (Discard Draft)**: 실수로 여러 편집이 꼬였을 때 한 번의 클릭으로 초벌 자동 복원(또는 마지막 저장) 시점의 깨끗한 상태로 즉시 회귀
6. **완성본 영속 저장 & 세션 자동 백업 & 사후 재수정 (Post-Edit & Re-render)**:
   - **사후 오류 발견 대비 무손상 재수정 구조**:
     - 수정 완료 후 이미지를 다운로드하거나 페이지를 닫은 뒤, 나중에 인쇄물이나 화면에서 오탈자·정렬 오류를 발견하더라도 **처음부터 다시 작업할 필요가 없습니다.**
     - 언제든 프로젝트 목록(`GET /api/projects`)에서 해당 작업을 다시 열면, 직전에 맞추어 둔 **깨끗한 배경 이미지 레이어와 모든 텍스트 영역의 세부 좌표/스타일(`regions_json`)이 캔버스에 100% 온전히 복원**됩니다.
     - 사용자는 오류가 발견된 글자 1~2개나 좌표만 살짝 조정한 뒤, 즉시 `재렌더링(Re-render)` 및 재다운로드가 가능합니다.
   - **브라우저 세션 로컬 자동 저장 (Auto-save on LocalStorage)**:
     - 편집 중 사용자의 네트워크 단절, 브라우저 탭 실수 닫힘, 새로고침 등에 대비하여, 수정이 발생할 때마다 1초 디바운스로 `localStorage`에 초안 상태를 자동 백업합니다.
     - 다시 접속 시 "편집 중이던 미저장 초안이 있습니다. 복원하시겠습니까?" 팝업을 통해 직전 작업 상태로 안전하게 복귀할 수 있습니다.
   - **서버 버전 히스토리 (Revision Snapshots)**:
     - 사용자가 상단 `저장하기`를 누르거나 최종 출력 시 자동으로 버전 번호(`version: 1, 2, ...`)가 증가하며 스냅샷이 누적됩니다.
     - 언제든 '저장·출력 후 되돌리기' 모달에서 원하는 과거 저장 시점을 선택하여 자유롭게 롤백할 수 있습니다.

### 3.6 부가 기능: 객체 클릭 누끼따기 (Interactive Cutout)
- 상단 툴바의 `✂️ 누끼따기` 모드 활성화
- 캔버스 내 특정 객체 클릭 시 해당 좌표 $(x, y)$를 `/api/cutout/click`으로 전달
- 하이브리드 세그멘테이션 엔진(Rembg/GrabCut)이 투명 배경 PNG 레이어 생성
- 캔버스 상에서 독자적 스티커 레이어로 이동/확대/축소하거나 개별 다운로드 지원

### 3.7 운영 배포: Docker & Docker Compose 아키텍처
- **컨테이너 구성 (`docker-compose.yml`)**:
  - `fixit-api`: FastAPI 백엔드 (Python 3.11-slim, PyTorch CPU, OpenCV `libgl1`, Nanum 폰트 패키지, LaMa/VLM 어댑터 탑재)
  - `fixit-web`: Nginx 기반 프로덕션 리버스 프록시 + React 정적 빌드 서빙 (포트 80/443 -> `/api` 백엔드 프록시)
- **볼륨 마운트 및 영속성 (Persistence)**:
  - 에셋 저장소: `./storage:/app/storage`
  - 폰트 저장소: `./fonts:/app/fonts:ro`
- **환경 변수 관리 (`.env`)**:
  - `DATABASE_URL=postgresql://inspection:ts2020!!@192.168.209.100:5432/DB_TRIP_TRANS`
  - `SECRET_KEY`, `TRIP_CLOSER_SECRET_KEY`
  - `STRATA_VLM_URL=http://host.docker.internal:8080/v1`
  - `MSDN_COST_API_URL=http://192.168.209.120:8100/api/costs/recommendation`
  - `DOC_LLM_MODEL=gpt-6.1-sol`
  - `LLM_REASONING_EFFORT=medium`

---

## 4. 단계별 세부 구현 체크리스트

### Phase 1: 프로젝트 기반 환경 및 리소스 셋업 (완료)
- [x] **1.1 프로젝트 디렉토리 및 에셋 구조화**
  - [x] 최상위 프로젝트 생성 (`/home/icarus/projects/python/fixit`)
  - [x] 디렉토리 분리 구성: `apps/api` (백엔드), `apps/web` (프론트엔드), `fonts` (폰트 저장소), `storage` (에셋 볼륨)
- [x] **1.2 3대 폰트 패밀리(7종 TTF) 실물 파일 배치 및 매니페스트 확인**
  - [x] 나눔스퀘어: `NanumSquareR.ttf`, `NanumSquareB.ttf`, `NanumSquareEB.ttf` 배치
  - [x] 본고딕: `NotoSansKR-Regular.ttf`, `NotoSansKR-Bold.ttf` 배치
  - [x] 페이퍼로지: `Paperlogy-4Regular.ttf`, `Paperlogy-7Bold.ttf` 배치
  - [x] `manifest.json` 에셋 체크섬 검증
- [x] **1.3 도커 환경변수 및 오케스트레이션 골격 구성**
  - [x] `.env` 및 `.env.example` 구성 (`DATABASE_URL`, `MSDN_COST_API_URL`, `DOC_LLM_MODEL`, `LLM_REASONING_EFFORT`)
  - [x] `docker-compose.yml` 포트 바인딩(단일 올인원 포트 8310), 볼륨 및 extra_hosts 설정

---

### Phase 2: 백엔드 API & 복원 엔진 구축 (`imgedit` + `luna` 통합) (완료)
- [x] **2.1 데이터베이스 & 인증 모듈 (`luna` 패턴)**
  - [x] `database.py`: SQLAlchemy 세션 팩토리 및 연결 풀 구성
  - [x] `models.py`:
    - [x] `users`: 기존 `DB_TRIP_TRANS`의 사용자 테이블 연동 (`extend_existing=True`)
    - [x] `fixit_projects`: 프로젝트 메타데이터, 원본/배경 이미지 경로, 최근 완성본 `regions_json`, 최신 `version`
    - [x] `fixit_revisions`: 버전별 스냅샷 이력 테이블 (`project_id`, `version`, `regions_json`, `image_path`)
  - [x] `auth.py`: JWT 토큰 발급/검증 및 TripCloser 인증 호환 미들웨어 (`get_current_user`)
- [x] **2.2 Dynamic Azure LLM Fallback 클라이언트 (`llm_client.py`)**
  - [x] `fetch_recommended_azure_config`: `msdn-cost` API (`192.168.209.120:8100/8101 /api/costs/recommendation`) 동적 쿼리 및 캐싱
  - [x] 타겟 모델 우선순위 바인딩 (`gpt-6.1-sol` > `gpt-6-luna` > Fallback target)
  - [x] `msdn-cost` 미응답 시 정적 Static Azure OpenAI 엔드포인트/키 자동 Failover
  - [x] `AzureOpenAI` 클라이언트 초기화 및 Vision 메시지 페이로드 생성 로직 작성
  - [x] `reasoning_effort="medium"` 파라미터 전달 및 예외 발생 시 일반 파라미터 자동 다운그레이드 처리
- [x] **2.3 `imgedit` 복원 엔진 흡수 및 다종 폰트 렌더러 구축**
  - [x] `schema.py`: `TextRegion`, `LineStyle` 데이터 모델 확장 (폰트 패밀리, 웨이트, 장평, 자간, 행간, 정렬, 마스크 정보)
  - [x] `strata_ocr.py` (Dual Engine VLM):
    - [x] 1차: 로컬 Strata VLM (`http://127.0.0.1:8080/v1/models`) 헬스체크 및 추론 호출
    - [x] 2차: Strata 미구동 시 `llm_client.py` 경유 Azure `gpt-6.1-sol` (Medium Thinking)으로 즉시 Fallback 호출
    - [x] 응답 JSON 파싱을 통해 `List[TextRegion]` 표준 스키마로 정규화
  - [x] `lama_inpaint.py`:
    - [x] 단색 카드/컨테이너 영역 제로-블리딩 채우기 (Exact Solid Background Fill)
    - [x] 복합 질감 배경 영역 PyTorch CPU 기반 LaMa Inpainting 하이브리드 결합
  - [x] `text_renderer.py`:
    - [x] 3대 폰트 패밀리(나눔스퀘어, NotoSans, 페이퍼로지) TTF 매퍼 작성
    - [x] 3배수 슈퍼샘플링 + 다운샘플링 안티앨리어싱
    - [x] 미세 가우시안 블러(`blur_radius: 0.35`) 합성
  - [x] `pipeline.py`: 4단계 End-to-End 자동화 파이프라인 결합
    - [x] Step 1(Dual OCR) → Step 2(스마트 인페인팅) → Step 3(타이포그래피 렌더링) → Step 4(비교 리포트 생성)
- [x] **2.4 REST API 라우터 구현 (`fixit_api/main.py`)**
  - [x] `POST /api/auth/login`, `GET /api/auth/me`: 인증 라우터
  - [x] `POST /api/projects`: 프로젝트 생성 및 이미지 업로드
  - [x] `GET /api/projects`: 내 프로젝트 목록 조회
  - [x] `GET /api/projects/{id}`: 특정 프로젝트 상세 및 완성본 데이터 조회
  - [x] `PUT /api/projects/{id}`: 프로젝트 저장 (신규 버전 커밋 및 `regions_json` 갱신)
  - [x] `GET /api/projects/{id}/revisions`: 리비전 히스토리 조회
  - [x] `POST /api/projects/{id}/revisions/restore`: 특정 버전 롤백 복원
  - [x] `POST /api/restore/auto`: `imgedit` 원터치 4단계 일괄 실행
  - [x] `POST /api/restore/analyze`: 1단계 VLM OCR 분석 단독 호출 (Dual Fallback)
  - [x] `POST /api/restore/inpaint`: 2단계 배경 인페인팅 단독 실행
  - [x] `POST /api/restore/render`: 3단계 파라미터 기반 출판급 최종 고해상도 렌더링
  - [x] `GET /api/restore/preview/{task_id}`: 중간 산출물/비교 썸네일 파일 서빙
  - [x] `POST /api/cutout/click`: 클릭 좌표 $(x, y)$ 기반 전경 객체 누끼따기 (투명 PNG 반환)

---

### Phase 3: 프론트엔드 UI & 위지윅 캔버스 구축 (`apps/web`) (완료)
- [x] **3.1 프로젝트 셋업 및 디자인 시스템 이식**
  - [x] Vite + React 19 + TypeScript 환경 구성
  - [x] `fixit_bkg` 크림/베이지 모던 테마 CSS (`style.css`), 컬러 토큰, 컴포넌트 이식
  - [x] 3대 폰트(나눔스퀘어, NotoSans, 페이퍼로지) `@font-face` 웹폰트 선언 및 프리로드
  - [x] Lucide React 아이콘 및 공통 모달/토스트 시스템 구축
- [x] **3.2 Konva 위지윅 캔버스 (`react-konva`) 코어 구현**
  - [x] 배경 레이어: 인페인팅 완료된 깨끗한 배경 이미지 배치 (줌/팬 뷰포트 지원)
  - [x] 텍스트 레이어: `TextRegion` 기반 바운딩 박스 렌더링
  - [x] 트랜스포머(Transformer): 마우스 드래그로 박스 위치 이동 및 크기 리사이징
  - [x] 마스킹 영역(`clean_bbox`) 시각화 및 수동 편집 지원
- [x] **3.3 인스펙터 패널 & 실시간 타이포그래피 슬라이더 연동**
  - [x] 폰트 패밀리 및 Weight 선택 드롭다운 (3대 폰트 7종 웨이트)
  - [x] 슬라이더: 폰트 크기(10~80pt), 장평(0.80~1.20), 자간(-3~+3px), 행간(0~40px)
  - [x] 텍스트 색상 피커(HEX), 정렬 버튼(좌/중/우, 상/중/하)
  - [x] 슬라이더 조작 시 0ms 클라이언트 GPU 즉각 반응 렌더링
- [x] **3.4 편집 히스토리 및 세션 안전망 (Undo/Redo & Save)**
  - [x] `undo` / `redo` 30단계 불변 스택 관리
  - [x] 단축키 구현 (`Ctrl+Z`, `Ctrl+Shift+Z` / `Ctrl+Y`) - 텍스트 입력창 포커스 시 네이티브 분리
  - [x] 상단 툴바 UI: `Undo`, `Redo`, `수정 모두 취소(초안 초기화)` 버튼
  - [x] `localStorage` 1초 디바운스 실시간 자동 백업 및 세션 복구 다이얼로그
  - [x] 상단 `저장하기` 버튼 연동 (`PUT /api/projects/:id`)
  - [x] `저장·출력 후 되돌리기` 리비전 히스토리 모달 및 시점 롤백
  - [x] **사후 오류 발견 대비 재수정 워크플로우**: 프로젝트 다시 열기 → 특정 글자 수정 → 즉각 `Re-render` 다운로드
- [x] **3.5 원터치 자동 복원 및 객체 누끼따기 인터랙션**
  - [x] 상단 `🪄 원클릭 자동 복원` 버튼: 이미지 업로드 즉시 `/api/restore/auto` 호출 및 결과 캔버스 반영
  - [x] Before / After 비교 뷰어 팝업 (`restoration_report.json` 및 크롭 썸네일 표시)
  - [x] 상단 `✂️ 누끼따기` 모드 토글: 캔버스 내 피사체 클릭 시 `/api/cutout/click` 호출 및 투명 PNG 다운로드/스티커 추가

---

### Phase 4: Docker 패키징, 배포 및 엔드투엔드 통합 검증 (완료)
- [x] **4.1 컨테이너 패키징 및 운영 환경 최적화**
  - [x] `apps/api/Dockerfile`: Python 3.11-slim, PyTorch CPU, OpenCV `libgl1`, 폰트 에셋 마운트
  - [x] `apps/web/Dockerfile`: Vite 멀티스테이지 정적 빌드 + Nginx 리버스 프록시
  - [x] `docker-compose.yml`: `fixit-api`와 `fixit-web` 컨테이너 상호 통신 및 볼륨 영속성 점검
- [x] **4.2 엔드투엔드 시나리오 통합 테스트**
  - [x] **시나리오 1 (기본 경로)**: 로그인 → 인포그래픽 업로드 → 로컬 Strata VLM 정상 분석 → LaMa 인페인팅 → 나눔스퀘어 렌더링 → Before/After 검증
  - [x] **시나리오 2 (VLM Fallback)**: 로컬 Strata 미구동 시뮬레이션 → `msdn-cost` 추천 API 연동 → Azure `gpt-6.1-sol` (Medium Thinking) Fallback 정상 전환 및 오탈자 정밀 파싱 검증
  - [x] **시나리오 3 (위지윅 & 3대 폰트)**: 캔버스에서 텍스트 박스 이동, 페이퍼로지/본고딕 폰트 변경, 장평/자간 슬라이더 조절, Undo/Redo 반복 동작 검증
  - [x] **시나리오 4 (사후 재수정 & 세션 복원)**: 저장 완료 후 브라우저 새로고침 → 세션 복구 확인 → 뒤늦게 발견된 오타 1개 수정 후 백엔드 최종 Re-render 다운로드 검증
  - [x] **시나리오 5 (객체 누끼따기)**: 캔버스 내 피사체 클릭 → 배경 제거 투명 PNG 분리 및 스티커 레이어 검증


