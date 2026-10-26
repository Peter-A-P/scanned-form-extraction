#!/usr/bin/env bash
# The ablations (legible/train/ablate.py), one after another on a rented GPU, as
# ops/train-queue.sh runs the headline: each resumes from the volume and is skipped once its
# adapter is there, so several pods can share the list. Run on the pod from the unpacked
# repository, after the pages and `legible train sets`:
#
#   VOLUME_ID=<id> DATACENTER=<dc> bash ops/ablate-queue.sh [KIND...]
#
# KIND is visual-tokens, volume or multi-corpus; with none, every ablation in the list's order.
# S3 credentials come from /root/s3.env, as for the headline; nothing here prints them.
set -euo pipefail

: "${VOLUME_ID:?}" "${DATACENTER:?}"
source /root/s3.env
export LEGIBLE_DATA="${LEGIBLE_DATA:-/root/legible-data}" HF_HOME=/root/hf PYTHONUNBUFFERED=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
cd "$(dirname "$0")/.."
export PATH="$PWD/.venv/bin:$PATH"
dc="$(echo "$DATACENTER" | tr '[:upper:]' '[:lower:]')"

.venv/bin/legible train ablations | while read -r run kind dataset tokens volume; do
  if [ $# -gt 0 ] && [[ " $* " != *" $kind "* ]]; then continue; fi
  if .venv/bin/aws s3 ls "s3://$VOLUME_ID/legible/checkpoints/$run/adapter/.complete" \
      --endpoint-url "https://s3api-$dc.runpod.io" --region "$dc" >/dev/null 2>&1; then
    echo "done already: $run"
    continue
  fi
  extra=()
  [ "$volume" != "-" ] && extra=(--volume "$volume")
  echo "training: $run ($kind)"
  .venv/bin/legible train run "$dataset" --size 2b --seed 0 --visual-tokens "$tokens" \
    "${extra[@]}" --checkpoint-uri "s3://$VOLUME_ID/legible/checkpoints" \
    --s3-datacenter "$DATACENTER" < /dev/null
done
echo QUEUEDONE
