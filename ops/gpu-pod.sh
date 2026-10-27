#!/usr/bin/env bash
# A GPU pod (RunPod, runpod/base CUDA 13 image) set up from nothing for arm B: the training
# stack, the gateway, the corpora and the pages. Run on the pod from the unpacked repository,
# with /root/s3.env holding the volume's S3 keys:
#
#   VOLUME_ID=<id> DATACENTER=<dc> bash ops/gpu-pod.sh setup   # uv, the locked environment, aws
#   VOLUME_ID=<id> DATACENTER=<dc> bash ops/gpu-pod.sh data [C...]  # pages and training sets
#                                       # unpacked; corpora C fetched and checked
#
# The pages come from the volume (legible/data/pages.tar, rendered once and checked against the
# committed manifests) rather than rendered again. Training needs nothing else; reading a VRDU
# corpus needs its split files, so the evaluation pod fetches fara (VRDU, with its
# checksums). Then ops/train-queue.sh, ops/ablate-queue.sh or ops/eval-queue.sh.
set -euo pipefail
: "${VOLUME_ID:?}" "${DATACENTER:?}"
export LEGIBLE_DATA="${LEGIBLE_DATA:-/root/legible-data}" UV_LINK_MODE=copy
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PWD/.venv/bin:$PATH"
dc="$(echo "$DATACENTER" | tr '[:upper:]' '[:lower:]')"

case "${1:-}" in
  setup)
    command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
    uv sync --frozen --no-dev --extra train --extra gateway
    uv pip install -q "awscli>=1.40,<2"
    python -c "import torch; print(torch.cuda.get_device_name(0))"
    ;;
  data)
    source /root/s3.env
    s3() { aws s3 "$@" --endpoint-url "https://s3api-$dc.runpod.io" --region "$dc"; }
    mkdir -p "$LEGIBLE_DATA"
    for c in "${@:2}"; do legible data fetch "$c"; done
    cd "$LEGIBLE_DATA"
    for t in pages train; do
      s3 cp --only-show-errors "s3://$VOLUME_ID/legible/data/$t.tar" "/root/$t.tar"
      tar --no-same-owner -xf "/root/$t.tar" && rm "/root/$t.tar"
    done
    ls "$LEGIBLE_DATA"
    ;;
  *)
    echo "usage: $0 setup | data" >&2
    exit 2
    ;;
esac
