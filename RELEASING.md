# Releasing eQ-3 MAX! Cube

[English](RELEASING.md) | [Deutsch](RELEASING.de.md)

How a release is made, step by step, so it does not depend on anyone's memory. Versions follow
[Semantic Versioning](https://semver.org/): a breaking change raises the major version, a new
feature the minor version, a fix the patch version.

## 1. Prepare

1. Check that everything meant for the release is merged to `main` and CI is green.
2. In both `CHANGELOG.md` and `CHANGELOG.en.md`, rename `[Unreleased]` to
   `[x.y.z] - YYYY-MM-DD` and start a new empty `[Unreleased]` section above it. Both sections
   become the bilingual release notes; a release must not ship with one language missing.
3. Set the new version in `custom_components/maxcube_local/manifest.json`.

## 2. Check locally

CI already runs Ruff, MyPy, Xenon, the pure unit tests, the tests in a real Home Assistant core,
Hassfest and the HACS validation. Run the same commands locally when changing code, and check the
change on a Home Assistant instance with a real Cube: the Cube's single-client protocol cannot be
fully simulated.

## 3. Pull request

Open a pull request with the changelog and version change, wait for **all** checks (tests on the
current and the minimum Home Assistant version, lint, types, complexity, Hassfest and HACS
`validate`) and squash-merge it. A release is not prepared from a red or skipped check; there are no
documented exceptions.

## 4. Tag

Create the tag on the merge commit of `main` and push it:

```bash
git checkout main && git pull
git tag vX.Y.Z
git push origin vX.Y.Z
```

The tag **must** be `v` plus the version in `manifest.json`. A suffix such as `-rc.1` makes it a
pre-release (set the same suffix in the manifest version).

## 5. What the workflow does

The tag starts `.github/workflows/release-zip.yml`, which calls the shared workflow in
[`Ebenhoeh80/.github`](https://github.com/Ebenhoeh80/.github). It checks that the tag matches the
manifest version, builds `maxcube_local.zip` (integration files at the zip root, as HACS expects with
`zip_release`), and creates or updates the GitHub release with the matching changelog section and
the zip attached. If the tag and the version differ, the workflow fails and nothing is published.
A second job then runs `scripts/release_notes.py` and replaces the release body with the German
**and** English changelog sections (the shared workflow only publishes German). A missing English
section fails that job instead of silently publishing an incomplete translation.

## 6. Verify the release

- The release page shows the changelog text and the `maxcube_local.zip` asset.
- HACS offers the new version (use *Update information* on the repository if it is slow).

## 7. Update and check a live system

Take a Home Assistant backup first. Then update through HACS, restart Home Assistant, and check that
the thermostats show current and target temperature, nothing is `unavailable`, and the log shows no new warnings for `maxcube_local`.

## 8. After the release

- If the repository is in the HACS default catalog and a review asked for the change, answer in the
  pull request there.
- Ask yourself whether the README, the translations and the roadmap section still match.
