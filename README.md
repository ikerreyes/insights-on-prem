# Insights on Prem

Self-contained on-premise deployment of Insights for OpenShift clusters.

- **Monolithic app** (`monolithic/`) — single Python (FastAPI) service that replaces the full console.redhat.com pipeline with a minimal, deployable alternative
- **Deploys via ACM addon** — managed through the `monolithic-acm-addon-complete` branch for addon-based rollout to spoke clusters
- **Test infra** (`tests/`) — containerized test runtime image built by Tekton, used for integration and e2e testing
- **CI** — Tekton pipelines (`.tekton/`) for image builds, GitHub Actions for linting and unit tests

---

The original microservices-based approach (deploying the full console.redhat.com pipeline components individually) was explored early on but we decided to pursue the monolithic architecture instead. The microservices deployment files are preserved on the [`microservices`](https://github.com/RedHatInsights/insights-on-prem/tree/microservices) branch for reference.
