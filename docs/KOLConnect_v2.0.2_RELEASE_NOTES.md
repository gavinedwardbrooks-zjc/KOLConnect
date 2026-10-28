# KOLConnect v2.0.2

KOLConnect v2.0.2 completes the M9.1 and M9.2 desktop application release scope.

## Highlights

- Configure your own supported AI provider, API key, and model (BYOK).
- Generate evidence-based Creator AI Decisions with deterministic fallback when AI is unavailable.
- Create multilingual mail templates and AI-assisted drafts.
- Send mail through the native SMTP workflow only after explicit human preview and confirmation.
- Use the Mail Workspace together with Mail Follow-up.
- Read IMAP message bodies on demand, with Sent observation and reconciliation support.
- Upgrade existing SQLite databases through schema version 8 while preserving existing business data.

## Important limitations

- AI never sends mail automatically. Every send requires explicit human confirmation.
- SMTP server acceptance does not guarantee final delivery to the recipient.
- API usage fees are charged by the AI provider selected by the user.
- Provider, model, mailbox, and operating-system compatibility varies; unverified combinations are not claimed as supported.
- The enhanced Chrome Extension workstream is not part of this release. The stable extension remains version 2.0.1.

KOLConnect v2.0.2 macOS packages follow the repository's existing ad-hoc signing contract and are not Apple-notarized.
