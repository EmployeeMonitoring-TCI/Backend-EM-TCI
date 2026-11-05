#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

if command -v docker >/dev/null 2>&1; then
  docker compose up --build -d
elif [[ -n "${BACKEND_SERVICE:-}" ]]; then
  if ! command -v systemctl >/dev/null 2>&1; then
    echo "systemctl tidak tersedia; tidak dapat me-restart service ${BACKEND_SERVICE}." >&2
    exit 1
  fi
  systemctl restart "$BACKEND_SERVICE"
else
  echo "Docker tidak tersedia dan BACKEND_SERVICE belum diatur." >&2
  echo "Cari nama service backend dengan:" >&2
  echo "  systemctl list-units --type=service --all | grep -Ei 'uvicorn|backend|fastapi'" >&2
  echo "Lalu deploy dengan:" >&2
  echo "  BACKEND_SERVICE=nama-service.service bash deploy.sh" >&2
  exit 1
fi

for attempt in {1..30}; do
  if openapi="$(curl --fail --silent --show-error http://127.0.0.1:12046/openapi.json 2>/dev/null)"; then
    if grep -Fq '"/api/attendance/check-in"' <<<"$openapi"; then
      legacy_status="$(curl --silent --output /dev/null --write-out '%{http_code}' \
        http://127.0.0.1:12046/attendance/history)"
      if [[ "$legacy_status" != "404" && "$legacy_status" != "000" ]]; then
        echo "Backend aktif; route /api/attendance/check-in dan /attendance/history tersedia."
        exit 0
      fi
    fi
  fi

  sleep 2
done

echo "Backend belum siap atau route absensi tidak tersedia pada http://127.0.0.1:12046." >&2
if [[ -n "${BACKEND_SERVICE:-}" ]]; then
  echo "Periksa log service dengan: journalctl -u ${BACKEND_SERVICE} -n 100 --no-pager" >&2
elif command -v docker >/dev/null 2>&1; then
  echo "Periksa log container dengan: docker compose logs --tail=100 backend" >&2
fi
exit 1
