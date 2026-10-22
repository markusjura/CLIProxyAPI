# Maintaining our CLIProxyAPI build

This fork owns the patch queue, upstream compatibility tests, and macOS ARM64 and Linux AMD64 release artifacts. Dotfiles owns deployment to the central Proxmox CLIProxyAPI LXC. The app's CLIProxyAPI project is a workspace for this repository; no automation depends on a conversation.

## Update

Run `python3 .fork/update.py --upstream latest --output /tmp/cliproxy-candidate` from `/Users/mj/workspace/CLIProxyAPI` to test and build locally. The output directory must be empty. Omit `--upstream` to use the baseline in `.fork/config.json`, or pass an exact upstream tag.

Run `gh workflow run fork-update.yml --repo markusjura/CLIProxyAPI -f upstream=latest` to request the same process on GitHub. The workflow also checks daily. It publishes tested fork releases, never deploys them. Check `gh run list --repo markusjura/CLIProxyAPI --workflow fork-update.yml`, then `gh run watch RUN_ID --repo markusjura/CLIProxyAPI --exit-status`. Failures leave the installed release unchanged. GitHub may require enabling scheduled workflows in a newly created fork.

## Patch ownership

`.fork/patches/*.patch`, applied lexically, is the canonical source of our changes. The checked-in upstream source is a reference snapshot, not the patched production source. Each build fetches an exact upstream tag into an isolated temporary checkout, applies the queue with `git apply --index`, tests executor, translator, API handler, and access packages, and builds there. The handler suite includes in-flight and late WebSocket interruption coverage. We do not rebase or force-push the published branch.

The image limits patch fits inline Claude images, including tool-result images, to Anthropic's limits in both streaming and non-streaming requests. It runs once, in `helps.FitClaudeImages`:

- Images above 2000 pixels per edge are downscaled with their aspect ratio preserved. PNG/JPEG/GIF/WebP are supported; oversized non-JPEG images become PNG. URL sources are left to the upstream provider. Images above 100 megapixels fail clearly before full decoding. See upstream issue https://github.com/router-for-me/CLIProxyAPI/issues/5539 (closed as not planned).
- Bodies above a 30 MiB budget would hit Anthropic's 32 MiB limit and `413 request_too_large`. Long image-heavy Codex threads reach it well before their token count triggers compaction, and every retry then fails. The oldest images become `[image omitted: request size limit]` text blocks that keep their `cache_control`. Omissions grow in 8 MiB steps, so the cached prompt prefix changes only after another 8 MiB of growth.

Smaller requests and the caller's history are unchanged. Image fitting runs after payload configuration and before CCH signing, so the signature covers the final resized request.

The alias recovery patch handles a changed Claude OAuth semantic suffix only when the returned alias is valid and its server and keyed tool ID identify exactly one generated alias in the current request. Upstream exact, semantic, and caller-owned passthrough recovery retain precedence; ambiguous semantic matches and colliding tool IDs still fail as request-scoped errors. Unknown and invalid names retain upstream's unchanged-name fallback for the caller to handle. Caller-owned MCP names do not participate in recovery. Debug logs identify recoveries without recording request bodies or credentials. The reported `mcp__select_sight__push_exit_command` failure is reproduced with an explicit test table; the original incident's request table was unavailable, so its intended tool remains unverified.

The first two patches were audited against `v8.0.23`. Upstream still lacks image resizing and request-byte budgeting, and its stock resolver fails the unique-ID semantic-drift fixture. Keep them; WebSocket `response.interrupt` handling and late-interrupt recovery now come from upstream and require no fork patch.

The ChatGPT token access patch lets Codex use the gateway through its built-in `openai` provider, which keeps the ChatGPT desktop app's first-party features such as voice. That provider sends only the signed-in user's ChatGPT access token. The patch registers a `chatgpt-token` access provider when `CLIPROXY_CHATGPT_USER_IDS` lists allowed ChatGPT user IDs (comma separated). It accepts RS256 tokens signed by a key from `https://auth.openai.com/.well-known/jwks.json`, with issuer `https://auth.openai.com`, audience `https://api.openai.com/v1`, a valid expiry, and an allowed `chatgpt_user_id` claim. Signing keys are cached and refetched at most once per minute for an unknown key ID. Bearers that are not JWTs fall through to the API-key provider, so gateway keys keep working.

The compaction bridge patch keeps compacted Codex threads readable when they switch between OpenAI and Claude models. Codex replays compaction items to whichever model continues the thread, but Claude compactions are proxy capsules that OpenAI rejects, and OpenAI compactions are encrypted items that only OpenAI can read. Before a Responses request is dispatched, proxy capsules become developer context for every target. For non-OpenAI targets, OpenAI compaction items are summarized by the model in `CLIPROXY_COMPACTION_BRIDGE_MODEL` and replaced with that summary, cached in memory by item hash. OpenAI targets keep their native items. Items that cannot be converted are left unchanged. The hook is one line in each of the non-streaming and streaming execution paths in `sdk/api/handlers`.

Both environment variables belong to the service unit on the gateway host. Without them, the two patches are inactive.

To change a patch, create a disposable checkout of the baseline tag, apply the queue, edit and test there, then stage only patch-owned files and export `git diff --cached --binary` back to the corresponding patch file. Keep patches independent where possible. Increment `patch_revision` whenever patches or the build recipe change, and update the baseline after verifying a newer upstream release. A conflict or failed test must be resolved before releasing; never skip a patch to make an update pass.

## Release and deployment

A fork release uses tag `mj-vUPSTREAM.REVISION`, binary version `UPSTREAM+mj.REVISION`, and a numeric build revision. `release.json` records the upstream commit, fork commit, patch hashes, and archive SHA-256. Commit changes before using `--publish`. Existing release assets are never overwritten. If publication fails after creating a draft, inspect and remove that incomplete draft before retrying; do not promote it manually without verifying its assets.

Every build tests the same patched source on macOS, builds the macOS ARM64 binary, and cross-compiles a static Linux AMD64 binary. `release.json` retains the original macOS descriptor format; `release-linux-amd64.json` records the Linux archive and binary checksums, upstream commit, fork commit, and identical patch hashes. Both archives and descriptors belong to the same immutable release. Increment `patch_revision` when changing either build recipe.

Deploy a validated release with `/Users/mj/dotfiles/.scripts/homeserver/deploy-cliproxyapi.py --release mj-vUPSTREAM.REVISION`. It obtains `release-linux-amd64.json` from the fork release, checks provenance and both checksums, uploads to `ssh cliproxy`, and replaces the binary through the server's installer with model-discovery verification and rollback. The service owns its configuration and OAuth state in CT 109; deployment never replaces either. Read `dotfiles/docs/cliproxyapi.md` for access, rollback, backups, and client setup. The daily GitHub workflow remains build-and-publish only.

The dotfiles skill `update-cliproxyapi` routes natural-language update requests here. “Update CLIProxyAPI” runs the full build/reuse, central LXC deployment, and verification workflow. An explicit build-only request stops before deployment.
