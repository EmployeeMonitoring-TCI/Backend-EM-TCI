#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

docker compose up --build -d

for attempt in {1..30}; do
  if openapi="$(curl --fail --silent --show-error http://127.0.0.1:12046/openapi.json 2>/dev/null)"; then
    if grep -Fq '"/api/attendance/check-in"' <<<"$openapi"; then
      echo "Backend aktif dan route /api/attendance/check-in terdaftar."
      exit 0
    fi
  fi

  sleep 2
done

echo "Backend tidak mendaftarkan /api/attendance/check-in pada http://127.0.0.1:12046/openapi.json." >&2
echo "Periksa log container dengan: docker compose logs --tail=100 backend" >&2
exit 1
