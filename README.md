# kubernetes-project1

A hardened, multi-container Flask + PostgreSQL + nginx application, built first with Docker Compose and then migrated to a self-hosted Kubernetes (k3s) cluster — end to end, from Dockerfile to a live Ingress-routed deployment with self-healing and horizontal scaling.

## What this demonstrates

- **Container hardening**: minimal Alpine base images, non-root execution, read-only root filesystems, multi-stage builds, and Trivy vulnerability scanning with before/after triage (163 to 5 vulnerabilities, 2 CRITICAL/9 HIGH to 0/0)
- **Secure secrets handling**: credentials via `.env` (Compose) and Kubernetes `Secret` objects (K8s) — never committed, never baked into images
- **Health-gated orchestration**: Docker Compose healthchecks and Kubernetes readiness/liveness probes, including two real debugging sessions (a DNS-resolution race condition in Compose, and a `runAsNonRoot`/numeric-UID enforcement gap between Docker and Kubernetes)
- **Stateful vs. stateless workload design**: the app as a Kubernetes Deployment (2 replicas, disposable), Postgres as a StatefulSet (stable identity, per-Pod persistent storage) — and the reasoning for why each needed different treatment
- **Private registry workflow**: image built, scanned, and pushed to GitHub Container Registry, then pulled into the cluster via `imagePullSecrets`
- **Verified Kubernetes behaviors**: self-healing (Pod deleted, replaced automatically) and live horizontal scaling (`kubectl scale`), tested and confirmed against the running cluster, not just declared in YAML

## Architecture

Docker Compose: client -> nginx -> app -> db (single host, docker-host)

Kubernetes: client -> Ingress -> app (Deployment, 2 replicas) -> db (StatefulSet, PVC-backed), running on k3s-node1

## Structure

- `app/` — Flask application (`/health`, `/visits` endpoints)
- `Dockerfile` — multi-stage, Alpine-based, non-root, minimal final image
- `docker-compose.yml` — 3-service local stack (app, db, nginx)
- `nginx.conf` — reverse proxy config for the Compose stack
- `k8s/` — Kubernetes manifests (Deployment, StatefulSet, Services, ConfigMap, Ingress; `secret.yaml` is gitignored)
- `docs/docker-fundamentals.md` — full writeup of the Docker phase: decisions, vulnerability scan results, and debugging notes
- `docs/kubernetes-deployment.md` — full writeup of the Kubernetes phase: architecture mapping from Compose, debugging notes, and verification of self-healing/scaling behavior

## Running it

**Docker Compose:**

```
cp .env.example .env   # fill in DB_PASSWORD
docker compose up -d
curl http://localhost:8080/health
```

**Kubernetes (k3s or any cluster with an nginx Ingress Controller):**

```
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml   # create this from your own credentials first
kubectl apply -f k8s/db-statefulset.yaml
kubectl apply -f k8s/db-service.yaml
kubectl apply -f k8s/app-deployment.yaml
kubectl apply -f k8s/app-service.yaml
kubectl apply -f k8s/ingress.yaml
```

See `docs/` for the full narrative behind each decision, including what broke, why, and how it was fixed.
