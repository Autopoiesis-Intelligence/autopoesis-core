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
- Static discovery of TODO/FIXME/HACK markers and source modules without conventional tests.
- A JSON task queue with stable candidate IDs, duplicate suppression, lifecycle statuses, attempt counts, and append-only status history.
- A replaceable `CodeWriter` interface and a bounded built-in writer that prepares a deterministic import-test patch artifact for an eligible Python module.
- Disposable sandbox verification that copies the package, applies one validated generated import test, executes only that test with a hard timeout, and records the result.
- Standard-library-only tests and CI.

## CI and result files

Every push to `main` and every pull request runs the tests and task runner on Python 3.12. The workflow uploads generated `RESULTS.json` and `TASK_QUEUE.json` as the `autopoesis-core-results` artifact.

To inspect a run, open [GitHub Actions](https://github.com/Autopoiesis-Intelligence/autopoesis-core/actions), select the run, and download the artifact from its **Artifacts** section. Generated execution files are artifacts, not committed source files; this keeps runtime output separate from source history. When running locally, `TASK_QUEUE.json` remains on disk between runs. Each GitHub Actions run starts from a clean checkout, so its queue artifact is a persisted snapshot for that run and is not automatically loaded into the next run.

## Important boundary

This starter can execute the task types implemented in `run_tasks.py`. A task description alone cannot cause the program to invent and write new code. The `prepare_test_patch` task currently generates a reviewable patch artifact for one narrow case: adding an import-smoke test for an existing module under `autopoesis/`. It does not modify source files, apply patches, or run generated code. Broader code generation remains separate. `apply_test_patch_sandbox` tests file application only; `verify_test_patch_sandbox` additionally runs the generated import test against a temporary copy of the package. A future external or local model can implement the same `CodeWriter` interface without changing the core task contract.

## Run

```bash
python run_tasks.py
python -m unittest discover -s tests -v
```

Edit `TASKS.json` to configure work. `queue_discovered_tasks` merges newly discovered candidates into `TASK_QUEUE.json` without duplicating existing IDs or overwriting their statuses. Use `update_task_status` with `task_id`, `status`, and optional `note` to persist a lifecycle change. The default `CORE-005` task invokes `prepare_test_patch` for `autopoesis/task_queue.py`; it places a reviewable generated patch in `RESULTS.json` on each run. Before returning the artifact, the writer validates artifact and file hashes, allowed output paths, duplicate paths, and Python syntax without executing generated code. `CORE-006` applies the same patch inside a disposable temporary sandbox and reports the result; the sandbox is removed after the task, and repository files are not modified. Additional `prepare_test_patch` tasks can target eligible modules by specifying an `id` and `source` path. Generated patches are not applied to the repository automatically. The separate `apply_test_patch_sandbox` task exercises file creation in a disposable directory and never executes generated code. `CORE-007` runs the generated import test in a temporary copy of the `autopoesis/` package with a 10-second timeout; it records exit code and bounded output, and deletes the workspace afterward. This is isolated from repository writes, but it is still execution of project Python code and is not a security boundary against a hostile operating system or interpreter. Supported statuses are `OPEN`, `SELECTED`, `IN_PROGRESS`, `DONE`, and `REJECTED`; moving a task to `IN_PROGRESS` increments its attempt count. The runner replaces `RESULTS.json` on each run so the file represents the latest run. Use `python run_tasks.py --queue path/to/TASK_QUEUE.json` to choose a queue file.
