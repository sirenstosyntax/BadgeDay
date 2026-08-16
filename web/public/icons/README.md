# App icons — not yet supplied

**These files do not exist yet, and nothing that needs them can be built until they do.**
`manifest.webmanifest` references them, Bubblewrap reads them to generate every Android
density, and both store listings require a 1024×1024 master.

Required here:

| File | Size | Notes |
|---|---|---|
| `icon-192.png` | 192×192 | Home screen, and the manifest's minimum for installability. |
| `icon-512.png` | 512×512 | Splash and high-density launchers. |
| `icon-maskable-512.png` | 512×512 | **Not the same image.** Android crops it to whatever shape the launcher uses, so the mark must sit inside the safe zone — a circle of 80% diameter, centred — with the brand background filling the rest. A non-maskable icon used here gets its edges cut off. |
| `icon-1024.png` | 1024×1024 | The store listing master, for both App Store Connect and Play Console. No transparency, no rounded corners — both stores apply their own mask and a pre-rounded icon ends up with two. |

## Where they come from

The **Dawn Shield** master SVG and full asset set live on the marketing side, per
`badgeday_infrastructure_map.md`. Export from that master rather than tracing anything, so
the app, the marketing site and the store listings are the same mark.

## Also outstanding: the favicon is still Vite's

`web/public/favicon.svg` is the purple lightning bolt that ships with the Vite React
template. It has been the icon on app.badgeday.com since the app deployed. Replace it from
the same master while doing these — a store reviewer opening the site sees it, and so does
every candidate who bookmarks the app.

Brand constants (from `badgeday_infrastructure_map.md`): charcoal `#171E26`, red `#C8102E`,
gold `#E8A33D`.
