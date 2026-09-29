#!/usr/bin/env bash
# data/ altındaki değişiklikleri commit edip gönderir. Çakışmada rebase ile tekrar dener.
set -euo pipefail
mesaj="${1:-veri}"
git config user.name "github-actions[bot]"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add data
if git diff --cached --quiet; then
  echo "Kaydedilecek değişiklik yok."
  exit 0
fi
git commit -q -m "$mesaj $(date -u +%Y-%m-%dT%H:%MZ)"
for deneme in 1 2 3 4 5; do
  if git push -q; then
    echo "Gönderildi."
    exit 0
  fi
  echo "Push reddedildi, rebase ($deneme)"
  git pull -q --rebase
  sleep $((deneme * 5))
done
echo "Push başarısız." >&2
exit 1
