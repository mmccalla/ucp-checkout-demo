# Vendored test tool: axe-core

| Field | Value |
|---|---|
| Package | `axe-core` 4.14.0 (npm), file `axe.min.js` |
| Stored as | `axe-4.14.0.min.js` (not changed) |
| npm integrity | `sha512-9WTZxEjsZ7b13TH8JPmbV2z8CHbl80/2hm3XPEG4JgNdQLK81IBRXmSxHfMAOkSqQeRxT/0dwNDz2GOm3zzpcQ==` |
| sha256 of the file | `20c09fe157a8a34a30e241aaa1fcdade657734f08ab379ecfbeb7d45cc46e878` |
| Licence | MPL-2.0 (header in the file, `axe-LICENSE`) |
| Source | https://www.npmjs.com/package/axe-core/v/4.14.0 and https://github.com/dequelabs/axe-core/tree/v4.14.0 |
| API | https://github.com/dequelabs/axe-core/blob/v4.14.0/doc/API.md (`axe.run`, `runOnly` tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, `wcag22aa`) |

The G7 e2e tests inject this file into the page and run `axe.run`. 04-build-plan.md slice S3 names "axe and keyboard checks". The tests use the file only in CI. The demo page does not load it.
