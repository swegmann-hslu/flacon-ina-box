# Release Workflow

GitHub releases are produced by pushing a version tag. The CI workflow builds the
extension from the tagged commit, creates a `.vsix` package, and attaches it to a
GitHub Release.

## Normal Release

1. Update `version` in `package.json`.
2. Update the documentation version in `docs/index.md`.
3. Update `CHANGELOG.md`, moving relevant entries from `Unreleased` into the new
   version section.
4. Commit those changes.
5. Create and push a matching tag:

   ```powershell
   git tag v1.0.0
   git push origin main
   git push origin v1.0.0
   ```

6. Check the `Release VSIX` workflow run on GitHub.

The tag must match the package version exactly with a leading `v`. For example,
`package.json` version `1.0.0` must be released as tag `v1.0.0`.

## Verification

Each release includes a SHA-256 checksum next to the `.vsix` package. Users can
verify the downloaded package with:

```powershell
Get-FileHash .\flacon-in-a-box-v1.0.0.vsix -Algorithm SHA256
```

The workflow also creates a GitHub artifact attestation for the `.vsix`. Users
with the GitHub CLI can verify that the package was built by this repository's
release workflow:

```powershell
gh attestation verify .\flacon-in-a-box-v1.0.0.vsix --repo swegmann-hslu/flacon-ina-box
```

## Notes

- The `.vsix` file is built in CI and attached to the GitHub Release.
- A `.sha256` checksum and GitHub artifact attestation are produced for the
  GitHub release package.
- Local `.vsix` files are ignored by git and do not need to be committed.
- Marketplace publishing can stay manual and separate from the GitHub release.
