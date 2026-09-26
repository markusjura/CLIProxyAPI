# Maintaining our CLIProxyAPI build

This fork owns the patch queue, upstream compatibility tests, and macOS ARM64 and Linux AMD64 release artifacts. Dotfiles owns deployment to the central Proxmox CLIProxyAPI LXC. The app's CLIProxyAPI project is a workspace for this repository; no automation depends on a conversation.

## Update

Run `python3 .fork/update.py --upstream latest --output /tmp/cliproxy-candidate` from `/Users/mj/workspace/CLIProxyAPI` to test and build locally. The output directory must be empty. Omit `--upstream` to use the baseline in `.fork/config.json`, or pass an exact upstream tag.

Run `gh workflow run fork-update.yml --repo markusjura/CLIProxyAPI -f upstream=latest` to request the same process on GitHub. The workflow also checks daily. It publishes tested fork releases, never deploys them. Check `gh run list --repo markusjura/CLIProxyAPI --workflow fork-update.yml`, then `gh run watch RUN_ID --repo markusjura/CLIProxyAPI --exit-status`. Failures leave the installed release unchanged. GitHub may require enabling scheduled workflows in a newly created fork.

## Patch ownership

`.fork/patches/*.patch`, applied lexically, is the canonical source of our changes. The checked-in upstream source is a reference snapshot, not the patched production source. Each build fetches an exact upstream tag into an isolated temporary checkout, applies the queue with `git apply --index`, tests executor and translator packages, and builds there. We do not rebase or force-push the published branch.

The image limits patch fits inline Claude images, including tool-result images, to Anthropic's limits in both streaming and non-streaming requests. It runs once, in `helps.FitClaudeImages`:

- Images above 2000 pixels per edge are downscaled with their aspect ratio preserved. PNG/JPEG/GIF/WebP are supported; oversized non-JPEG images become PNG. URL sources are left to the upstream provider. Images above 100 megapixels fail clearly before full decoding. See upstream issue https://github.com/router-for-me/CLIProxyAPI/issues/5539 (closed as not planned).
- Bodies above a 30 MiB budget would hit Anthropic's 32 MiB limit and `413 request_too_large`. Long image-heavy Codex threads reach it well before their token count triggers compaction, and every retry then fails. The oldest images become `[image omitted: request size limit]` text blocks that keep their `cache_control`. Omissions grow in 8 MiB steps, so the cached prompt prefix changes only after another 8 MiB of growth.

Smaller requests and the caller's history are unchanged.

The alias recovery patch handles a changed Claude OAuth semantic suffix only when the returned alias is valid and its server and keyed tool ID identify exactly one generated alias in the current request. Upstream exact, semantic, and caller-owned passthrough recovery retain precedence; ambiguous semantic matches, colliding tool IDs, and unknown IDs still fail as request-scoped errors. Caller-owned MCP names do not participate in recovery. Debug logs identify recoveries without recording request bodies or credentials. The reported `mcp__select_sight__push_exit_command` failure is reproduced with an explicit test table; the original incident's request table was unavailable, so its intended tool remains unverified.

To change a patch, create a disposable checkout of the baseline tag, apply the queue, edit and test there, then stage only patch-owned files and export `git diff --cached --binary` back to the corresponding patch file. Keep patches independent where possible. Increment `patch_revision` whenever patches or the build recipe change, and update the baseline after verifying a newer upstream release. A conflict or failed test must be resolved before releasing; never skip a patch to make an update pass.

## Release and deployment

A fork release uses tag `mj-vUPSTREAM.REVISION`, binary version `UPSTREAM+mj.REVISION`, and a numeric build revision. `release.json` records the upstream commit, fork commit, patch hashes, and archive SHA-256. Commit changes before using `--publish`. Existing release assets are never overwritten. If publication fails after creating a draft, inspect and remove that incomplete draft before retrying; do not promote it manually without verifying its assets.

Every build tests the same patched source on macOS, builds the macOS ARM64 binary, and cross-compiles a static Linux AMD64 binary. `release.json` retains the original macOS descriptor format; `release-linux-amd64.json` records the Linux archive and binary checksums, upstream commit, fork commit, and identical patch hashes. Both archives and descriptors belong to the same immutable release. Increment `patch_revision` when changing either build recipe.

Deploy a validated release with `/Users/mj/dotfiles/.scripts/homeserver/deploy-cliproxyapi.py --release mj-vUPSTREAM.REVISION`. It obtains `release-linux-amd64.json` from the fork release, checks provenance and both checksums, uploads to `ssh cliproxy`, and replaces the binary through the server's installer with model-discovery verification and rollback. The service owns its configuration and OAuth state in CT 109; deployment never replaces either. Read `dotfiles/docs/cliproxyapi.md` for access, rollback, backups, and client setup. The daily GitHub workflow remains build-and-publish only.

The dotfiles skill `update-cliproxyapi` routes natural-language update requests here. “Update CLIProxyAPI” runs the full build/reuse, central LXC deployment, and verification workflow. An explicit build-only request stops before deployment.
