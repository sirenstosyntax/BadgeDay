# iOS usage strings

The Xcode project is not in git. `mobile/ios/patch_native_ios.py` writes these
keys after CI (or a Mac) runs `npx cap add ios` / `npx cap sync ios`. They
describe what BadgeDay actually does — Promote reading-list upload and Recruit
spoken answers. Do not invent department names.

The Promote upload UI is **Files / iCloud** plus **Scan page** (camera only).
There is no Photo Library picker. Photo Library keys are documented only
because `@capacitor/camera` may inject them; the strings must not claim a
Photos path the UI does not offer.

| Key | String |
|---|---|
| `NSCameraUsageDescription` | BadgeDay uses the camera so you can photograph a page from your promotional reading list and upload it for cited practice questions. |
| `NSPhotoLibraryUsageDescription` | BadgeDay does not read your photo library. Scan page uses the camera only. This string exists only if the camera plugin requires the key. |
| `NSPhotoLibraryAddUsageDescription` | BadgeDay does not save photos to your library. This string exists only if a plugin requires the key. |
| `NSMicrophoneUsageDescription` | BadgeDay records your spoken oral-board answer so it can be transcribed and critiqued. Recordings are discarded unless you keep them for self-review. |

Files / iCloud uses the system document picker (`UIDocumentPickerViewController`)
and does not need a separate usage string.

Local notifications are requested at runtime. There is no remote push.

After sync, the App ID needs the **In-App Purchase** capability (StoreKit) so
the already-declared `@capgo/native-purchases` plugin can talk to StoreKit.
That is an App ID switch, not an IAP product. Product create in App Store
Connect stays HELD. Archive / TestFlight upload is the **TestFlight** workflow;
see `TESTFLIGHT_CI.md`.
