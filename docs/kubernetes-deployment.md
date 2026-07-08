# Kubernetes Deployment: Migrating the Docker Stack to k3s

## Overview

Migrated the containerized Flask/Postgres/nginx stack (see
`docker-fundamentals.md`) from Docker Compose on a single host to a
Kubernetes cluster, to learn core K8s primitives hands-on before moving to a
managed offering (AKS). Cluster: k3s v1.36.2+k3s1, single control-plane node
(`k3s-node1`, 192.168.1.168), built on Proxmox alongside the existing homelab.

## Architecture

| Compose concept | Kubernetes equivalent |
|---|---|
| `app` service | Deployment (2 replicas) + Service (ClusterIP) |
| `db` service | StatefulSet (1 replica) + headless Service |
| `nginx` reverse proxy | Ingress (nginx Ingress Controller) |
| `.env` file | ConfigMap (non-secret) + Secret (DB_PASSWORD) |
| named volume (`dbdata`) | PersistentVolumeClaim via `volumeClaimTemplates` |
| `depends_on: condition: service_healthy` | readiness/liveness probes |
| `deploy.resources.limits` | Pod `resources.requests`/`resources.limits` |
| custom bridge network | Namespace + Service-based network segmentation |

## Cluster Setup

- Installed via `curl -sfL https://get.k3s.io | sh -s - --disable traefik`
- Disabled the bundled Traefik Ingress Controller in favor of nginx Ingress,
  to keep manifests portable to other clusters (e.g. AKS) where nginx Ingress
  is more common
- Installed nginx Ingress Controller via the upstream static manifest
  (`ingress-nginx` namespace)
- Fixed default kubeconfig permissions (`chown`/`chmod 600` on
  `~/.kube/config`, exported `KUBECONFIG`) so `kubectl` runs without `sudo`

## Manifests (`k8s/`)

- `configmap.yaml` — non-secret app config (DB_HOST, DB_NAME, DB_USER)
- `secret.yaml` — DB_PASSWORD (gitignored, not committed)
- `app-deployment.yaml` — Flask app, 2 replicas, readiness/liveness probes
  against `/health`, resource requests/limits, non-root + read-only root
  filesystem via `securityContext`, `emptyDir` volume for `/tmp`,
  `imagePullSecrets` for private GHCR image access
- `app-service.yaml` — ClusterIP Service exposing the app internally
- `db-statefulset.yaml` — Postgres, 1 replica, `volumeClaimTemplates` for
  per-Pod persistent storage, `pg_isready` exec-based probes
- `db-service.yaml` — headless Service (`clusterIP: None`) required for
  StatefulSet Pod DNS identity
- `ingress.yaml` — routes `docker-project1.local` to the app Service on
  port 5000

## Key Decisions & Debugging Notes

### StatefulSet vs. Deployment for Postgres
Chose a StatefulSet over a Deployment for `db` despite running only 1
replica, because StatefulSets give each Pod a stable identity and bind a
specific PersistentVolumeClaim to that identity permanently — a Deployment's
Pods are interchangeable and don't guarantee the same volume reattaches to
the same Pod after a reschedule. For a real production Postgres deployment,
would look at a proper Postgres Operator (e.g. CloudNativePG) or a managed
service (Azure Database for PostgreSQL) rather than hand-rolling a
StatefulSet, but building this manually was valuable for understanding the
underlying primitive.

### Private registry authentication (`imagePullSecrets`)
First deploy attempt failed with `ImagePullBackOff` — the node had no
credentials for the private GHCR image (`ghcr.io/camparent/docker-project1-app`),
unlike `docker-host`, which was already authenticated via `docker login`.
Fixed by creating a `kubernetes.io/dockerconfigjson` Secret
(`kubectl create secret docker-registry`) using the same PAT, then referencing
it via `imagePullSecrets` in the Deployment's Pod spec. This is a distinct
authentication boundary from the machine that built/pushed the image — each
node that runs a Pod needs its own credentials to pull the image, a detail
that's abstracted away in managed setups like AKS + ACR with workload
identity, but explicit and manual with a self-hosted registry-adjacent setup
like this one.

### Numeric UID required for `runAsNonRoot`
Second deploy attempt failed with `CreateContainerConfigError`:
`container has runAsNonRoot and image has non-numeric user (appuser), cannot
verify user is non-root`. The Dockerfile used a named user (`USER appuser`,
created via `adduser -D appuser`), which Docker resolves to a UID at runtime
without issue — but Kubernetes' `runAsNonRoot` security context check
inspects image metadata *before* the container runtime resolves that name,
and requires a numeric UID to statically verify non-root. Fixed by explicitly
assigning a UID in the Dockerfile (`adduser -D -u 1000 appuser`, `USER 1000`),
rebuilding, and pushing a new image tag (`1.1`). This is a Kubernetes-specific
constraint that never surfaced in Docker Compose — a good example of how the
same image can behave differently depending on which orchestrator is
enforcing security policy around it.

## Verification

- Confirmed full request chain end-to-end: `curl -H "Host:
  docker-project1.local" http://<node-ip>/visits` → nginx Ingress Controller
  → app Service → Pod (env vars from ConfigMap/Secret) → headless db Service
  → `db-0` StatefulSet Pod → Postgres, with the visit counter incrementing
  correctly and persisting across Pod restarts (backed by the PVC)
- Verified self-healing: manually deleted a running `app` Pod
  (`kubectl delete pod`) — a replacement Pod was created automatically by the
  ReplicaSet controller within seconds, no manual intervention required. This
  is a meaningful behavioral difference from Compose, where a deleted/stopped
  container does not self-heal unless the daemon itself restarts.
- Verified live scaling: `kubectl scale deployment app --replicas=4` brought
  up 2 additional Pods automatically load-balanced by the existing Service;
  scaling back to `--replicas=2` terminated the newest Pods first, no service
  interruption to the remaining replicas.

## What I'd Do Differently in Production

- Multi-node cluster instead of a single control-plane node, for actual
  high availability
- Postgres via an Operator or managed service instead of a hand-rolled
  StatefulSet
- Secrets via an external manager (Azure Key Vault + CSI driver) rather than
  a K8s-native Secret, which is only base64-encoded at rest by default, not
  encrypted, unless etcd encryption-at-rest is separately configured
- Real DNS/TLS for the Ingress instead of a fake local hostname and plain HTTP
- `PodDisruptionBudget` and topology spread constraints for more control over
  which Pods survive during scale-down or node maintenance
- GitOps-style deployment (Flux/ArgoCD) instead of manually running
  `kubectl apply` per file

## Next Steps

- Redeploy this same application to AKS using existing Terraform
  (`iac-foundation` repo), applying these same K8s concepts against a managed
  control plane and Azure-native integrations (ACR + workload identity for
  image pulls, Azure networking for Ingress/LoadBalancer)
