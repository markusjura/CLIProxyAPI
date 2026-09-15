# Maintaining our CLIProxyAPI build

This fork owns the patch queue, upstream compatibility tests, and macOS ARM64 release artifacts. Dotfiles owns release selection and installation across the configured fleet. The app's CLIProxyAPI project is a workspace for this repository; no automation depends on a conversation.

## Update

Run `python3 .fork/update.py --upstream latest --output /tmp/cliproxy-candidate` from `/Users/mj/workspace/CLIProxyAPI` to test and build locally. The output directory must be empty. Omit `--upstream` to use the baseline in `.fork/config.json`, or pass an exact upstream tag.

Run `gh workflow run fork-update.yml --repo markusjura/CLIProxyAPI -f upstream=latest` to request the same process on GitHub. The workflow also checks daily. It publishes tested fork releases, never deploys them. Check `gh run list --repo markusjura/CLIProxyAPI --workflow fork-update.yml`, then `gh run watch RUN_ID --repo markusjura/CLIProxyAPI --exit-status`. Failures leave the installed release unchanged. GitHub may require enabling scheduled workflows in a newly created fork.

## Patch ownership

`.fork/patches/*.patch`, applied lexically, is the canonical source of our changes. The checked-in upstream source is a reference snapshot, not the patched production source. Each build fetches an exact upstream tag into an isolated temporary checkout, applies the queue with `git apply --index`, tests executor and translator packages, and builds there. We do not rebase or force-push the published branch.

The image patch limits inline Claude images to 2000 pixels per edge before both streaming and non-streaming requests, including tool-result images. It preserves aspect ratio and leaves smaller images and source history unchanged. PNG/JPEG/GIF/WebP are supported; oversized non-JPEG images become PNG. URL sources are left to the upstream provider. Images above 100 megapixels fail clearly before full decoding. See upstream issue https://github.com/router-for-me/CLIProxyAPI/issues/5539 (closed as not planned).

The alias recovery patch handles a changed Claude OAuth semantic suffix only when the returned alias is valid and its server and keyed tool ID identify exactly one generated alias in the current request. Exact and semantic matches retain precedence; ambiguous semantic matches, colliding tool IDs, and unknown IDs still fail as request-scoped errors. Caller-owned MCP names do not participate in recovery. Debug logs identify recoveries without recording request bodies or credentials. The reported `mcp__select_sight__push_exit_command` failure is reproduced with an explicit test table; the original incident's request table was unavailable, so its intended tool remains unverified.

The v7.3.3 compatibility patch preserves `input-modalities: [text]` when Claude tool images are relayed into OpenAI user messages. It replaces those image parts with omission markers and updates the executor tests to verify the translated message layout for streaming and non-streaming requests. Multimodal and unspecified models retain their images.

To change a patch, create a disposable checkout of the baseline tag, apply the queue, edit and test there, then stage only patch-owned files and export `git diff --cached --binary` back to the corresponding patch file. Keep patches independent where possible. Increment `patch_revision` whenever patches or the build recipe change, and update the baseline after verifying a newer upstream release. A conflict or failed test must be resolved before releasing; never skip a patch to make an update pass.

## Release and deployment

A fork release uses tag `mj-vUPSTREAM.REVISION`, binary version `UPSTREAM+mj.REVISION`, and a numeric build revision. `release.json` records the upstream commit, fork commit, patch hashes, and archive SHA-256. Commit changes before using `--publish`. Existing release assets are never overwritten. If publication fails after creating a draft, inspect and remove that incomplete draft before retrying; do not promote it manually without verifying its assets.

First deploy the dotfiles changes that add fork promotion and verification. To select a validated release for the fleet, run `/Users/mj/dotfiles/.scripts/fleet promote-cliproxy --release mj-vUPSTREAM.REVISION`. This validates and retains its artifact in the fleet's private artifact store, then stages it for the next fleet sync. Run `fleet sync` to publish the selection and `fleet maintain --only cliproxyapi` to install locally. For a user-requested update, read current membership from `.config/dotfiles/fleet.json` in the active dotfiles deployment (`~/.local/share/dotfiles/current`) and run the same fleet commands on reachable configured machines using existing SSH configuration. Verify each target, installed binary, running service, and activation status. Report offline or busy machines as pending; their normal fleet jobs handle retries. Do not hardcode machine names in this workflow. Activation defers while inbound client connections are visible; idle persistent connections may also defer it. Close those clients and retry if needed. A failed health check restores the previous binary. A user-requested update includes promotion and fleet deployment. The daily GitHub workflow remains build-and-publish only.

The dotfiles skill `update-cliproxyapi` routes natural-language update requests here. “Update CLIProxyAPI” runs the full build/reuse, promotion, fleet deployment, and verification workflow. An explicit build-only request stops before promotion.
