#!/usr/bin/env bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-8310}"
PID_FILE="$DIR/storage/logs/fixit_local.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "🛑 FixIt 프로세스(PID: $PID) 종료 중..."
        kill "$PID" 2>/dev/null || true
        sleep 1
    fi
    rm -f "$PID_FILE"
fi

EXISTING_PID=$(lsof -t -i :"$PORT" 2>/dev/null || true)
if [ -n "$EXISTING_PID" ]; then
    echo "🛑 포트 $PORT 점유 프로세스(PID: $EXISTING_PID) 강제 종료 중..."
    kill -9 $EXISTING_PID 2>/dev/null || true
fi

echo "✅ FixIt 로컬 서버가 종료되었습니다."
