# M3.1 Runtime Hold

## Status

M3.1 is on hold. It is not complete.

## Completed

Phase 1: Passive MAIN-world capture foundation implemented and offline tested.

Phase 2: Authoritative `/api/post/item_list/` parser implemented and offline tested.

## Not Completed

- Real-page MAIN injection
- Multi-response session buffer
- Auto-scroll
- `user/detail` parser
- `comment/list` parser
- Preview integration
- Import integration
- L1 to L2 to L3 orchestration

## Verified Blocker

In the verified real Chrome runtime:

- The correct Runtime Test extension was loaded.
- Site Access was allowed.
- The extension was reloaded.
- Chrome reported no extension errors.
- A normal TikTok creator page was open without a login wall or challenge.
- The manifest declared the expected MAIN-world scripts in the expected order.
- Runtime files were present, syntax-valid, and matched the source copies.
- The protocol lifecycle marker was absent.
- The MAIN lifecycle marker was absent.

Therefore, the declared static MAIN-world content-script group did not
successfully inject or execute in the verified project/runtime environment.

This does not establish that Chrome universally cannot support static
MAIN-world content scripts. The failure is scoped to the verified
project/runtime environment.

## Resume Entry Point

Investigate or replace the MAIN-world injection mechanism before building the
session buffer, auto-scroll, `user/detail`, `comment/list`, Preview integration,
Import integration, or final L1 to L2 to L3 orchestration. Do not restart the
investigation from the item-list parser.
