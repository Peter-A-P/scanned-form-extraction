#!/usr/bin/env bash
# Arm B's fine-tunes, one after another on a rented GPU, each resuming from the volume and
# skipped once its adapter is there. Run on the pod from the unpacked repository, after
# `bash ops/cpu-pod.sh data` and `legible train sets`:
#
#   VOLUME_ID=<id> DATACENTER=<dc> bash ops/train-queue.sh SEED SIZE [DATASET...]
#
# With no datasets it takes the headline order: FARA's three held-out templates, DeepForm's
# unseen split, CORD, NIST, then the two mixed splits. Several pods can work one list: each
# run's checkpoints and adapter live under its own run id, and a pod skips what is done.
# S3 credentials come from /root/s3.env (AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY, the
# volume's S3 keys); nothing here prints them.
set -euo pipefail

seed="${1:?seed}"
size="${2:?2b or 4b}"
shift 2
: "${VOLUME_ID:?}" "${DATACENTER:?}"
source /root/s3.env
export LEGIBLE_DATA="${LEGIBLE_DATA:-/root/legible-data}" HF_HOME=/root/hf PYTHONUNBUFFERED=1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
cd "$(dirname "$0")/.."
# The checkpoint store shells out to `aws`, installed in the environment beside legible.
export PATH="$PWD/.venv/bin:$PATH"

if [ $# -eq 0 ]; then
  set -- "fara-unseen-amendment-s$seed" "fara-unseen-dissemination_report-s$seed" \
    "fara-unseen-short-form-s$seed" "deepform-unseen-s$seed" cord nist \
    "fara-mixed-s$seed" "deepform-mixed-s$seed"
fi
dc="$(echo "$DATACENTER" | tr '[:upper:]' '[:lower:]')"
for dataset in "$@"; do
  run=$(.venv/bin/python -c "from legible.train.recipe import chosen; print(chosen('$size', '$dataset', seed=$seed).run_id)")
  if .venv/bin/aws s3 ls "s3://$VOLUME_ID/legible/checkpoints/$run/adapter/.complete" \
      --endpoint-url "https://s3api-$dc.runpod.io" --region "$dc" >/dev/null 2>&1; then
    echo "done already: $run"
    continue
  fi
  echo "training: $run"
  .venv/bin/legible train run "$dataset" --size "$size" --seed "$seed" \
    --checkpoint-uri "s3://$VOLUME_ID/legible/checkpoints" --s3-datacenter "$DATACENTER"
done
echo QUEUEDONE
