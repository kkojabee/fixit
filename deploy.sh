#!/usr/bin/env bash
set -e

REMOTE_USER="icarus"
REMOTE_HOST="192.168.209.120"
REMOTE_DIR="~/dockers/fixit"
CONTAINER_PORT="8310"

echo "=================================================="
echo "🚀 FixIt 배포 시작: ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}"
echo "=================================================="

# 1. 원격지 대상 디렉토리 생성
echo "📁 [1/4] 원격지 배포 디렉토리 확인 및 생성..."
ssh -o StrictHostKeyChecking=no "${REMOTE_USER}@${REMOTE_HOST}" "mkdir -p ${REMOTE_DIR}"

# 2. rsync를 이용한 프로젝트 소스코드 동기화
echo "📦 [2/4] 소스코드 동기화 (rsync)..."
rsync -avz --progress \
  --exclude='.git' \
  --exclude='node_modules' \
  --exclude='apps/web/node_modules' \
  --exclude='apps/web/dist' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.pytest_cache' \
  --exclude='.venv' \
  --exclude='storage/*.png' \
  --exclude='storage/*.jpg' \
  --exclude='storage/uploads/*' \
  --exclude='storage/results/*' \
  ./ "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DIR}/"

# 3. 원격지 Docker Compose 빌드 및 컨테이너 재실행
echo "🐳 [3/4] 원격지 Docker 빌드 및 서비스 재시작..."
ssh -t "${REMOTE_USER}@${REMOTE_HOST}" "cd ${REMOTE_DIR} && \
  mkdir -p storage fonts && \
  if command -v docker &> /dev/null; then \
    if docker compose version &> /dev/null; then \
      docker compose down || true; \
      docker compose up -d --build; \
    else \
      docker-compose down || true; \
      docker-compose up -d --build; \
    fi; \
  else \
    echo '❌ docker 명령어를 찾을 수 없습니다.'; \
    exit 1; \
  fi"

# 4. 배포 완료 확인
echo "🔍 [4/4] 컨테이너 상태 점검..."
ssh "${REMOTE_USER}@${REMOTE_HOST}" "cd ${REMOTE_DIR} && (docker compose ps 2>/dev/null || docker-compose ps 2>/dev/null)"

echo "=================================================="
echo "✅ 배포 완료!"
echo "🌐 접속 주소: http://${REMOTE_HOST}:${CONTAINER_PORT}"
echo "=================================================="
