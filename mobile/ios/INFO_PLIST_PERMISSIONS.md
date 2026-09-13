# iOS usage strings (copy into Info.plist on Mac `npx cap sync`)

The Xcode project is not in git. After `npx cap add ios` / `npx cap sync ios`
on a Mac, set these keys. They describe what BadgeDay actually does — Promote
reading-list upload and Recruit spoken answers. Do not invent department names.

| Key | String |
|---|---|
| `NSCameraUsageDescription` | BadgeDay uses the camera so you can photograph a page from your promotional reading list and upload it for cited practice questions. |
| `NSPhotoLibraryUsageDescription` | BadgeDay reads a photo you choose so you can upload a page from your promotional reading list. |
| `NSPhotoLibraryAddUsageDescription` | BadgeDay does not save photos to your library. This string exists only if a plugin requires the key. |
| `NSMicrophoneUsageDescription` | BadgeDay records your spoken oral-board answer so it can be transcribed and critiqued. Recordings are discarded unless you keep them for self-review. |

Files / iCloud uses the system document picker (`UIDocumentPickerViewController`)
and does not need a separate usage string.

Local notifications are requested at runtime. There is no remote push.

After sync, add the **In-App Purchase** capability on the app target (StoreKit).
Do not archive or submit TestFlight from this repo slice.
