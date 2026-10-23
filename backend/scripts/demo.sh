#!/bin/bash
# Manage the DEMO copy of the system: its own database ("ems_demo"), backend on :8001, frontend on :5174.
# Your real database and the real app (:8000 / :5173) are never touched.
#
#   scripts/demo.sh reset   rebuild the demo: copy the people from the real database, then fill in 12 months of history
#   scripts/demo.sh start   start the demo backend and frontend  ->  open http://localhost:5174
#   scripts/demo.sh stop    stop them
set -e
BACKEND="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND="$BACKEND/../frontend"
cd "$BACKEND"
DBURL=$(grep -i "^DATABASE_URL=" .env | cut -d= -f2- | sed 's#/employee_management$#/ems_demo#')
SYNCURL=$(grep -i "^DATABASE_URL_SYNC=" .env | cut -d= -f2- | sed 's#/employee_management$#/ems_demo#')

case "$1" in
  reset)
    "$0" stop >/dev/null 2>&1 || true
    pg_dump -d employee_management -Fc -f /tmp/ems_demo_src.dump   # read-only copy of the real database
    dropdb --if-exists ems_demo >/dev/null 2>&1; createdb ems_demo
    pg_restore --no-owner --no-privileges -d ems_demo /tmp/ems_demo_src.dump >/dev/null 2>&1 || true
    psql -d ems_demo -q -c "GRANT ALL ON ALL TABLES IN SCHEMA public TO ems_app; GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO ems_app; GRANT ALL ON SCHEMA public TO ems_app;"
    psql -d ems_demo -tAc "SELECT 'ALTER TABLE public.'||quote_ident(tablename)||' OWNER TO ems_app;' FROM pg_tables WHERE schemaname='public';" | psql -d ems_demo -q
    psql -d ems_demo -tAc "SELECT 'ALTER TYPE public.'||quote_ident(t.typname)||' OWNER TO ems_app;' FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname='public' AND t.typtype='e';" | psql -d ems_demo -q
    rm -f /tmp/ems_demo_src.dump
    DATABASE_URL_SYNC="$SYNCURL" venv/bin/alembic upgrade head 2>&1 | grep -E "Running|Error" || true
    DATABASE_URL_SYNC="$SYNCURL" venv/bin/python -m app.seed_demo_history --upload-dir "$BACKEND/uploads_demo"
    redis-cli -n 9 flushdb >/dev/null
    ;;
  start)
    "$0" stop >/dev/null 2>&1 || true
    DATABASE_URL="$DBURL" REDIS_URL="redis://localhost:6379/9" UPLOAD_DIR="$BACKEND/uploads_demo" CORS_ORIGINS="http://localhost:5174" \
      nohup venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8001 > /tmp/ems_demo_server.log 2>&1 < /dev/null &
    (cd "$FRONTEND" && VITE_API_BASE_URL="http://127.0.0.1:8001/api/v1" nohup npx vite --port 5174 --strictPort > /tmp/ems_demo_vite.log 2>&1 < /dev/null &)
    sleep 5
    echo "Demo is running: open http://localhost:5174  (same logins as the real app; starter password ChangeMe123!)"
    ;;
  stop)
    lsof -ti:8001 | xargs kill 2>/dev/null || true
    lsof -ti:5174 | xargs kill 2>/dev/null || true
    echo "Demo stopped."
    ;;
  *)
    echo "Usage: scripts/demo.sh reset|start|stop"; exit 1 ;;
esac
