#!/usr/bin/env bash
# Arms B and C read their test pages through vLLM on the GPU pod, through the gateway.
#
#   bash ops/serve-eval.sh RUN_ID     # arm B: a fine-tune, merged and served, reads its splits
#   bash ops/serve-eval.sh 2b-it      # arm C: an untuned instruction model reads every corpus
#
# A fine-tune's adapter is fetched from the volume if this pod did not train it. vLLM lives in
# its own environment (/root/vllm-env), because it brings its own torch. Reads go through the
# served gateway configuration (legible serve config), 8 calls in flight, and each pass's wall
# time is kept beside its run for the cost per page.
set -euo pipefail
model="${1:?run id or 2b-it / 4b-it}"
: "${VOLUME_ID:?}" "${DATACENTER:?}"
source /root/s3.env
export LEGIBLE_DATA="${LEGIBLE_DATA:-/root/legible-data}" HF_HOME=/root/hf PYTHONUNBUFFERED=1
cd "$(dirname "$0")/.."
export PATH="$PWD/.venv/bin:$PATH"
dc="$(echo "$DATACENTER" | tr '[:upper:]' '[:lower:]')"
s3() { aws s3 "$@" --endpoint-url "https://s3api-$dc.runpod.io" --region "$dc"; }

if [ ! -x /root/vllm-env/bin/vllm ]; then
  uv venv -q /root/vllm-env --python 3.12
  VIRTUAL_ENV=/root/vllm-env uv pip install -q "vllm==0.30.0"
fi

if [[ "$model" == *-it ]]; then
  arm=c
  size="${model%-it}"
  args=$(legible serve argv "$model")
  reads=$( { for c in fara deepform cord; do echo "$c - dev 0"; echo "$c - test 0"; done;
             for c in fara deepform; do echo "$c - vrdu_curve 2"; echo "$c - vrdu_curve 4"; done;
             legible serve reads nist; } )
else
  arm=b
  dir="$LEGIBLE_DATA/models/$model"
  if [ ! -f "$dir/adapter/adapter_model.safetensors" ]; then
    mkdir -p "$dir"
    s3 cp --recursive "s3://$VOLUME_ID/legible/checkpoints/$model/adapter" "$dir/adapter" >/dev/null
    cp "$dir/adapter/run.json" "$dir/run.json"
  fi
  [ -d "$LEGIBLE_DATA/merged/$model" ] || legible serve merge "$model"
  dataset=$(python -c "import json; print(json.load(open('$dir/run.json'))['config']['dataset'])")
  budget=$(python -c "import json; print(json.load(open('$dir/run.json'))['config']['visual_tokens'])")
  args=$(legible serve argv "$model" --visual-tokens "$budget")
  reads=$(legible serve reads "$dataset")
fi

mapfile -t argv <<< "$args"
# vLLM's kernels compile on first use with the ninja its environment installs, found on PATH.
PATH="/root/vllm-env/bin:$PATH" "/root/vllm-env/bin/${argv[0]}" "${argv[@]:1}"   > "/root/vllm-$model.log" 2>&1 &
server=$!
trap 'kill $server 2>/dev/null || true' EXIT
for _ in $(seq 1 180); do
  curl -sf http://127.0.0.1:8000/v1/models >/dev/null && break
  kill -0 $server 2>/dev/null || { tail -20 "/root/vllm-$model.log"; exit 1; }
  sleep 5
done
legible serve config "$model" --out boundary-served.yaml

# Two passes: a call that fails is left unread by the first, and the second, a resume, tries
# only those.
for pass in 1 2; do
  while read -r corpus split part level; do
    extra=()
    [ "$split" != "-" ] && extra=(--split "$split")
    legible read submit "$corpus" --arm "$arm" --route "$model" --part "$part" --level "$level" \
      --gateway-config boundary-served.yaml --concurrency 8 "${extra[@]}"
  done <<< "$reads"
done
echo "EVALDONE $model"
