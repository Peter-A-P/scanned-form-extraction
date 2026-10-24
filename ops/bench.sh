#!/usr/bin/env bash
# The load test on the GPU pod: each fine-tune named is merged, served by vLLM and read by the
# closed-loop client at 1, 8 and 32 in flight on its own test documents (legible bench run).
#
#   GPU="RTX 3090" RATE=0.50 CHECKED=2026-10-23 bash ops/bench.sh RUN_ID [RUN_ID ...]
#
# RATE is the pod's costPerHr as RunPod's API returned it at creation, CHECKED that day. Each
# model's record is synced to the volume as soon as it finishes, so a lost pod keeps what it
# measured, and a model whose record is already complete there is skipped.
set -euo pipefail
: "${VOLUME_ID:?}" "${DATACENTER:?}" "${GPU:?}" "${RATE:?}" "${CHECKED:?}"
source /root/s3.env
# Newer botocore asks for response checksums, and RunPod's S3 refused a 6 GB GetObject
# with "Invalid object path" until it was told to ask only when required (2026-10-23).
export AWS_RESPONSE_CHECKSUM_VALIDATION=when_required AWS_REQUEST_CHECKSUM_CALCULATION=when_required
export LEGIBLE_DATA="${LEGIBLE_DATA:-/root/legible-data}" HF_HOME=/root/hf PYTHONUNBUFFERED=1
cd "$(dirname "$0")/.."
export PATH="$PWD/.venv/bin:$PATH"
dc="$(echo "$DATACENTER" | tr '[:upper:]' '[:lower:]')"
s3() { aws s3 "$@" --endpoint-url "https://s3api-$dc.runpod.io" --region "$dc"; }

if [ ! -x /root/vllm-env/bin/vllm ]; then
  uv venv -q /root/vllm-env --python 3.12
  VIRTUAL_ENV=/root/vllm-env uv pip install -q "vllm==0.30.0"
fi

for model in "$@"; do
  out="$LEGIBLE_DATA/bench/$model"
  if s3 cp "s3://$VOLUME_ID/legible/bench/$model/bench.json" - 2>/dev/null \
      | python -c "import json,sys; sys.exit(0 if json.load(sys.stdin).get('finished_at') else 1)"; then
    echo "SKIP $model: measured"
    continue
  fi
  dir="$LEGIBLE_DATA/models/$model"
  if [ ! -f "$dir/adapter/adapter_model.safetensors" ]; then
    mkdir -p "$dir"
    s3 cp --recursive "s3://$VOLUME_ID/legible/checkpoints/$model/adapter" "$dir/adapter" >/dev/null
    cp "$dir/adapter/run.json" "$dir/run.json"
  fi
  [ -d "$LEGIBLE_DATA/merged/$model" ] || legible serve merge "$model"
  budget=$(python -c "import json; print(json.load(open('$dir/run.json'))['config']['visual_tokens'])")
  mapfile -t argv < <(legible serve argv "$model" --visual-tokens "$budget")
  PATH="/root/vllm-env/bin:$PATH" "/root/vllm-env/bin/${argv[0]}" "${argv[@]:1}" \
    > "/root/vllm-$model.log" 2>&1 &
  server=$!
  for _ in $(seq 1 180); do
    curl -sf http://127.0.0.1:8000/v1/models >/dev/null && break
    kill -0 $server 2>/dev/null || { tail -20 "/root/vllm-$model.log"; exit 1; }
    sleep 5
  done
  legible serve config "$model" --out boundary-served.yaml
  legible bench run "$model" --gpu "$GPU" --usd-per-hour "$RATE" --checked "$CHECKED"
  s3 cp --recursive "$out" "s3://$VOLUME_ID/legible/bench/$model" >/dev/null
  kill $server; wait $server 2>/dev/null || true
  # The merged weights are rebuilt from the adapter if wanted again; the disk is not.
  rm -rf "$LEGIBLE_DATA/merged/$model"
  echo "BENCHED $model"
done
echo "BENCHDONE"
