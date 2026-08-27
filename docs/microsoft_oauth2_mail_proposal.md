# M7.4a Microsoft OAuth2 Mail Authentication Proposal

> **DEPRECATED_REFERENCE_ONLY**
>
> Microsoft OAuth2 is not part of the current supported KOLConnect mail contract. Current support
> is standard IMAP/SMTP with password or app-password authentication where the provider permits it.
> Any future Microsoft OAuth2 work is a new product feature; this document is retained only as
> historical design reference.

## Decision

KOLConnect currently validates IMAP with username/password `LOGIN`. Microsoft may disable that
mechanism independently of whether an app password was saved correctly. OAuth2 must therefore be
a separate milestone rather than being hidden inside the M7.4 intelligence work.

## Proposed flow

1. Register a Microsoft Entra application with least-privilege delegated mail scopes.
2. Start authorization from Settings and open the system browser.
3. Receive the authorization response on a random localhost callback port with state and PKCE.
4. Exchange the code for access and refresh tokens.
5. Store refresh credentials in the existing protected application settings boundary, never in
   `Creator_Library.xlsx`, logs, URLs, or frontend state.
6. Authenticate IMAP using XOAUTH2 where supported, refresh tokens before expiry, and require
   explicit reauthorization when refresh is rejected.

## Security and lifecycle

- Scopes must be limited to the mail capabilities actually used by KOLConnect.
- Logs and API errors must redact authorization codes, tokens, client secrets, and mail bodies.
- Settings must provide disconnect/revoke and clearly distinguish saved configuration from live
  authentication status.
- Windows and macOS packages must share the localhost callback contract without fixed user paths.
- Existing password accounts remain compatible; migration is opt-in per account.

## Packaging impact

The desktop package needs browser launch, localhost callback handling, PKCE support, secure token
persistence, and Microsoft endpoint configuration. Automated tests must use mocked transports only.
