#!/usr/bin/env bash
# The CPU machine every OCR number is measured on: a RunPod CPU pod (Ubuntu 24.04), set up
# from nothing. Run on the pod from the unpacked repository:
#
#   bash ops/cpu-pod.sh setup     # Tesseract, uv, the locked environment
#   bash ops/cpu-pod.sh data [C]  # fetch and verify a corpus (default all), render, check pages
#   bash ops/cpu-pod.sh ocr PART [C...]  # Tesseract over PART (dev or test), level 0
#   bash ops/cpu-pod.sh curve     # Tesseract over the NIST curve pages at levels 1 to 4
#
# The render on the pod must give the pages the committed manifests describe, byte for byte,
# or the OCR is of different pixels than the vision arms are sent: `data` stops if any page's
# sha256 differs.
set -euo pipefail

export LEGIBLE_DATA="${LEGIBLE_DATA:-/root/legible-data}"
export UV_LINK_MODE=copy
# os.cpu_count() sees the host's cores, not the pod's share; Python 3.13 reads this instead.
export PYTHON_CPU_COUNT="$(nproc)"
cd "$(dirname "$0")/.."

case "${1:-}" in
  setup)
    apt-get update -q
    DEBIAN_FRONTEND=noninteractive apt-get install -y -q tesseract-ocr tesseract-ocr-eng rsync
    export PATH="$HOME/.local/bin:$PATH"
    command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
    uv sync --frozen --no-dev
    tesseract --version | head -1
    nproc
    ;;
  data)
    mkdir -p "$LEGIBLE_DATA"
    cp -r manifests "$LEGIBLE_DATA/manifests-committed"
    which="${2:-all}"
    .venv/bin/legible data fetch "$which"
    .venv/bin/legible data build "$which"
    for c in $([ "$which" = all ] && echo fara deepform cord nist || echo "$which"); do
      # A checkout on Windows may carry CRLF line ends; the records are what is compared.
      if ! diff -q <(tr -d '
' < "manifests/$c-pages.jsonl")           <(tr -d '
' < "$LEGIBLE_DATA/manifests-committed/$c-pages.jsonl") >/dev/null; then
        echo "$c: rendered pages differ from the committed manifest" >&2
        exit 1
      fi
    done
    echo "pages match the committed manifests"
    ;;
  ocr)
    part="${2:?dev or test}"
    shift 2
    for c in ${@:-fara deepform cord nist}; do
      .venv/bin/legible ocr run "$c" --part "$part" --level 0 --workers "$(nproc)"
    done
    ;;
  curve)
    for level in 1 2 3 4; do
      .venv/bin/legible ocr run nist --part curve --level "$level" --workers "$(nproc)"
    done
    ;;
  *)
    echo "usage: $0 setup | data [corpus] | ocr dev|test [corpus...] | curve" >&2
    exit 2
    ;;
esac
