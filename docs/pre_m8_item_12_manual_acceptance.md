# PRE-M8 Item #12 Manual Acceptance

Run this checklist in the packaged Windows application. Do not use production data unless the
Campaign is safe to edit.

1. Open an existing Campaign and confirm its planned accounts and planned dates still display.
2. Confirm legacy publish links display as actual publications with account/time left unknown.
3. Edit one CampaignCreator and add an actual publication: choose the actual account, enter the
   public URL, and enter the actual publication time.
4. Save and reopen the Campaign. Confirm actual account, URL, and time persist, and that planned
   account/date remain unchanged.
5. Add a second actual publication and confirm both deliverables persist independently.
6. Confirm the observation time is displayed separately and is not shown as actual publication
   time.

Acceptance result: `PASS`.

Packaged Windows acceptance confirmed:

- planned account selector UX and selection persistence
- actual publication creation
- save and reopen persistence
- planned and actual publication separation
- multiple independent publications
- unknown publication time handling where applicable

No blocking defect was found. Item #12 is closed.
