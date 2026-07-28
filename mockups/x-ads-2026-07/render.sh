#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/../.." && pwd)"
output_dir="${repo_root}/site/assets/landing/x-ads-2026-07"
source_url="file://${script_dir}/index.html"

mkdir -p "${output_dir}"

ids=(
  mx-x-01a mx-x-01b
  mx-x-02a mx-x-02b
  mx-x-03a mx-x-03b
  mx-x-04a mx-x-04b
  mx-x-05a mx-x-05b
  mx-x-06a mx-x-06b
  mx-x-07a mx-x-07b
  mx-x-08a mx-x-08b
  mx-x-09a mx-x-09b
  mx-x-10a mx-x-10b
)

for id in "${ids[@]}"; do
  playwright screenshot \
    --viewport-size="1200,628" \
    --wait-for-selector='html[data-ready="true"]' \
    --timeout=30000 \
    "${source_url}?ad=${id}" \
    "${output_dir}/${id}.png"
done

echo "Rendered ${#ids[@]} ads to ${output_dir}"
