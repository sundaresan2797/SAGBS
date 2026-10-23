#!/bin/sh
# Switch the backend between the DEMO data (test people) and the LIVE data (your real company).
#   ./scripts/use_env.sh live      use the real, empty-then-filled database
#   ./scripts/use_env.sh demo      go back to the demo database
# After switching, RESTART the backend. The two use different databases, different upload folders,
# different Redis databases and different login secrets, so they never mix.
set -e
cd "$(dirname "$0")/.."
case "$1" in
  live) cp .env.live .env ;;
  demo) cp .env.demo .env ;;
  *) echo "Use:  ./scripts/use_env.sh live   or   ./scripts/use_env.sh demo"; exit 1 ;;
esac
chmod 600 .env
echo "Now using the $1 settings. Restart the backend for it to take effect."
grep -E '^(DATABASE_URL|UPLOAD_DIR|REDIS_URL)=' .env | sed -E 's#(://[^:]+:)[^@]*@#\1***@#'
