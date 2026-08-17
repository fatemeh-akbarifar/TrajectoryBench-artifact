# Third-party material and release scope

TrajectoryBench is derived from AgentBench and retains substantial upstream
framework, environment, task, and documentation material. The repository-level
Apache License 2.0 continues to govern code distributed under that license; it
does not silently replace separate terms attached to third-party components.

The public software release therefore preserves the existing root `LICENSE`,
adds the attribution in `NOTICE`, and retains the WebShop license at
`src/server/tasks/webshop/LICENSE.md`. AgentBench must be cited when its
framework or benchmark environments are described.

The separate research-data archive is deliberately narrower than the working
directory. It contains sanitized numerical episode metrics, derived stability
tables, statistical outputs, checksums, and archive documentation. It excludes:

- raw trajectories and model-generated free text;
- provider response identifiers and credentials;
- untracked benchmark outputs and smoke-test artifacts;
- Docker images and base-image layers; and
- copied benchmark task data beyond what is already present in the tagged
  upstream-derived software repository.

Original numerical data and archive documentation created for this study are
released under CC BY 4.0. That data license does not grant rights in excluded
raw outputs, AgentBench, WebShop, other benchmark content, model services, or
container images. Anyone redistributing a broader package must review the terms
of every added component independently.
