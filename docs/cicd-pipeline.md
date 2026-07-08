# CI/CD Pipeline: Build, Scan, and Push on Every Commit

## Overview

Automated the manual build -> scan -> push workflow from the Docker phase into a GitHub Actions pipeline, triggered on every push or pull request to `main`. Runs on a self-hosted runner rather than GitHub-hosted runners, reusing existing infrastructure (`github-runner` VM, already running three other self-hosted runners for `fortigate-iac`, `ad-lab-iac`, and `iac-foundation`).

## What it does

On every push to `main` (and on pull requests, build/scan only):

1. Checks out the repo
2. Builds the Docker image, tagged with the commit SHA
3. Runs a Trivy vulnerability scan (CRITICAL/HIGH severity), configured to fail the entire pipeline if either severity is found
4. Logs in to GHCR using the repo's auto-generated `GITHUB_TOKEN` (no manual PAT required for this step)
5. Tags and pushes the image to GHCR under both the commit SHA and `latest`

Workflow file: `.github/workflows/build-scan-push.yml`

## Why a self-hosted runner

Reused the existing `github-runner` VM instead of provisioning a new one or using GitHub-hosted runners, consistent with how the other three repos in this homelab are set up. Required installing Docker on that VM (it previously only ran Terraform/Ansible-style jobs with no container engine) and adding the runner's service account (`cam`) to the `docker` group so the workflow's `docker build`/`docker push` steps could run without `sudo`.

Registered a fourth, dedicated runner instance (`github-runner-k8s`) on the same VM rather than reusing one of the other three runner registrations, since GitHub Actions runners are registered per-repository by default.

## Debugging Notes

### Missing `workflow` scope on PAT
First push of the workflow file itself was rejected: `refusing to allow a Personal Access Token to create or update workflow .github/workflows/build-scan-push.yml without workflow scope`. GitHub requires an explicit `workflow` scope (separate from `repo`) to create or modify anything under `.github/workflows/`, since a malicious workflow file is a realistic attack vector (arbitrary code execution on runners, secret exfiltration). Fixed by regenerating the PAT with both `repo` and `workflow` scopes.

### Trivy Action tag format changed after a supply chain incident
The pipeline failed with `Unable to resolve action aquasecurity/trivy-action@0.24.0, unable to find version 0.24.0`. Investigated and found that `trivy-action` suffered a supply chain attack at some point, after which the maintainers migrated all release tags to require a `v` prefix (`v0.35.0` instead of `0.35.0`) as part of their remediation. Updated the workflow to reference the current release (`v0.36.0`) with the correct prefix.

Worth noting for production use: pinning a third-party Action by a mutable tag (even a "correct" one) is not the most secure pattern, since tags can in principle be moved. The more robust approach is pinning to an immutable commit SHA. Used tag-pinning here as reasonable for a portfolio/learning pipeline, but would use SHA-pinning for anything handling real secrets or production deploys.

### GHCR package not authorized for the repo's GITHUB_TOKEN
Build and Trivy scan succeeded, but the push step failed: `403 Forbidden` on a blob upload to GHCR. The `docker-project1-app` package had originally been created via a manual `docker push` authenticated with a personal PAT, so it had no record of `kubernetes-project1`'s own auto-generated `GITHUB_TOKEN` as an authorized publisher. Fixed via the package's own settings (Package settings -> Manage Actions access -> Add Repository -> `kubernetes-project1`, Write role), which explicitly grants that repository's workflow runs push access to the package, independent of any personal account credentials.

## Verification

Confirmed a full green run end-to-end (build, Trivy scan pass, GHCR login, tag/push), completing in 45 seconds. Verified the resulting image landed in the package registry under a new tag matching the exact commit SHA (in addition to `latest`), confirming full traceability from a running/pushed image back to the commit that produced it.

## What I'd Do Differently in Production

- Pin third-party Actions by commit SHA rather than version tag
- Add a `pull_request`-only build/scan gate as a required status check before merge, rather than only running against `main` directly
- Separate the self-hosted runner used for this pipeline from the ones used for Terraform/Ansible jobs, to avoid a single compromised runner having broad blast radius across unrelated projects
- Add image signing (e.g. cosign) so a deployed image's provenance can be cryptographically verified, not just trusted by tag
