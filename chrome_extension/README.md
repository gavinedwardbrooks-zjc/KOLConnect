# KOLConnect Chrome Extension

This directory contains the Chrome extension for KOLConnect v2.0.1.

Current scope:

- TikTok, Instagram, and YouTube public profile collection
- Automatic floating assistant on supported creator pages
- User-triggered analysis of up to 30 recent TikTok videos, Instagram Reels, or YouTube Shorts/videos
- Redacted diagnostic report
- Compatible `/api/extension/import` payload
- Non-blocking update prompt backed by the latest formal GitHub Release

Update checks use the GitHub Releases API and expect the formal asset name
`KOLConnect_Chrome_Extension_vX.Y.Z.zip`. Results are cached, network failures
remain silent, and users can defer the same version for 24 hours. Because this
extension is distributed as a zip/unpacked extension, the prompt downloads the
zip and never claims to install it. A newer product release is ignored unless
it includes the correctly named, uploaded Chrome Extension asset.

Recent-content analysis reports only public objective metrics. It does not produce creator grades or pricing advice.
