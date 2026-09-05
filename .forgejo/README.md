# Forgejo workflows

Forgejo 16 treats `.forgejo/workflows` as an all-or-nothing override of
`.github/workflows`. The override intentionally runs the consolidated CI suite
and scheduled advisory OSV scans. GitHub-specific release, PyPI upload, website
deployment, Windows installer, Nix maintenance, and lockfile-fix automation are
excluded until equivalent Forgejo publishing credentials and runners are
reviewed. Container publication remains disabled here for the same reason.
