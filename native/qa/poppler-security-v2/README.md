# Pinned Poppler source preparation

Run `python3 prepare.py --archive /path/to/poppler-26.04.0.tar.xz --work /new/private/directory`.
Requires Python 3.12 or newer and git. Inputs are hash checked before extraction; an existing destination is refused. The source manifest binds every resulting file/link.

This bundle applies four upstream security fixes plus the original Krita dependency platform header fix. Exact commits and six before/after source hashes are in receipt.json. The combined patch preserves upstream code changes; one password-patch context line uses the older source cast spelling. Poppler licensing is retained in COPYING and source headers.

This is source preparation, not a complete security audit or desktop release approval. Native build, actual PDF import, compatibility, relocation and platform packaging require their own evidence. The broader dependency review remains open.
