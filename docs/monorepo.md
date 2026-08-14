# One repo, many packages

Why every source package lives in this one repository, and what that promises you.

Each source package is a separate product on PyPI, with its own version and its own users. Someone who installs `dlt-source-aquabyte` never sees this repository and must not be affected when another package changes.

## Why one repo

Compared to one repository per source package:

- **Conventions cannot drift.** Formatter, linter, CI and docs are defined once and apply to every package. With separate repos, each copy ages on its own.
- **A new package starts free.** Adding a folder is all it takes: no repository to create, no workflows to copy, no access to set up.
- **The plumbing is shared.** The CI quality gate, the release validation and the publishing workflow are built once, and every package gets them — and every later improvement to them — for free.
- **The examples are next door.** You copy a working package, not a template that rots.
- **Breakage shows immediately.** CI runs every package on every pull request, so a change to something shared reveals at once what it breaks.
- **Consumers pay nothing for it.** Packages are versioned and released independently, so the shared repository is invisible exactly where it does not help.

## What you get

These are promises. If a change breaks one, the change is wrong.

- **You only deal with your own package.** Its own tests, its own config, its own version. You don't read the others or run their tests.
- **You never write CI configuration.** Adding a source package means adding a folder. The workflows find it. The only manual step is one-time PyPI setup, covered in [release.md](release.md#first-release-of-a-package).
- **The standards are identical everywhere.** Same formatter, linter and type checker in every package. Nothing to decide, nothing to argue about in review.
- **You have working examples to copy.** Every package solves the same problem the same way, so you start by reading an existing one. This helps the agents too — they have real reference packages instead of inventing a structure.
- **A green pull request means the package can be released.** CI builds every package on every PR, so packaging mistakes show up then, not on release day.
- **A release is one tag.** Bump the version, write the changelog entry, push one tag. See [release.md](release.md).
- **You can run everything locally.** `pytest` needs no credentials, no supplier account and no network.
