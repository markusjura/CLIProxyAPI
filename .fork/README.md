# Maintaining our CLIProxyAPI build

This fork owns the patch queue, upstream compatibility tests, and macOS ARM64 release artifacts. Dotfiles owns release selection and installation on studio/m1. The app's CLIProxyAPI project is a workspace for this repository; no automation depends on a conversation.

## Update

Run `python3 .fork/update.py --upstream latest --output /tmp/cliproxy-candidate` from `/Users/mj/workspace/CLIProxyAPI` to test and build locally. The output directory must be empty. Omit `--upstream` to use the baseline in `.fork/config.json`, or pass an exact upstream tag.

Run `gh workflow run fork-update.yml --repo markusjura/CLIProxyAPI -f upstream=latest` to request the same process on GitHub. The workflow also checks daily. It publishes tested fork releases, never deploys them. Check `gh run list --repo markusjura/CLIProxyAPI --workflow fork-update.yml`, then `gh run watch RUN_ID --repo markusjura/CLIProxyAPI --exit-status`. Failures leave the installed release unchanged. GitHub may require enabling scheduled workflows in a newly created fork.

## Patch ownership

`.fork/patches/*.patch`, applied lexically, is the canonical source of our changes. The checked-in upstream source is a reference snapshot, not the patched production source. Each build fetches an exact upstream tag into an isolated temporary checkout, applies the queue with `git apply --index`, tests executor and translator packages, and builds there. We do not rebase or force-push the published branch.

The image patch limits inline Claude images to 2000 pixels per edge before both streaming and non-streaming requests, including tool-result images. It preserves aspect ratio and leaves smaller images and source history unchanged. PNG/JPEG/GIF/WebP are supported; oversized non-JPEG images become PNG. URL sources are left to the upstream provider. Images above 100 megapixels fail clearly before full decoding. See upstream issue https://github.com/router-for-me/CLIProxyAPI/issues/5539 (closed as not planned).

To change a patch, create a disposable checkout of the baseline tag, apply the queue, edit and test there, then stage only patch-owned files and export `git diff --cached --binary` back to the corresponding patch file. Keep patches independent where possible. Increment `patch_revision` whenever patches or the build recipe change, and update the baseline after verifying a newer upstream release. A conflict or failed test must be resolved before releasing; never skip a patch to make an update pass.

## Release and deployment

A fork release uses tag `mj-vUPSTREAM.REVISION`, binary version `UPSTREAM+mj.REVISION`, and a numeric build revision. `release.json` records the upstream commit, fork commit, patch hashes, and archive SHA-256. Commit changes before using `--publish`. Existing release assets are never overwritten. If publication fails after creating a draft, inspect and remove that incomplete draft before retrying; do not promote it manually without verifying its assets.

First deploy the dotfiles changes that add fork promotion and verification. To select a validated release for the fleet, run `/Users/mj/dotfiles/.scripts/fleet promote-cliproxy --release mj-vUPSTREAM.REVISION`. This validates and retains its artifact in the fleet's private artifact store, then stages it for the next fleet sync. Run `fleet sync` to publish the selection and `fleet maintain --only cliproxyapi` to install locally. Other machines follow their normal fleet maintenance schedule. Activation defers while inbound client connections are visible; idle persistent connections may also defer it. Close those clients and retry if needed. A failed health check restores the previous binary. Promotion is on request, not part of the daily build workflow.

The dotfiles skill `update-cliproxyapi` routes natural-language update requests here. A generic update request builds the latest upstream candidate and reports its release; deployment is a separate action unless the user requests it too.
