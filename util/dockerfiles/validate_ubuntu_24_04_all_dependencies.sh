#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(git -C "$script_dir" rev-parse --show-toplevel)"
image_name="gem5-local:ubuntu24-alldeps"
dockerfile="$repo_root/util/dockerfiles/ubuntu-24.04_all-dependencies/Dockerfile"
build_context="$repo_root/util/dockerfiles/ubuntu-24.04_all-dependencies"
tmp_suite_file="/tmp/gem5_suites.txt"

command -v docker >/dev/null 2>&1 || {
    echo "error: docker CLI is required but was not found in PATH" >&2
    exit 1
}

rm -f "$tmp_suite_file"

docker build --pull -f "$dockerfile" -t "$image_name" "$build_context"

docker run --rm \
    -u "$(id -u):$(id -g)" \
    "$image_name" \
    pre-commit --version
docker run --rm "$image_name" mypy --version
docker run --rm "$image_name" python3 --version
docker run --rm "$image_name" scons --version

docker run --rm \
    -u "$(id -u):$(id -g)" \
    -v "$repo_root:/workspace" \
    -w /workspace \
    "$image_name" \
    scons build/NULL/gem5.opt -j2

docker run --rm \
    -u "$(id -u):$(id -g)" \
    -v "$repo_root:/workspace" \
    -v /tmp:/tmp \
    -w /workspace/tests \
    "$image_name" \
    sh -lc './main.py -h'

docker run --rm \
    -u "$(id -u):$(id -g)" \
    -v "$repo_root:/workspace" \
    -v /tmp:/tmp \
    -w /workspace/tests \
    "$image_name" \
    sh -lc './main.py list -q --suites gem5 > /tmp/gem5_suites.txt'

test -s "$tmp_suite_file"
