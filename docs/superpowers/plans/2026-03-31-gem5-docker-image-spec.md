# Canonical gem5 Docker Image Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a first-class Dockerized gem5 development/build/test workflow by standardizing and hardening the existing `ubuntu-24.04_all-dependencies` image as the canonical project container.

**Architecture:** Reuse the current `util/dockerfiles` pipeline instead of adding a redundant root-level Dockerfile or a second general-purpose base image. Keep `ubuntu-24.04_all-dependencies` as the canonical image for mounted-checkout development, make only minimal package changes that unblock core workflows, and add validation plus documentation so downstream users can reliably build and test gem5 in-container.

**Tech Stack:** Docker, Docker Buildx Bake, GHCR, GitHub Actions, gem5 `SConstruct`, `tests/main.py`, `util/dockerfiles/*`, Markdown docs.

---

## Current State

- The repo already ships general-purpose and specialized images in `util/dockerfiles/`.
- `util/dockerfiles/ubuntu-24.04_all-dependencies/Dockerfile` already contains the core gem5 build/test toolchain plus common developer tools.
- `.github/workflows/ci-tests.yaml`, `.github/workflows/daily-tests.yaml`, `.github/workflows/weekly-tests.yaml`, and `.github/workflows/compiler-tests.yaml` already use `ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest` for the common Linux path.
- `util/dockerfiles/devcontainer/Dockerfile` is developer-oriented, but it bakes in a released `gem5` binary and is therefore not the right source-of-truth image for mounted checkouts.
- `util/dockerfiles/README.md` currently contains incorrect GHCR pull examples using `ghcr.io/gem5/gem5/...` instead of `ghcr.io/gem5/...`.
- `util/dockerfiles/README.md` also contains at least one stale buildx example: it refers to `docker buildx bake gcc-compiler`, while `util/dockerfiles/docker-bake.hcl` defines the group as `gcc-compilers`.
- Repo-local runbooks already document important container runtime rules:
  - run with `-u $(id -u):$(id -g)` to avoid root-owned build artifacts,
  - mount the repo into `/workspace`,
  - mount host `/tmp` for some `tests/main.py` runs,
  - keep `scons -j` conservative on Apple Silicon Docker Desktop.

## Problem Statement

Today the repo has container building blocks, but not one clearly documented, project-facing container contract for local gem5 development. The implementation gap is not "invent a new Docker system"; it is "formalize one canonical image and make its behavior explicit, validated, and discoverable."

## Scope

### In Scope

- Make `ubuntu-24.04_all-dependencies` the canonical project image for common gem5 development, build, and test workflows.
- Patch that image only if a core workflow is missing a package or runtime configuration.
- Fix Docker documentation and usage examples.
- Add repeatable smoke validation for the canonical image.
- Document the relationship between the canonical image and specialized images.

### Out of Scope

- Replacing specialized images such as `gcn-gpu`, `sst-env`, or `systemc-env`.
- Bundling gem5 resources, disk images, or full-system workloads into the image.
- Making GPU, SST, SystemC, or docs-generation support mandatory in the canonical image.
- Replacing native macOS setup paths.
- Requiring editor-specific devcontainer integration in this phase.

## Approaches Considered

### Option A: Promote `ubuntu-24.04_all-dependencies` as the canonical image

- Pros:
  - already exists and is already used in CI,
  - avoids duplicating package maintenance,
  - avoids stale prebuilt-binary drift,
  - keeps current buildx/GHCR pipeline intact.
- Cons:
  - requires some documentation cleanup,
  - may need a small package/runtime polish pass.

### Option B: Add a new `gem5-dev` overlay image

- Pros:
  - clear project-facing name,
  - can add developer-only tools without touching the CI base.
- Cons:
  - duplicates maintenance with the existing all-dependencies image,
  - creates ambiguity between two general-purpose images,
  - risks becoming a thin alias with little value.

### Option C: Reuse `devcontainer` as the main project image

- Pros:
  - already positioned for developers,
  - already layers on the existing base image.
- Cons:
  - bakes in a released `gem5` binary unrelated to the checked-out source tree,
  - name is tooling-specific,
  - currently references a missing `./devcontainer/devcontainer.json`.

**Recommendation:** implement Option A. Treat `ubuntu-24.04_all-dependencies` as the canonical project container, and improve packaging, docs, and validation around it.

## Canonical Image Contract

The canonical image must support these workflows against a bind-mounted checkout:

- build `build/ALL/gem5.opt`,
- build at least one smaller target quickly for smoke validation, preferably `build/NULL/gem5.opt`,
- run `tests/main.py -h`,
- list suites via `tests/main.py list`,
- run repository Python tooling already expected by developers:
  - `pre-commit`,
  - `mypy`.

