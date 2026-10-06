# Branch protection for `main`

These settings are applied on GitHub by a repository admin (Rasya). They are not applied by any file in this repo.

GitHub → Settings → Branches → Add branch ruleset (or classic rule) for `main`:

- Require a pull request before merging
  - Require 1 approving review
  - Require review from Code Owners (see `.github/CODEOWNERS`)
  - Dismiss stale approvals when new commits are pushed
- Require status checks to pass before merging, and require branches to be up to date
  - Required checks: `ci`, `security`
  - `codeql` and `dependency-review` are non-blocking until GitHub Advanced Security is confirmed for this private repo
- Block force pushes
- Block branch deletion
- (Optional) Require linear history

Also enable under Settings → Code security: Dependabot alerts, Dependabot security updates and, if available, secret scanning with push protection.

Note: required check names come from the job names in `.github/workflows/`. They only appear in the picker after the
workflows have run once.
