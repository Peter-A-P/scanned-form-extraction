#!/usr/bin/env bash
# Arm B's confidence reads: each headline (seed-0) fine-tune reads its level-0 dev and test
# documents again with every answer token's log-probability (ops/serve-eval.sh, LOGPROBS=1),
# and the reads go to the volume after each model.
#
#   VOLUME_ID=<id> DATACENTER=<dc> bash ops/logprob-queue.sh RUN_ID...
#
# With no run ids it takes every seed-0 model a result table uses (`legible serve headline`).
# What is done is listed in /root/logprobs-done.txt, so the loop can be stopped and started.
set -uo pipefail
: "${VOLUME_ID:?}" "${DATACENTER:?}"
source /root/s3.env
cd "$(dirname "$0")/.."
export PATH="$PWD/.venv/bin:$PATH" LEGIBLE_DATA="${LEGIBLE_DATA:-/root/legible-data}"
dc="$(echo "$DATACENTER" | tr '[:upper:]' '[:lower:]')"
done_list=/root/logprobs-done.txt
touch "$done_list"
[ $# -eq 0 ] && set -- $(legible serve headline)

for run in "$@"; do
  grep -qx "$run" "$done_list" && continue
  echo "confidence reads: $run"
  ok=0
  LOGPROBS=1 bash ops/serve-eval.sh "$run" > "/root/logprobs-$run.log" 2>&1 || ok=$?
  [ -d "$LEGIBLE_DATA/runs/arm-b/$run@logprobs" ] && aws s3 sync --only-show-errors \
    "$LEGIBLE_DATA/runs/arm-b/$run@logprobs" "s3://$VOLUME_ID/legible/runs/arm-b/$run@logprobs" \
    --endpoint-url "https://s3api-$dc.runpod.io" --region "$dc"
  if [ "$ok" -eq 0 ]; then
    echo "$run" >> "$done_list"
    rm -rf "$LEGIBLE_DATA/merged/$run"
    echo "done: $run"
  else
    echo "FAILED: $run (see /root/logprobs-$run.log)"
  fi
done
echo LOGPROBSDONE