The canonical image must **not** assume:

- a prebuilt gem5 binary copied into `/usr/local/bin`,
- bundled workloads or disk images,
- GPU-specific or SystemC/SST-specific dependencies,
- root execution inside the container.

## Hard Constraints

- Do not add a second general-purpose base image unless Task 1 proves the existing image cannot satisfy the contract with a small additive change.
- Do not break current GHCR naming conventions under `ghcr.io/gem5/<image>:<tag>`.
- Do not change specialized image ownership or scope in this phase.
- Do not make docs-generation packages mandatory unless a core gem5 workflow in this repo actually requires them.
- Do not rely on host Python for the canonical Linux workflow.

## Files To Touch

- Modify: `util/dockerfiles/ubuntu-24.04_all-dependencies/Dockerfile`
- Modify: `util/dockerfiles/README.md`
- Modify: `README.md`
- Create: `util/dockerfiles/validate_ubuntu_24_04_all_dependencies.sh`
- Create: `.github/workflows/docker-image-smoke.yaml`
- Optional follow-up only if needed: `util/dockerfiles/devcontainer/Dockerfile`

## Acceptance Criteria

- The canonical image can be built locally from repo source with:

```bash
docker build \
  --pull \
  -f util/dockerfiles/ubuntu-24.04_all-dependencies/Dockerfile \
  -t gem5-local:ubuntu24-alldeps \
  .
```

- The canonical image can be built via bake metadata with:

```bash
docker buildx bake -f util/dockerfiles/docker-bake.hcl ubuntu-24-04_all-dependencies --print >/tmp/gem5-bake-plan.json
test -s /tmp/gem5-bake-plan.json
```

- A mounted checkout can build a small gem5 target:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -w /workspace \
  gem5-local:ubuntu24-alldeps \
  scons build/NULL/gem5.opt -j2
```

- A mounted checkout can also complete a full canonical build outside the fast smoke path:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -w /workspace \
  gem5-local:ubuntu24-alldeps \
  scons build/ALL/gem5.opt -j2
```

- A mounted checkout can run test harness discovery:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -v /tmp:/tmp \
  -w /workspace/tests \
  gem5-local:ubuntu24-alldeps \
  ./main.py -h
```

- The docs show the correct pull path:

```bash
docker pull ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest
```

- The docs clearly distinguish:
  - canonical general-purpose image,
  - specialized images,
  - optional devcontainer path.

## Task 1: Finalize the Canonical Image Contract

**Files:**
- Modify: `util/dockerfiles/ubuntu-24.04_all-dependencies/Dockerfile`

- [x] **Step 1: Audit the current package list against the canonical image contract**

Review the current package list in `util/dockerfiles/ubuntu-24.04_all-dependencies/Dockerfile` and compare it with the required workflows in this spec.

Expected result: a short list of missing items or a written conclusion that the current package set is already sufficient.

- [x] **Step 2: Limit package additions to verified core workflow needs**

If a gap exists, only add packages that unblock common gem5 development. Acceptable phase-1 candidates are:

- `gdb`
- `locales`
- `unzip`

Explicitly do **not** add `qemu-system`, cross-compilers, GPU stacks, or full-system resources unless a core workflow in this repo proves they are required.

- [x] **Step 3: Preserve non-root-friendly runtime behavior**

Keep:

- `DEBIAN_FRONTEND=noninteractive`,
- `XDG_CACHE_HOME=/tmp/`.

Do not add a baked-in repo checkout or prebuilt gem5 binary.

- [ ] **Step 4: Build the image locally**

Run:

```bash
docker build \
  --pull \
  -f util/dockerfiles/ubuntu-24.04_all-dependencies/Dockerfile \
  -t gem5-local:ubuntu24-alldeps \
  .
