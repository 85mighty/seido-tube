#!/usr/bin/env bash
# config/secrets.enc (암호화 번들: cookies.txt + .env 추가분) → VPS에 풀어서 적용 후 번들 삭제
# usage: SECRETS_PASS=<passphrase> bash vps/apply_secrets.sh
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f config/secrets.enc ] || { echo "config/secrets.enc 없음"; exit 1; }
[ -n "${SECRETS_PASS:-}" ] || { echo "SECRETS_PASS 필요"; exit 1; }
tmp=$(mktemp -d)
openssl enc -d -aes-256-cbc -pbkdf2 -pass "pass:$SECRETS_PASS" -in config/secrets.enc | tar -C "$tmp" -xzf -
[ -f "$tmp/cookies.txt" ] && install -m 600 "$tmp/cookies.txt" config/cookies.txt && echo "config/cookies.txt ($(wc -l < config/cookies.txt) lines)"
[ -f .env ] || cp .env.example .env
if [ -f "$tmp/env.add" ]; then
  while IFS='=' read -r k v; do
    [ -z "$k" ] && continue
    grep -q "^$k=" .env && sed -i "s|^$k=.*|$k=$v|" .env || echo "$k=$v" >> .env
    echo ".env: $k 설정"
  done < "$tmp/env.add"
fi
rm -rf "$tmp"
git rm -q --cached config/secrets.enc 2>/dev/null || true
rm -f config/secrets.enc
git -c user.name=vps -c user.email=vps@seido-note.com commit -qm "remove secrets bundle" 2>/dev/null && git push -q origin main 2>/dev/null && echo "secrets.enc 저장소에서 제거됨" || true
echo "done"
