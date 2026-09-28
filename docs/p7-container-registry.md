# P7-A container registry

Status: **PARTIAL — WORKFLOW READY; REAL REGISTRY PUBLICATION AND POLICY REQUIRED**.

No existing production registry integration was found. Because the source repository is on GitHub, `.github/workflows/publish-production-images.yml` prepares a manual GHCR path using the scoped GitHub token; this is a prepared default, not proof that package publication, retention or access policy is configured.

The manual workflow builds backend, frontend, backup, proxy and metrics-proxy images and tags each with the full commit SHA. It never publishes `latest`. A release operator must first require green CI and protected-branch/reviewer approval, then run the workflow against the reviewed commit. Record the returned digest for every image.

Deployment uses `docker-compose.registry.yml.example` with `MYVITA_*_IMAGE` values pinned as `registry/name@sha256:<digest>`, followed by `pull` and `up --no-build`. Verify OCI revision labels and digest equality before starting services. The migration and backend must use the same backend digest.

Required external controls: private package visibility, least-privilege pull identity on the host, protected publication permission, retention/immutability policy, vulnerability scan, revocation procedure and registry availability owner. Credentials belong in the host secret manager, never `.env` in Git. GHCR may be replaced by another approved registry without changing the immutable-digest contract.
