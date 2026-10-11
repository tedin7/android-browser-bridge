# Mozilla submission preparation

Status: package lint validation and functional testing are performed locally.
No AMO submission or Mozilla signature is claimed without an actual submission
response and a signed artifact. The maintainer needs an authenticated Mozilla
Developer Hub session or their own AMO API credentials.

Suggested listing information:

- Name: Android Browser Bridge
- Summary: Control your own Firefox Android browser from your Linux MCP assistant, without ADB.
- Homepage: https://github.com/tedin7/android-browser-bridge
- Support: https://github.com/tedin7/android-browser-bridge/issues
- License: MIT
- Privacy policy: https://github.com/tedin7/android-browser-bridge/blob/main/PRIVACY.md
- Source: this repository; plain JavaScript, no bundling/minification/remote code.
- Android compatibility: declared in `browser_specific_settings.gecko_android`;
  actual Android testing must be reported honestly in review notes.

Required data categories are declared in the manifest. Supported minimum versions
are Firefox desktop 140 and Android 142, which provide built-in data consent.
The control enablement checkbox has an explicit privacy disclosure next to it;
polling remains off until the user opts in. No maintainer telemetry exists.

To validate:

```sh
npm exec --yes --package web-ext@10 -- web-ext lint --source-dir extension
python3 build.py
```

For signing without a public store listing, use your own credentials via
`WEB_EXT_API_KEY` and `WEB_EXT_API_SECRET` and run:

```sh
npm exec --yes --package web-ext@10 -- web-ext sign \
  --source-dir extension --channel unlisted --artifacts-dir signed-artifacts
```

This submits the add-on to Mozilla; it requires the maintainer's authorization
and account, and may be subject to automated or manual review. Keep credentials
out of the repository and logs. `signed-artifacts` is gitignored. The unlisted
channel yields self-distribution signing, not a public AMO marketplace listing.
For the store use the Developer Hub listed submission flow, including a full
listing, privacy policy, compatibility, and review information.

Mozilla references:
- https://extensionworkshop.com/documentation/develop/firefox-builtin-data-consent/
- https://extensionworkshop.com/documentation/publish/signing-and-distribution-overview/
