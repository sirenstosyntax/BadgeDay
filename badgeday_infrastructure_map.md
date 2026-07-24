# BadgeDay / Sirens to Syntax — Infrastructure Map

*Single source of truth for domains, hosting, and who manages what. Updated 2026-07-24.*

## Domains & routing

| Domain | Role | Hosted on | DNS managed at |
| :---- | :---- | :---- | :---- |
| **badgeday.com** | Marketing \+ waitlist site (Recruit \+ Promote). Permanent apex; never the app. | Netlify (static, deployed via drag-and-drop zip) | **Hostinger** (nameservers: aurora/nebula.dns-parking.com) |
| [**www.badgeday.com**](http://www.badgeday.com) | Redirects/serves same Netlify site | Netlify | Hostinger (CNAME → joyful-kheer-d210a0.netlify.app) |
| **app.badgeday.com** | The Promote web app (canonical product host) | Azure Container Apps | Hostinger (CNAME \+ TXT asuid.app — pending setup) |
| **api.badgeday.com** | Reserved for future mobile-app backend | — (future) | Hostinger (future) |
| **badgeday.app** | Parked; eventually 301 → badgeday.com (brand protection) | Hostinger parking | Hostinger |
| **sirenstosyntax.com** | Company site | (pre-existing setup) | (pre-existing) |

**Key fact both sides keep forgetting:** DNS for badgeday.com lives at **Hostinger**, not Netlify. Netlify only hosts the marketing site's files.

## Current DNS records for badgeday.com (Hostinger)

- A `@` → 75.2.60.5 (Netlify load balancer)  
- CNAME `www` → joyful-kheer-d210a0.netlify.app  
- *(pending)* CNAME `app` → badgeday-web.redgrass-87ddbb2c.centralus.azurecontainerapps.io  
- *(pending)* TXT `asuid.app` → Azure domain-verification ID  
- All other records (MX, TXT, autoconfig, etc.): do not touch

## Division of responsibilities

| Concern | Owner |
| :---- | :---- |
| Marketing site (badgeday.com), content, deploys | Cowork session (marketing) — Netlify drag-and-drop |
| Email list, tags, lead magnets, broadcasts | Kit (Sirens to Syntax account). Tags: `badgeday`, `bd-recruit`, `bd-promote`; DrillGround separate |
| Waitlist forms | Kit forms 9721830 (recruit) / 9721937 (promote); marketing site posts to them directly |
| Analytics | PostHog, single free-plan project shared with sirenstosyntax.com — filter by `$host`. Custom event: `waitlist_signup` (property `audience`: recruit/promote) |
| The Promote app, Azure infra, Stripe, az commands | Claude Code session (app repo: sirens-to-syntax-os) |
| Hostinger DNS edits | Grant, guided by whichever session needs the record |
| Social, content calendar, weekly draft batches | Cowork session (automated Monday batches) |

## App ↔ marketing touchpoints (the only intentional overlaps)

1. **PUBLIC\_WEB\_URL** (app) \= [https://app.badgeday.com](https://app.badgeday.com) — set in Azure, drives Stripe URLs.  
2. At app launch: marketing site adds "Open the app → app.badgeday.com" and app-store badges. Marketing side handles this.  
3. Future mobile apps: universal links / assetlinks files (apple-app-site-association, assetlinks.json) would be served from badgeday.com — marketing/Netlify side hosts them; app side supplies the file contents.  
4. Waitlist emails (Kit list) become launch-announcement audience — marketing side sends.

## Brand constants (for anything user-facing either side builds)

- Colors: charcoal \#171E26 · red \#C8102E · gold \#E8A33D · font: Inter  
- Logo: "Dawn Shield" (SVG master \+ full asset set exists on marketing side)  
- Tagline: "Earn the badge. Advance the badge."  
- Founder byline: "Grant Collings, Fire Captain — over 20 years in the fire service"  
- Hard rule: Grant's fire department is never named or visually identifiable anywhere.

