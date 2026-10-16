# Public release status

Flapart browser editor and Flapsoft source workshop are live at https://flaptown.com. The Linux online installer is available on https://flaptown.com/flapsoft/flapart/.

This repository mirrors published GPL source and runs native platform qualification. Test artifacts are evidence, not automatically approved end-user releases. Full Windows/macOS source-fork packaging remains in progress. Official-engine plugin testing does not establish source-fork qualification.

Linux online installer 0.1.2 adds a hash-verified Ubuntu TLS security-library refresh and uses the host system certificate bundle. Installed artwork/save/upgrade tests and Python/Qt trusted, unknown-authority, wrong-host, expired-certificate and normal HTTPS checks passed. This is scoped qualification, not a claim that all bundled dependencies or hardware combinations have been exhaustively audited. Published source archive: 0.1.4.

Linux online installer0.1.3 adds CPython3.13.16 built from Sigstore-verified official source in an isolated Ubuntu22.04 environment. Its source/build package is public through Flapsoft. Host and clean-Ubuntu native drawing/save/reopen and Python/Qt certificate tests passed, along with upgrade preservation, damaged-payload refusal and early Python/glibc compatibility checks. Latest published app source archive:0.1.6.