```

Expected: successful image build.

Implementation note: the Task 1 audit concluded that the current package set is
already sufficient for the canonical contract, so no `Dockerfile` package
changes were required. On March 31, 2026, repeated local `docker build --pull`
attempts were blocked before the build began by Docker Hub registry access
failures while resolving `ubuntu:24.04`. The first reproductions showed both a
direct `docker pull ubuntu:24.04` TLS handshake timeout and no cached local
base image. A later rerun downloaded `ubuntu:24.04` successfully, but
`docker build --pull` still failed before any `Dockerfile` instruction ran with
`failed to fetch anonymous token` / `connection reset by peer`, which narrows
the open blocker to the forced-refresh registry path used by BuildKit rather
than the gem5 `Dockerfile` contents. A fresh rerun in this workspace on
March 31, 2026 again failed before the first `Dockerfile` instruction, this
time at `load metadata for docker.io/library/ubuntu:24.04` with
`failed to do request: Head ".../library/ubuntu/manifests/24.04": EOF`,
which is consistent with the earlier external-registry failure mode.

## Task 2: Add a Canonical Smoke Validation Script

**Files:**
- Create: `util/dockerfiles/validate_ubuntu_24_04_all_dependencies.sh`

- [x] **Step 1: Create a single entrypoint script for local validation**

The script should:

- check Docker CLI availability,
- always rebuild the image from the current Dockerfile,
- run all smoke commands from this spec,
- fail fast on the first error.

- [x] **Step 2: Validate developer tooling inside the image**

Include these commands in the script:

```bash
docker run --rm gem5-local:ubuntu24-alldeps pre-commit --version
docker run --rm gem5-local:ubuntu24-alldeps mypy --version
docker run --rm gem5-local:ubuntu24-alldeps python3 --version
docker run --rm gem5-local:ubuntu24-alldeps scons --version
```

Expected: all commands succeed.

Implementation note: the validator now runs `pre-commit --version` as the
invoking UID/GID so the smoke path exercises the image's non-root cache
behavior, and it builds from the Dockerfile directory as a smaller context
because this image does not copy repository content during the build.

- [ ] **Step 3: Validate mounted-checkout build and test harness behavior**

Include these commands in the script:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -w /workspace \
  gem5-local:ubuntu24-alldeps \
  scons build/NULL/gem5.opt -j2

docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -v /tmp:/tmp \
  -w /workspace/tests \
  gem5-local:ubuntu24-alldeps \
  ./main.py list -q --suites gem5 > /tmp/gem5_suites.txt

test -s /tmp/gem5_suites.txt
```

Expected: `build/NULL/gem5.opt` exists and suite discovery returns at least one suite.

Implementation note: a fresh March 31, 2026 rerun of
`bash util/dockerfiles/validate_ubuntu_24_04_all_dependencies.sh` did not
reach the mounted-checkout smoke commands because its initial
`docker build --pull` failed at `load metadata for docker.io/library/ubuntu:24.04`
with `failed to do request: Head ".../library/ubuntu/manifests/24.04": EOF`.
This keeps the step open for external registry availability rather than because
of a repository-side script gap.

- [ ] **Step 4: Run one non-smoke full-build validation outside the script**

After the fast smoke script passes, run:

```bash
docker run --rm \
  -u $(id -u):$(id -g) \
  -v "$PWD":/workspace \
  -w /workspace \
  gem5-local:ubuntu24-alldeps \
  scons build/ALL/gem5.opt -j2
```

Expected: the canonical image proves it can support the repo's standard full build, even though CI smoke coverage stays on the smaller target.

Implementation note: the script now keeps the fast smoke path separate from the
full `build/ALL/gem5.opt` validation, matching the spec.
On March 31, 2026, rerunning
`bash util/dockerfiles/validate_ubuntu_24_04_all_dependencies.sh` failed during
its initial `docker build --pull` with `failed to fetch anonymous token` /
`connection reset by peer` while resolving `docker.io/library/ubuntu:24.04`.
A matching standalone `docker build --pull` attempt and direct
`docker pull ubuntu:24.04` reproduction confirmed the validator never reached
its mounted-checkout smoke commands, and the separate
`build/ALL/gem5.opt` validation could not start because the image prerequisite
was unavailable. Additional diagnostics on the same date showed that removing
`--pull` from `docker build`, or disabling BuildKit for
`DOCKER_BUILDKIT=0 docker build --pull`, allowed the build to progress into the
`apt` phase, where both runs then failed on
`http://ports.ubuntu.com/ubuntu-ports/.../coreutils_9.4-3ubuntu6.2_arm64.deb`
with `502 Bad Gateway`. Task 2 Step 3, Task 2 Step 4, and the rollout
smoke-pass checkbox remain open pending external registry / package-mirror
stability rather than repository code changes. A fresh `docker image inspect
gem5-local:ubuntu24-alldeps` check in this workspace on March 31, 2026 returned
`No such image`, confirming there was no locally built image available to make
the full-build validation meaningful after the rebuild prerequisite failed.

## Task 3: Fix Docker Documentation and Make the Image Discoverable

**Files:**
- Modify: `util/dockerfiles/README.md`
- Modify: `README.md`

- [x] **Step 1: Correct the GHCR namespace examples**

Replace incorrect Docker README examples such as:

```bash
docker pull ghcr.io/gem5/gem5/ubuntu-24.04_all-dependencies:latest
```

with:

```bash
docker pull ghcr.io/gem5/ubuntu-24.04_all-dependencies:latest
```

