# Source workshop limits

Each saved version accepts **1–256 UTF-8 text files**. `FILE_LIMIT` is shared by
server validation and `/flapsoft/session`'s `limits.files`. The browser displays
the advertised limit and refuses another file before prompting at that limit. It
also honors a lower server limit, so a staged frontend remains compatible with
the previous 100-file backend. The server remains authoritative for all writes.

The increase changes only file count. Existing limits remain:

- 512 KiB UTF-8 bytes per file, with NUL/surrogate rejection.
- 2 MiB per version, measured as the canonical UTF-8 JSON of filenames and text.
- 32 MiB per account, including retained versions and existing discussion/suggestion accounting.
- Existing path portability, collision, reserved-name and traversal checks.
- 30 projects, 200 versions per project, and 2 GiB community storage.

No migration is required. Create/save use `files_checked`; editions and accepted
suggestions reuse already-validated immutable versions. The separate 100-project
browse result cap, 100-character search query, and rate limits are unchanged.
Historical release snapshots/official-update scripts retain their original caps;
new official-update preparation must import this candidate's validator rather than
an old frozen release. No deployed backend or official source snapshot is changed
by editing these source files.

Qualification from the Flapart root:

```sh
/home/skinflap/Projects/Flaptown/accounts/.venv/bin/python -m unittest discover -s flapsoft-backend -p 'test_*.py'
PYTHONPATH=/home/skinflap/Projects/Flaptown/accounts/.venv/lib/python3.14/site-packages python3 flapsoft/qa/test_file_limit.py
node --check flapsoft/flapsoft.js
```

Backend tests cover exact 256 acceptance, 257 rejection without a new version,
ZIP file preservation, the exact 2 MiB/32 MiB boundaries, and existing security and
contribution behavior. Browser QA uses current local source and an isolated real
SQLite/Flask fixture at 320/390/1440px, including an advertised legacy 100-file cap.
It tests preserved unsaved text, pre-prompt refusal, removal/replacement and saving
at the limit. No account or public mutations occur outside disposable fixtures.
