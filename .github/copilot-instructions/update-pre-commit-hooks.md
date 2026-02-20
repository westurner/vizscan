---
name: Update pre-commit hooks
description: Updates the versions of pre-commit hooks in .pre-commit-config.yaml to their latest releases.
instructions: |
  1. Read the `.pre-commit-config.yaml` file to identify the repositories and their current versions.
  2. For each repository listed, find the latest release tag. You can use the GitHub API (e.g., `curl -s https://api.github.com/repos/<owner>/<repo>/releases/latest | grep '"tag_name":'`) or the `pre-commit autoupdate` command if `pre-commit` is installed.
  3. Update the `rev` field for each repository in `.pre-commit-config.yaml` to the latest version found.
  4. Ensure the formatting of the YAML file is preserved.
---
