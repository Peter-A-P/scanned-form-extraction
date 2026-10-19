#!/usr/bin/env bash
# The evaluation pod's loop: every adapter that lands on the volume is merged, served and read
# (ops/serve-eval.sh), once; then the untuned instruction models (arm C) when nothing is waiting.
#
#   VOLUME_ID=<id> DATACENTER=<dc> bash ops/eval-queue.sh
#
# What has been read is listed in /root/evaluated.txt, so the loop can be stopped and started;
# on a fresh pod, seed it with what has already been read. Each model's reads are copied to the
# volume under legible/runs/ after its pass.
# A merged model is deleted after its reads, since 48 of them do not fit on the disk.
set -uo pipefail
: "${VOLUME_ID:?}" "${DATACENTER:?}"
source /root/s3.env
cd "$(dirname "$0")/.."
export PATH="$PWD/.venv/bin:$PATH" LEGIBLE_DATA="${LEGIBLE_DATA:-/root/legible-data}"
dc="$(echo "$DATACENTER" | tr '[:upper:]' '[:lower:]')"
done_list=/root/evaluated.txt
touch "$done_list"

while true; do
  ready=$(aws s3 ls --recursive "s3://$VOLUME_ID/legible/checkpoints/" \
      --endpoint-url "https://s3api-$dc.runpod.io" --region "$dc" 2>/dev/null \
    | awk '{print $4}' | grep '/adapter/.complete$' | cut -d/ -f3 | sort -u     | awk '{ s = ($0 ~ /-s0-/) ? 0 : 1; print s, $0 }' | sort | cut -d' ' -f2)
  # Seed 0 first, every corpus and size: the headline and the gate are seed 0's.
  next=""
  for run in $ready; do
    grep -qx "$run" "$done_list" || { next="$run"; break; }
  done
  if [ -z "$next" ]; then
    for base in 2b-it 4b-it; do
      grep -qx "$base" "$done_list" || { next="$base"; break; }
    done
  fi
  if [ -z "$next" ]; then sleep 300; continue; fi
  echo "evaluating: $next"
  ok=0
  bash ops/serve-eval.sh "$next" > "/root/eval-$next.log" 2>&1 || ok=$?
  # The reads go to the volume as soon as they exist, finished or not: a pod that is
  # terminated (a spent balance does it) takes its disk with it.
  arm=b; [[ "$next" == *-it ]] && arm=c
  [ -d "$LEGIBLE_DATA/runs/arm-$arm/$next" ] && aws s3 sync --only-show-errors \
    "$LEGIBLE_DATA/runs/arm-$arm/$next" "s3://$VOLUME_ID/legible/runs/arm-$arm/$next" \
    --endpoint-url "https://s3api-$dc.runpod.io" --region "$dc"
  if [ "$ok" -eq 0 ]; then
    echo "$next" >> "$done_list"
    rm -rf "$LEGIBLE_DATA/merged/$next"
    echo "evaluated: $next"
  else
    echo "FAILED: $next (see /root/eval-$next.log)"
    sleep 600
  fi
done
