# One repo, many packages

Why every source package lives in this one repository, and what that promises you.

Each package is a separate product on PyPI, with its own version and its own users. Someone who installs `dlt-source-aquabyte` never sees this repository and must not be affected when another package changes. The single repo is for **our** convenience: one set of standards, one CI setup, and working examples side by side.

## What you get

These are promises. If a change breaks one, the change is wrong.

- **You only deal with your own package.** Its own tests, its own config, its own version. You don't read the others or run their tests.
- **You never write CI configuration.** Adding a source package means adding a folder. The workflows find it. The only manual step is one-time PyPI setup, covered in [release.md](release.md#first-release-of-a-package).
- **The standards are identical everywhere.** Same formatter, linter and type checker in every package. Nothing to decide, nothing to argue about in review.
- **You have working examples to copy.** Every package solves the same problem the same way, so you start by reading an existing one. This helps the agents too — they have real reference packages instead of inventing a structure.
- **A green pull request means the package can be released.** CI builds every package on every PR, so packaging mistakes show up then, not on release day.
- **A release is one tag.** Bump the version, write the changelog entry, push one tag. See [release.md](release.md).
- **You can run everything locally.** `pytest` needs no credentials, no supplier account and no network.
