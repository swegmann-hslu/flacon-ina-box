# Release Workflow

GitHub releases are produced by pushing a version tag. The CI workflow builds the
extension from the tagged commit, creates a `.vsix` package, and attaches it to a
GitHub Release.

## Normal Release

1. Update `version` in `package.json`.
2. Update `CHANGELOG.md`, moving relevant entries from `Unreleased` into the new
   version section.
3. Commit those changes.
4. Create and push a matching tag:

   ```powershell
   git tag v0.2.1
   git push origin main
   git push origin v0.2.1
   ```

5. Check the `Release VSIX` workflow run on GitHub.

The tag must match the package version exactly with a leading `v`. For example,
`package.json` version `0.2.1` must be released as tag `v0.2.1`.

## Notes

- The `.vsix` file is built in CI and attached to the GitHub Release.
- Local `.vsix` files are ignored by git and do not need to be committed.
- Marketplace publishing can stay manual and separate from the GitHub release.
