# Releasing

One page for the maintainer. Every step is a command or a gate, not a
reminder; the gates fail closed and none of them fixes anything silently.

## Before the tag

1. `main` is the SHA to promote, `dev` merged into it, CI green **on that SHA**
   (the release workflow re-checks that the tag points at `origin/main`).
2. Working tree clean; `python scripts/check_release_versions.py` passes
   (tag comes later, so labels only).
3. `CHANGELOG.md` has the version's section; `AGENTS.md`'s `stack-version`
   header, `VERSION` and `ainative.__version__` moved together (the build
   refuses a tree carrying two versions).
4. `python scripts/measure_scope.py` passes (AGENTS.md's scope table is a fact
   with an expiry date).

## Tag and release

```bash
git checkout main && git pull --ff-only
git tag v2.4.4 <MAIN_SHA>
git push origin v2.4.4
```

The **Release assets** workflow then runs, in order:

1. the tag points at `origin/main`;
2. `check_release_versions.py --tag` (tag == VERSION == package == AGENTS.md);
3. wheel, sdist, lifecycle bundle build; the V2 bridge publishes a
   `ainative-lifecycle-v2-<version>.zip`, a V3 release publishes the external
   manifest and a protocol 3 bundle (see "V2 bridge gate" below);
4. `check_release_versions.py --dist` re-reads every artifact (filenames, wheel
   METADATA, sdist PKG-INFO, protocol document, payload VERSION);
5. the **bridge gate** reads the built artifacts: a protocol 3 publication
   requires a verified `V3_BRIDGE_RELEASE` (blocked otherwise), a protocol 2
   release reports the gate as explicitly not applicable — the absence of the
   variable is never treated as proof of a V2 release;
6. `SHA256SUMS` is written;
7. **build provenance is attested** for every artifact
   (`actions/attest-build-provenance`): GitHub signs a statement that these
   bytes came from this workflow, this repository, this commit;
8. the release is created as a **draft**, assets are uploaded (no `--clobber`),
   `check_published_assets.py` compares the uploaded names, sizes and digests
   against `dist/`, and only then is the draft published.

A failure at any step leaves a draft release (or none) - never a visible
release with a partial asset set.

## V2 bridge gate (before the first V3 publication)

The first V3 release cannot be applied by any runtime older than V3, so every
installed runtime must be able to reach the bridge release first. The bridge is
a normal protocol 2 release that ships the PR-0B bridge: a V2 runtime meeting a
future protocol reports `CLI_UPDATE_REQUIRED` with the upgrade path, instead of
`UPDATE_INTEGRITY_METADATA_MISSING`.

The release workflow determines the protocol it is publishing **from the built
artifacts** (`scripts/check_release_gate.py`): a `dist/` holding
`ainative-release-v3.json` or an `ainative-lifecycle-v3-*.zip` is a protocol 3
publication and requires the repository variable `V3_BRIDGE_RELEASE` to name a
bridge that a V2 runtime can actually resolve — the same resolution a user's
updater performs. A protocol 2 release passes with the gate explicitly not
applicable. A missing variable on a V3 publication, a nonexistent bridge, or a
bridge without a valid V2 lifecycle bundle all block the release.

A runtime older than the bridge sees a V3 release as
`UPDATE_INTEGRITY_METADATA_MISSING`; its documented escape path is the same
upgrade command:

```bash
pip install --upgrade "git+https://github.com/Rwanbt/ai-native-dev-stack.git@v<bridge>"
cd your-project && ainative update
```

## PyPI

The **Publish to PyPI** workflow runs when a release is published (or on
`workflow_dispatch` with an existing tag) and uses PyPI Trusted Publishing
(OIDC). No API token is stored anywhere.

One-time setup, by the maintainer, outside this repository:

1. Create or claim the project `ainative-dev-stack` on PyPI (the first upload
   of a new name reserves it; use a TestPyPI rehearsal first if unsure);
2. PyPI -> Account -> Publishing -> **Add a new pending publisher** (or the
   project's Publishing settings once it exists):
   - owner: `Rwanbt`
   - repository: `ai-native-dev-stack`
   - workflow: `publish-pypi.yml`
   - environment: `pypi`
3. In the repository settings, create the environment `pypi` (no secrets).

Until the trusted publisher exists, PyPI rejects the upload with
`invalid-publisher`. That does not affect the GitHub Release path.

One chaining detail: a release created by `release-assets.yml` uses the
workflow token, and GitHub does not let one workflow's token trigger another
— `release: published` will not fire for it. Once the trusted publisher
exists, upload an already-published release with:

```bash
gh workflow run publish-pypi.yml -f tag=v2.4.4
```

```bash
# what a user then runs
pip install ainative-dev-stack==2.4.4
# or, isolated:
pipx install ainative-dev-stack==2.4.4
```

## Verifying what was published

```bash
# integrity: the bytes match the published sums
gh release download v2.4.4 --dir dist
cd dist && sha256sum -c SHA256SUMS

# provenance: which workflow, repository and commit produced them
gh attestation verify dist/ainative_dev_stack-2.4.4-py3-none-any.whl -R Rwanbt/ai-native-dev-stack

# PyPI provenance (attestations are published with the files)
python -m pip install --upgrade pypi-attestations
python -m pypi_attestations verify dist/ainative_dev_stack-2.4.4-py3-none-any.whl
```

`SHA256SUMS` alone proves integrity against the source that published it; it
does not authenticate a maintainer against a compromised source. The build
attestation is what binds an artifact to a specific workflow run - and #24
remains the place where stronger, end-to-end signing is tracked.

## If something is wrong after the tag

Assets are never replaced (`gh release upload` without `--clobber` refuses an
existing name). The recovery is a **new patch version**: fix, qualify, tag.
The broken tag and release stay as the historical record of what was
distributed - v2.2.0 was rolled back exactly this way.