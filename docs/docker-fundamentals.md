# Docker Fundamentals: Containerized Flask + Postgres + Nginx Stack

## Overview

A three-service containerized application built to demonstrate practical Docker
skills: multi-container orchestration, network segmentation, secrets handling,
health-gated startup ordering, and container hardening. Built on a dedicated
Proxmox VM (`docker-host`, 192.168.1.105) rather than Docker Desktop, to mirror
a real deployment environment. This was the prerequisite phase before moving
to Kubernetes (see `kubernetes-deployment.md`).

## Architecture

- **nginx** (reverse proxy) — only service with a published port (8080 → host)
- **app** (Flask) — internal only, reachable by nginx via Docker DNS (`http://app:5000`)
- **db** (Postgres 16) — internal only, reachable by app via Docker DNS (`db`)

All three services sit on a custom bridge network (`appnet`), isolating app/db
from any access outside the Docker host.

## Stack

- Docker Engine 29.6.1, Docker Compose v5.3.0
- Base images: `python:3.12-alpine` (app), `postgres:16-alpine`, `nginx:alpine`
- IaC: `docker-compose.yml`, `Dockerfile`, `nginx.conf`, `.env` (gitignored)

## Key Decisions & Tradeoffs

### Base image: Debian slim → Alpine
Started with `python:3.12-slim`. Ran a Trivy scan and found 163 vulnerabilities
(2 CRITICAL, 9 HIGH, 53 MEDIUM, 63 LOW, 36 UNKNOWN) — all traced to unused Perl
tooling pulled in by the Debian base, not anything in the app's own dependency
tree (Flask, Werkzeug, psycopg2 all scanned clean).

Switched to `python:3.12-alpine`. Required adding `postgresql-dev gcc musl-dev`
as build-only dependencies (to compile psycopg2's C extensions against musl
libc instead of glibc), then removing them post-install with `apk del
.build-deps` to keep the final image lean. Rescanned: 5 vulnerabilities,
0 CRITICAL, 0 HIGH — package count dropped from 87 to 40.

Later refactored to a proper multi-stage build (separate `builder` stage),
so build tools never touch the final image layer at all, rather than being
installed and deleted in the same stage. Final image: 91.2MB (22.5MB
compressed).

### Secrets handling
Postgres credentials are passed via `.env`, referenced in `docker-compose.yml`
with `${DB_PASSWORD}` variable substitution — never hardcoded in the compose
file or baked into the image. `.env` is gitignored.

### Non-root execution
Both the app's Dockerfile and base images run as non-root users. Limits the
blast radius of a container process compromise.

### Read-only root filesystem
`app` service runs with `read_only: true` and a `tmpfs` mount at `/tmp` for
any runtime temp-file needs. The rest of the container filesystem is
immutable at runtime — no ability to drop a persistent payload even with
code execution inside the container.

### Resource limits
Each service has explicit CPU/memory limits (`deploy.resources.limits`) so a
single misbehaving or compromised container can't starve the Docker host or
its neighbors.

### Health-gated startup ordering
Initially used plain `depends_on`, which only orders container *starts*, not
service *readiness*. Discovered this the hard way: killed the `db` container
mid-request and got a DNS resolution failure (`could not translate host name
"db"`) rather than a connection-refused error — confirming that once a
container fully stops, Docker's embedded DNS drops it from service discovery
entirely, a different failure mode than "container running but not ready yet."

Fixed by adding a `healthcheck` to `db` (`pg_isready`) and changing `app`'s
`depends_on` to `condition: service_healthy`. Later hit the same race
condition between `app` and `nginx`. Fixed the same way: added a healthcheck
to `app` itself (Python's `urllib.request` against `/health`, since the
Alpine image doesn't ship curl) and gated `nginx`'s `depends_on` on `app`'s
health.

## Debugging Notes

- **Bind-mounting a file that doesn't exist yet on the host**: Docker will
  silently create a directory at that path instead of failing clearly. Hit
  this with `nginx.conf` — fix: remove the auto-created directory
  (`rm -rf nginx.conf`), then create the file properly.
- **`restart: unless-stopped` vs `restart: always`**: `unless-stopped`
  respects an explicit `docker stop` and will not auto-restart the container
  — confirmed by manually stopping `db` and watching it stay down.

## Vulnerability Scan Results (Trivy)

| Base Image | Total | Critical | High | Medium | Low | Unknown |
|---|---|---|---|---|---|---|
| python:3.12-slim (Debian) | 163 | 2 | 9 | 53 | 63 | 36 |
| python:3.12-alpine | 5 | 0 | 0 | 3 | 2 | 0 |

The 2 CRITICALs on the Debian build were both in `perl-base`, a transitive
dependency the app never invokes — one of the two wasn't even applicable to
this container's architecture (32-bit only). Documented here as an example
of triaging CVEs by reachability rather than treating CVSS severity as
automatically equal to real risk.

## Registry

Image pushed to GitHub Container Registry:
`ghcr.io/camparent/docker-project1-app` (tags `1.0`, `1.1`, `latest`),
private visibility. Authenticated via a scoped PAT (`write:packages`/
`read:packages` only).

## What I'd Do Differently in Production

- Use a proper WSGI server (gunicorn) instead of Flask's dev server
- Add TLS termination at nginx rather than serving plain HTTP
- Move secrets to a proper secrets manager (Vault, Azure Key Vault) instead
  of a `.env` file
- Load-test to derive real resource limit values instead of estimates
- Set up a Docker credential helper instead of the default plaintext
  `~/.docker/config.json` storage
