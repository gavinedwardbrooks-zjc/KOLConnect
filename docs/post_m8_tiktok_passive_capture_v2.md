# TikTok Passive Capture V2 (Post-M8)

The historical M3.1 passive TikTok pipeline is retired from the current production contract. Its
parser, sanitized fixtures, protocol, and bridge remain experimental reference components and are
not injected by the production extension manifest.

Passive TikTok network capture/import is not supported in the current release. A future V2 is a
new project, not PRE-M8 legacy debt.

## Revalidation boundary

A future implementation must independently validate authoritative endpoint evidence, sanitized
fixtures, pure parsers, extension transport, application receive contracts, and import into the
current CreatorAccount, Video, and Campaign publication models. It must define idempotency,
privacy controls, failure behavior, and real packaged-runtime acceptance. Existing M3.1 components
are candidates for reuse only after that revalidation.
