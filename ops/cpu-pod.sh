#!/usr/bin/env bash
# The CPU machine every OCR number is measured on: a RunPod CPU pod (Ubuntu 24.04), set up
# from nothing. Run on the pod from the unpacked repository:
#
#   bash ops/cpu-pod.sh setup     # Tesseract, uv, the locked environment
#   bash ops/cpu-pod.sh data      # fetch and verify the corpora, render, check the pages
#   bash ops/cpu-pod.sh ocr PART  # Tesseract over PART (dev or test) of every corpus, level 0
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
    .venv/bin/legible data fetch all
    .venv/bin/legible data build all
    for c in fara deepform cord; do
      # A checkout on Windows may carry CRLF line ends; the records are what is compared.
      if ! diff -q <(tr -d '' < "manifests/$c-pages.jsonl")           <(tr -d '' < "$LEGIBLE_DATA/manifests-committed/$c-pages.jsonl") >/dev/null; then
        echo "$c: rendered pages differ from the committed manifest" >&2
        exit 1
      fi
    done
    echo "pages match the committed manifests"
    ;;
  ocr)
    part="${2:?dev or test}"
    for c in fara deepform cord; do
      .venv/bin/legible ocr run "$c" --part "$part" --level 0 --workers "$(nproc)"
    done
    ;;
  *)
    echo "usage: $0 setup | data | ocr dev|test" >&2
    exit 2
    ;;
esac
