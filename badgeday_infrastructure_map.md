# BadgeDay / Sirens to Syntax — Infrastructure Map

*Single source of truth for domains, hosting, and who manages what. Updated 2026-07-26.*

## Domains & routing

| Domain | Role | Hosted on | DNS managed at |
| :---- | :---- | :---- | :---- |
| **badgeday.com** | Marketing \+ waitlist site (Recruit \+ Promote). Permanent apex; never the app. | Netlify (static, deployed via drag-and-drop zip) | **Hostinger** (nameservers: aurora/nebula.dns-parking.com) |
| [**www.badgeday.com**](http://www.badgeday.com) | Redirects/serves same Netlify site | Netlify | Hostinger (CNAME → joyful-kheer-d210a0.netlify.app) |
| **app.badgeday.com** | The Promote web app (canonical product host) | Azure Container Apps | Hostinger (CNAME \+ TXT asuid.app — **live**) |
| **api.badgeday.com** | Reserved for future mobile-app backend | — (future) | Hostinger (future) |
| **badgeday.app** | Parked; eventually 301 → badgeday.com (brand protection) | Hostinger parking | Hostinger |
| **sirenstosyntax.com** | Company site | (pre-existing setup) | (pre-existing) |

**Key fact both sides keep forgetting:** DNS for badgeday.com lives at **Hostinger**, not Netlify. Netlify only hosts the marketing site's files.

## Current DNS records for badgeday.com (Hostinger)

- A `@` → 75.2.60.5 (Netlify load balancer)  
- CNAME `www` → joyful-kheer-d210a0.netlify.app  
- CNAME `app` → badgeday-web.redgrass-87ddbb2c.centralus.azurecontainerapps.io  
- TXT `asuid.app` → Azure domain-verification ID  
- Both of the above are **in place and serving**: the hostname is bound to the `badgeday-web` container app with an Azure managed certificate, and `https://app.badgeday.com/health` returns 200.  
- All other records (MX, TXT, autoconfig, etc.): do not touch

## Division of responsibilities

| Concern | Owner |
| :---- | :---- |
| Marketing site (badgeday.com), content, deploys | Cowork session (marketing) — Netlify drag-and-drop |
| Email list, tags, lead magnets, broadcasts | Kit (Sirens to Syntax account). Tags: `badgeday`, `bd-recruit`, `bd-promote`; DrillGround separate |
| Waitlist forms | Kit forms 9721830 (recruit) / 9721937 (promote); marketing site posts to them directly |
| Analytics | PostHog, single free-plan project shared with sirenstosyntax.com — filter by `$host`. Custom event: `waitlist_signup` (property `audience`: recruit/promote) |
| The Promote app, Azure infra, Stripe, az commands | Claude Code session (app repo: `sirenstosyntax/BadgeDay`, local `~/Development/Sirens-to-Syntax/products/BadgeDay`). Not `sirens-to-syntax-os` — that repo is DrillGround, a separate B2G product. |
| Hostinger DNS edits | Grant, guided by whichever session needs the record |
| Social, content calendar, weekly draft batches | Cowork session (automated Monday batches) |

## App ↔ marketing touchpoints (the only intentional overlaps)

1. **PUBLIC\_WEB\_URL** (app) \= [https://app.badgeday.com](https://app.badgeday.com) — drives Stripe's return URLs. Set by `deploy/azure-deploy.sh`, not by hand: it uses the canonical host once that hostname is bound to the web app, and the ingress FQDN before then. Don't edit it in the Azure portal; the next deploy overwrites it.  
2. At app launch: marketing site adds "Open the app → app.badgeday.com" and app-store badges. Marketing side handles this.  
3. TWA Digital Asset Links (`assetlinks.json`) must be served from **app.badgeday.com** (the TWA start-URL host), not the marketing apex. Filled file: `web/public/.well-known/assetlinks.json` (same content as `mobile/android/assetlinks.template.json`). Reaches production on the next Azure image deploy. Apple `apple-app-site-association` stays on badgeday.com (marketing/Netlify).  
4. Waitlist emails (Kit list) become launch-announcement audience — marketing side sends.

## Brand constants (for anything user-facing either side builds)

- Colors: charcoal \#171E26 · red \#C8102E · gold \#E8A33D · font: Inter  
- Logo: "Dawn Shield" (SVG master \+ full asset set exists on marketing side)  
- Tagline: "Earn the badge. Advance the badge."  
- Founder byline: "Grant Collings, Fire Captain — over 20 years in the fire service"  
- Hard rule: Grant's fire department is never named or visually identifiable anywhere.

