#!/usr/bin/env bash
# Keep the calculator listening on PORT (default 4317).
# Preview URLs only work while this process is up.
set -u
cd "$(dirname "$0")/.."
if [[ ! -f out/index.html ]]; then
  npm run build
fi
export PORT="${PORT:-4317}"
while true; do
  node server.mjs
  echo "Sunucu kapandı (çıkış $?). 2 saniye sonra yeniden başlıyor…"
  sleep 2
done
