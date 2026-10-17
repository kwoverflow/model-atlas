# Local Next.js ESLint Security Patch

This is a private, MIT-licensed source copy of `@next/eslint-plugin-next@16.4.2`,
not an upstream security release. `UPSTREAM.json` pins the official npm tarball's
SHA-512 integrity and every original compiled file's SHA-256.

All lint rule implementations, exports and declarations are unchanged.
Only `lib/utils/get-root-dirs.js` is replaced. Explicit absolute/relative root
directories and arrays are supported; glob syntax fails closed with a clear error.
The current single-app project uses the unchanged default `context.cwd`.

The manifest removes `fast-glob` and uses a distinct local version. npm's root
override installs this source package, including in fresh Docker builds.
No advisory suppressions, fake upstream versions, or vulnerable glob code are used.

Run `npm test` to verify unchanged upstream file hashes, root resolution bounds,
and real ESLint rule detection. Review a future upstream version before removing
this patch; do not automatically regenerate over it. `tools/prepare_next_lint_patch.mjs`
documents the integrity-checked mechanical import used to create this copy.

Known compatibility boundary: `settings.next.rootDir = "packages/*"` is intentionally
unsupported. Supply an explicit directory array instead. This is not a sandbox
for arbitrary untrusted ESLint config, which executes JavaScript by design.
