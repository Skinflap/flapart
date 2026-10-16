# Flapart account integration

Isolated issuer source: `backend/issuer`. No shared/live issuer or production data was changed by this lane. The copied baseline came from `Flaptown/accounts/issuer`, not a verified byte-for-byte copy of the live release. Read-only live check on 2026-10-16 found account release `20261015-05-alyra-journal` active on Belial. Parent must reconcile current release before composing deployment.

## Backend patch set

New runtime files:

- `flapart_store.py`: offline schema installer/validator, private project store, bounded PNG sanitization, publication/catalog and forum attachment projection.
- `flapart_routes.py`: explicitly registered `/flapart/*` API.
- `flapsoft_routes.py`: parent-owned module; always use latest parent source, not potentially older copied test version.

Modified integration files:

- `session_issuer.py`: opt-in `flapart_enabled`/`flapsoft_enabled`; registers route modules. Removes inherited branch-local `Path` import which otherwise shadows the global import and breaks account/font routes when member_profiles=False.
- `issuer_service.py`: allowlist/boolean validation and factory transport of both flags.
- `public_catalog.py`: already-public Flapart profile-opted-in PNGs included in image library.
- `forum_routes.py`: `artwork` optional object added to item JSON. Reads recheck public PNG eligibility. Removed/moderated posts expose no artwork.
- `account_profiles.py`: conditional Flapart project and Flapsoft export entries; removes inherited unnecessary inner json import which shadowed top-level import in new export branch.

Before startup enablement, parent should back up current DB/source/config, check original table fingerprints, and run `flapart_store.install(db)` against the quiescent DB. This provisions three additive tables and checks exact existing schema plus foreign keys. No request or registration creates tables. Register fails if Flapart schema unavailable. Configure `flapart_enabled: true`. Flapsoft migration/validation is separately parent-owned.

## Frontend patch set

- `Flapart/web/integration.js` and `integration.css`, included by editor HTML. Uses actual editor export/load/preview hooks.
- Parent must add optional image rendering to current `site/forum/forum.js`; only accept backend URL pattern `https://accounts.flaptown.com/flapart/public/[0-9a-f]{32}.png`; set image alt via property/text, lazy load, bounded display width, never use HTML rendering.
- Parent must permit `https://accounts.flaptown.com` in forum Worker img-src. Flapart CSP needs self scripts/styles/fonts, data/blob/account images, account connect; retain no inline scripts, no unsafe evaluation.

Profile publishing adds an image to the current trusted library and links the existing profile editor. It does not overwrite existing profile documents. User chooses insertion, previews and publishes their page using existing profile flow. Independent public images survive removal of a forum post; withdrawing the artwork removes its public URL, catalog entry and attachment references. Re-publishing rotates the URL and invalidates the previous frozen image; UI warns existing profile placements/posts may need updating. Disabled/unverified/deleted owners' PNG reads fail closed; revoked sessions cannot write. Downloads already copied by others cannot be recalled.

## Limits

Private cloud project JSON: 16 MiB; 24 works/account; 384 MiB combined private/public per account; 4 GiB aggregate logical payloads. Local editor supports larger projects with local project export. Public PNG: <=12 MiB, <=4096 pixels on each side, 8-bit noninterlaced RGB/RGBA. CRC, chunk order, exact bounded decompression/pixel rows/filter bytes are checked; metadata stripped; fresh IDAT encoded. No arbitrary image format decoder or untrusted renderer is invoked. Opaque private JSON is never rendered by server or public APIs.

## Verification

`test_flapart.py`: ownership, stale revisions, private export, immutable PNG snapshot, metadata stripping, separate profile opt-in, withdrawal, CSRF/CORS, lifecycle suspend/unverify/delete, Town Square alias/bans/moderation, quotas and malformed PNG/decompression bomb, offline migration validation.

Full account regression passed 277 tests in `backend/regression.log`. Final atomic endpoint authorization hardening passed 40 focused tests including revocation-race regressions in `backend/focused-final.log`. Synthetic actual Chromium flow passed at `evidence/account-browser-result.json`; images `account-profile-publish.png` and `account-townhall-publish.png` visually inspected. This tests editor and issuer contract using local synthetic services under intercepted HTTPS names, not public production availability. Browser harness `backend/browser_integration.py`; private temporary DB/cookies are destroyed, no real user records touched.

Browser command:

```
PYTHONPATH=/home/skinflap/.local/lib/python3.14/site-packages:/usr/lib/python3.14/site-packages PYTHONDONTWRITEBYTECODE=1 /home/skinflap/Projects/Flaptown/accounts/.venv/bin/python /home/skinflap/Projects/Flapart/backend/browser_integration.py
```
