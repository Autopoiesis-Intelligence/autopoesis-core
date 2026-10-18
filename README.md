# autopoesis-core

A minimal, file-driven core for deterministic state evolution.

## Operating model

1. Put tasks in `TASKS.json`.
2. Run `python run_tasks.py`.
3. Read task outcomes from `RESULTS.json`.

The core has no user accounts, internal authorization framework, network service, external dependencies, or required API credentials.

## Current capabilities

- Deterministic JSON state digest using SHA-256 for content identity.
- A small evolution operation that accepts a meaningful state change and rejects a no-op.
- Explicit, bounded task types rather than arbitrary shell or Python execution from task data.
- Machine-readable results written to a file.
- Standard-library-only tests and CI.

## CI and result files

Every push to `main` and every pull request runs the tests and task runner on Python 3.12. The workflow uploads the generated `RESULTS.json` as the `autopoesis-core-results` artifact.

To inspect a run, open [GitHub Actions](https://github.com/Autopoiesis-Intelligence/autopoesis-core/actions), select the run, and download the artifact from its **Artifacts** section. The generated result file is an artifact, not a committed repository file; this keeps execution output separate from source history.

## Important boundary

This starter can execute the task types implemented in `run_tasks.py`. A task description alone cannot cause the program to invent and write new code. Connecting a code-writing agent is a separate next step; that adapter should produce a patch, run tests, and report results without requiring an internal authorization subsystem.

## Run

```bash
python run_tasks.py
python -m unittest discover -s tests -v
```

Edit `TASKS.json` to change the task queue. The runner replaces `RESULTS.json` on each run so the file represents the latest run.
