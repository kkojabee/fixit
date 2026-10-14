#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

PORT="${PORT:-8310}"
LOG_DIR="$DIR/storage/logs"
LOG_FILE="$LOG_DIR/fixit_local.log"
PID_FILE="$LOG_DIR/fixit_local.pid"

mkdir -p "$LOG_DIR" storage fonts

echo "=================================================="
echo "🚀 FixIt Studio 로컬 단독 서버 시작"
echo "=================================================="

# 1. 기존 프로세스 종료
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "🛑 기존 실행 중인 FixIt 프로세스(PID: $OLD_PID)를 종료합니다..."
        kill "$OLD_PID" 2>/dev/null || true
        sleep 1
    fi
    rm -f "$PID_FILE"
fi

# 8310 포트가 여전히 점유 중인 경우 강제 정리
EXISTING_PID=$(lsof -t -i :"$PORT" 2>/dev/null || true)
if [ -n "$EXISTING_PID" ]; then
    echo "⚠️  포트 $PORT 점유 프로세스(PID: $EXISTING_PID) 정리 중..."
    kill -9 $EXISTING_PID 2>/dev/null || true
    sleep 1
fi

# 2. 프론트엔드 최신 빌드 검증
if [ ! -f "apps/web/dist/index.html" ]; then
    echo "📦 프론트엔드 빌드 중..."
    (cd apps/web && npm run build)
fi

# 3. 환경 변수 적용
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi
export PYTHONPATH="$DIR/apps/api"
export PORT="$PORT"
export API_PORT="$PORT"

# 4. 백그라운드로 uvicorn 실행
echo "🚀 Uvicorn 서버 백그라운드 구동 (포트: $PORT)..."
nohup python3 -m uvicorn fixit_api.main:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    > "$LOG_FILE" 2>&1 &

NEW_PID=$!
echo "$NEW_PID" > "$PID_FILE"
echo "✅ FixIt 백그라운드 실행 완료 (PID: $NEW_PID)"

# 5. 구동 상태 대기 및 확인 (최대 10초)
echo "⏳ 서버 초기화 대기 중..."
READY=false
for i in {1..10}; do
    if curl -s -m 1 "http://127.0.0.1:$PORT/api/health" | grep -q "healthy"; then
        READY=true
        break
    fi
    sleep 1
done

if [ "$READY" = true ]; then
    echo "=================================================="
    echo "🎉 FixIt Studio 로컬 구동 성공!"
    echo "🌐 서비스 접속 URL: http://localhost:$PORT"
    echo "📄 실시간 로그 파일: $LOG_FILE"
    echo "=================================================="
    
    # Strata VLM 연결 상태 점검
    STATUS=$(curl -s "http://127.0.0.1:$PORT/api/strata/status" 2>/dev/null || true)
    echo "🔍 Strata VLM 상태: $STATUS"
else
    echo "❌ 서버 시작 확인 실패! 최근 로그:"
    tail -n 20 "$LOG_FILE"
    exit 1
fi
