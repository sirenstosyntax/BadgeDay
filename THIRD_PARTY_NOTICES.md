# Third-party notices

MPL-2.0 packages that ship in BadgeDay. This file names the package, the
version, the license, and where the unmodified source for that version lives.
It does not copy license texts.

Build-time and release-tooling MPL packages that are not in the API image or
the iOS app are not listed here.

## certifi 2026.10.19

- Package: certifi
- Version: 2026.10.19
- License: MPL-2.0
- Ships in: the API Docker image. `Dockerfile` runs `pip install -e .`, which
  installs certifi through `app-store-server-library` and `requests`
  (`certifi>=2023.5.7`). Wheel metadata for this release says `License:
  MPL-2.0`.
- Source: https://github.com/certifi/python-certifi/tree/2026.10.19

MPL-2.0 source is available unmodified at that URL.

## @capgo/native-purchases 7.19.3

- Package: @capgo/native-purchases
- Version: 7.19.3
- License: MPL-2.0
- Ships in: the iOS app. It is a direct dependency in
  `mobile/ios/package.json`, locked at 7.19.3 in
  `mobile/ios/package-lock.json` (license field `MPL-2.0`), installed by
  `npm ci`, and compiled in by `npx cap sync ios` in `mobile/ios/build-ios.sh`.
  The published package's `package.json` says `"license": "MPL-2.0"`.
- Source: https://github.com/Cap-go/capacitor-native-purchases/tree/7.19.3

MPL-2.0 source is available unmodified at that URL.
