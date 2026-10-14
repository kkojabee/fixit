# Fixit Image Studio (픽싯 이미지 스튜디오)

> **한글 인포그래픽/배너 고품질 복원 & 실시간 위지윅 편집 & 객체 클릭 누끼따기 스튜디오**

본 프로젝트는 `fixit_bkg`의 과도한 분산 워커/세션 복잡성을 걷어내고, `imgedit`에서 검증된 **LaMa 무손상 인페인팅 + Strata VLM 맞춤법 교정 + 나눔스퀘어 3배수 슈퍼샘플링 렌더러**를 단일 서비스로 최적화한 모던 이미지 복원 스튜디오입니다.

---

## 🌟 주요 특징

1. **위지윅(WYSIWYG) 캔버스**: 바운딩 박스 드래그/리사이즈, 실시간 장평(0.85~1.10), 자간(-2~+2px), 행간, 폰트(나눔스퀘어/노토산스) 즉시 조정
2. **트립클로저(`trip-closer`) & 루나(`luna`) 연동**: 동일한 운영 DB(`DB_TRIP_TRANS`), `users` 테이블 및 bcrypt/JWT 인증 공유
3. **무손상 지우개 & 칼같은 한글 렌더링**: 단색 배경 0% 잔상 인페인팅 및 서브픽셀 알파 대비 보정
4. **객체 클릭 누끼따기 (Interactive Cutout)**: 이미지 내 피사체 클릭 시 고속 배경 분리 투명 PNG 추출
5. **Docker 기반 운영 배포**: `docker-compose.yml` 단일 명령으로 프론트엔드/백엔드 원클릭 배포

---

## 🚀 빠른 시작 (Docker Compose)

```bash
# 1. 환경 변수 복사 및 확인
cp .env.example .env

# 2. 도커 컨테이너 빌드 및 실행
docker compose up -d --build

# 3. 접속 (단일 포트 8310 올인원 서빙)
# Web UI: http://localhost:8310
# API Docs: http://localhost:8310/docs
```

## 🛠️ 로컬 개발 환경 실행

### 백엔드 (FastAPI)
```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn fixit_api.main:app --host 127.0.0.1 --port 8170 --reload
```

### 프론트엔드 (React 19 + Vite)
```bash
cd apps/web
npm install
npm run dev
```