Also correct other known Docker README inaccuracies while touching the file:

- use `gcc-compilers` instead of `gcc-compiler` for the bake group example,
- use `linux/arm64` instead of `linux/aarch64` in buildx platform examples if the current command is invalid in practice.

Also fix stale buildx target/group examples so the docs match `util/dockerfiles/docker-bake.hcl`, for example:

```bash
docker buildx bake -f util/dockerfiles/docker-bake.hcl gcc-compilers
```

- [x] **Step 2: Add a short repo-root Docker quickstart**

Add a short "Build gem5 in Docker" section to `README.md` with:

- pull path,
- `docker run` pattern using `-u $(id -u):$(id -g)`,
- mounted repo path `/workspace`,
- note about `/tmp` mount for test harness usage,
- note about conservative `-j2` on Apple Silicon Docker Desktop.

- [x] **Step 3: Distinguish the canonical image from specialized images**

Document that:

- `ubuntu-24.04_all-dependencies` is the canonical general-purpose image,
- `gcn-gpu`, `sst-env`, and `systemc-env` are specialized,
- `devcontainer` is optional and not the canonical mounted-checkout image.

- [x] **Step 4: Document local validation**

Add a short doc snippet pointing readers to:

```bash
util/dockerfiles/validate_ubuntu_24_04_all_dependencies.sh
```

Expected: a developer can discover pull, build, run, and validate commands without reading internal plan docs.

## Task 4: Add CI Smoke Coverage For Docker Image Regressions

**Files:**
- Create: `.github/workflows/docker-image-smoke.yaml`

- [x] **Step 1: Create a workflow that runs on Docker-related changes**

Trigger on:

- pull requests touching `util/dockerfiles/**`,
- `README.md`,
- `.github/workflows/docker-image-smoke.yaml`.

Use `runs-on: ubuntu-24.04` unless a repo-specific runner constraint is discovered during implementation.

- [x] **Step 2: Build the canonical image in CI**

In the workflow:

- check out the repo,
- build `gem5-local:ubuntu24-alldeps` from `util/dockerfiles/ubuntu-24.04_all-dependencies/Dockerfile`.

- [x] **Step 3: Run the same smoke script in CI**

Execute:

```bash
bash util/dockerfiles/validate_ubuntu_24_04_all_dependencies.sh
```

Expected: Docker packaging regressions fail fast before merge.

Implementation note: the workflow now relies on the shared validator to perform
the CI image build so the smoke job does not rebuild the same image twice.

- [x] **Step 4: Keep CI scope intentionally small**

Do not make this workflow build `build/ALL/gem5.opt` in phase 1. Limit CI smoke coverage to:

- image build,
- tool versions,
- `build/NULL/gem5.opt`,
- `tests/main.py` help/list behavior.

This keeps PR latency reasonable while still validating the container contract.

## Task 5: Clarify the `devcontainer` Relationship

**Files:**
- Modify: `util/dockerfiles/README.md`
- Optional follow-up only if documentation is not enough: `util/dockerfiles/devcontainer/Dockerfile`

- [x] **Step 1: Document why `devcontainer` is not the canonical image**

State clearly that the canonical mounted-checkout workflow should use `ubuntu-24.04_all-dependencies`, because `devcontainer` currently includes a prebuilt released gem5 binary for convenience rather than source-tree fidelity.

- [x] **Step 2: Decide whether `devcontainer` needs a follow-up cleanup issue**

If maintainers want one general developer image later, file a follow-up issue to:

- remove the baked-in released binary,
- fix or remove the `./devcontainer/devcontainer.json` reference,
- re-evaluate whether `devcontainer` should become a thin wrapper over the canonical image.

Do not block this plan on that follow-up.

Implementation note: no follow-up issue was filed in this pass because the
documentation clarification is sufficient for the current phase.

## Rollout Checklist

- [x] `util/dockerfiles/ubuntu-24.04_all-dependencies/Dockerfile` matches the canonical image contract.
- [ ] Local smoke validation script exists and passes.
- [x] `util/dockerfiles/README.md` uses the correct GHCR namespace.
- [x] `README.md` contains a Docker quickstart.
- [x] CI smoke workflow exists and runs on Docker-related changes.
- [x] Docs explain the difference between canonical and specialized images.
- [x] `devcontainer` status is documented, even if its cleanup is deferred.

## Definition of Done

This work is complete when a new contributor can:

1. discover the canonical image from `README.md`,
2. pull or build it with the documented commands,
3. build a small gem5 target from a mounted checkout,
4. run `tests/main.py` discovery in-container,
5. understand when they need a specialized image instead.
