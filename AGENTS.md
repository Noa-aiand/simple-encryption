# Simple Encryption — Agent Context

## Overview
Multi-page **PGP beginner practice / learning tool** with user accounts, persistent keys, practice challenge, and a multi-note manager. Deployed on Build.io with PostgreSQL for production persistence.

> This app is intentionally designed as a **learning environment**, not a high-security tool. Keys are stored server-side so beginners can focus on learning PGP without losing their first keys.

## Frontend
- **5 pages** sharing an early-2000s clunky & vibrant theme (light blue/white palette, 3D outset buttons, rainbow dividers, subtle grid background, scrolling marquee, and terminal-style inputs):
  - `index.html` — Home with auth, PGP feature overview
  - `encrypt.html` — Key generation, encrypt/decrypt with manual key input, keypair generation RSA 2048/4096
  - `profile.html` — Username, public key save/display, nav tabs
  - `saved-keys.html` — Key library CRUD (create, rename, delete saved public keys)
  - `practice.html` — AI practice partner with RSA-2048/4096 keypair selector, plaintext rejection, and LLM-powered dynamic encrypted replies
  - **Right sidebar (Tools)** on every page with Notes (multi-note CRUD), Saved Keys list, and My Profile public key
- **Nav**: responsive burger menu, auth status in top-right, logout button
- **Version badge**: V1.12 in bottom-right corner on every page

## Backend
- **Framework**: Flask (`server.py`)
- **Database**: PostgreSQL via `SCHEMA_TO_GO_URL` (or SQLite for local dev)
- **Tables**: `users`, `saved_keys`, `notes`, `server_config` (practice keypair)
- **Keygen**: Server-side RSA-2048/4096 using `cryptography` library (custom PGP-armored format, not raw OpenPGP.js)

## API Endpoints
### Auth
- `POST /api/register` — {username, password} → account creation
- `POST /api/login` — {username, password} → session login
- `POST /api/logout` → clears session
- `GET /api/me` → {logged_in, username, public_key}

### Profile & Keys
- `GET /api/profile` → {username, public_key}
- `POST /api/update-public-key` → saves public_key string for logged-in user
- `POST /api/update-private-key` → saves private_key string for logged-in user
- `POST /api/intro-seen` → marks the first-time introduction as seen
- `GET /api/saved-keys` → list user's saved keys
- `POST /api/saved-keys` → save new named key
- `PUT /api/saved-keys/:id` → rename/edit saved key
- `DELETE /api/saved-keys/:id` → delete saved key

### Notes
- `GET /api/notes` → list user's notes
- `POST /api/notes` → create note
- `PUT /api/notes/:id` → update title/content
- `DELETE /api/notes/:id` → delete note

### Crypto (server-side)
- `POST /api/generate-keys` → {key_size: 2048|4096} → {public_key, private_key, key_size}
- `POST /api/encrypt` → {message, public_key} → {encrypted, key_size}
- `POST /api/decrypt` → {message, public_key, private_key} → {decrypted}

### Practice
- `GET /api/practice/key` → practice partner's public key
- `POST /api/practice/send` → {message, key_size} (must be encrypted PGP block); returns LLM-powered contextual encrypted response. Rejects plaintext and requires a saved user public key.

## Architecture Decisions
- **PostgreSQL** for production on Build.io (rolling deploys wipe local SQLite)
- **Private keys are stored server-side** — this is a deliberate beginner-friendly choice. Users often lose their first private keys, so the app saves them to the user's profile. A clear warning is shown that this is a practice tool and not for real secrets.
- **Sidebar note encryption** uses `/api/encrypt` (server-side RSA + AES-GCM). Notes are NOT encrypted with OpenPGP.js due to format mismatch.
- **OpenPGP.js** is loaded only on `encrypt.html` and `practice.html`
- **Practice partner** has both RSA-2048 and RSA-4096 keypairs stored in `server_config` table
- **LLM integration** is optional and OpenAI-compatible; configure via `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL`. Defaults point to ai& (`https://api.aiand.com/v1`, model `google/gemma-4-31b-it`) but any OpenAI-compatible provider works. Falls back to rule-based replies when not configured or on API failure.
- **Auto-save on notes** with 800ms debounce

## Deployment
- **Platform**: Build.io (Heroku-compatible)
- **Git remotes**: `origin` (GitHub), `build` (Build.io git URL)
- **Deploy**: `git push origin main && git push build main`
- **Stack**: heroku-24
- **Dyno**: Standard-1X, process `web: gunicorn server:app`
- **App URL**: https://simple-encryption-06d36746.onbld.com

## Version Convention
> **Every user request that changes the project MUST bump the version badge.**
> - The badge lives in the bottom-right corner of **all 5 HTML pages**.
> - On each change, increment the patch number (`V1.0` → `V1.1` → `V1.2`, etc.).
> - After updating the version, commit, push, and deploy.
> - Also update this `AGENTS.md` Version History section.

## Current Version
**V1.13**

## Version History
- **V1.13**: De-purpled the page headers and practice "How It Works" box so they match the light blue/white theme. The V1.11 heading override (`h1, h2, h3, .subtitle`) was being beaten by the higher-specificity `.page-header h1` / `.page-header .subtitle` rules, leaving the purple `#9d4edd`/`#c77dff` headers and purple glow on the Encrypt, Profile, Saved Keys, and Practice pages. Strengthened the override with `!important` on color + text-shadow across all 5 pages. Also recolored the home page's purple lock-icon to blue, fixed the practice page's purple `.instructions` box (background, border, h3, highlight, list text), and replaced unreadable inline light-gray/light-purple/light-green text (`#ccc`, `#c77dff`, `#9d4edd`, `#81c784`) with readable dark blue/green. No backend changes.
- **V1.12**: Fixed homepage "What Does PGP Do?" section text contrast and sidebar profile text so light gray/purple copy is readable against the white/light-blue background. No backend changes.
- **V1.11**: Softened the early-2000s theme: replaced neon purple/pink palette with a light blue and white color scheme, gentler gradients, subtler shadows, and easier-on-the-eyes typography while keeping the clunky 3D buttons, rainbow divider, and marquee. No backend changes.
- **V1.10**: Full early-2000s clunky & vibrant frontend redesign: starfield background, rainbow dividers, 3D outset buttons with press effects, neon yellow headings with drop shadows, inset terminal-style inputs, and a scrolling marquee banner. No backend changes.
- **V1.9**: Standardized navigation tab formatting across all 5 pages and added Y2K-style visual touches: glossy gradient buttons, a subtle grid/scanline background overlay, glowing headings, chrome-style cards, and a CSS lock icon on the homepage.
- **V1.8**: Removed or replaced emoji icons throughout the site (warning signs, lock icons, tab icons, button icons, toast icons, and intro modal icons) with text labels and subtle CSS shapes to create a more natural, less AI-generated feel.
- **V1.7**: Added a "What Does PGP Do?" educational section to the Home page explaining what PGP is, what it does, how to use it, and when to use it. Updated the first-time introduction modal to point users to the new guide.
- **V1.6**: Added a first-time introduction modal that appears automatically when a user registers or logs in for the first time. The intro explains PGP basics, key generation, encrypt/decrypt, the practice partner challenge, saved keys, and notes. Added `intro_seen` user flag and `/api/intro-seen` endpoint to persist dismissal. Loaded via a reusable `intro.js` script across all pages.
- **V1.5**: Pivoted app positioning from "serious PGP tool" to "PGP beginner practice / learning tool". Server now stores generated private keys in user profiles for beginner convenience. Added clear "Learning Environment" warning banners on every page. Fixed JavaScript syntax errors in note-decrypt code across all pages. Fixed note decryption API call (`message`/`encrypted_message` compatibility). Added key-status indicators, key-download buttons, and private-key management in My Profile. Updated copy buttons and help text for beginners.
- **V1.4**: Improved LLM system prompt so replies directly reference the decrypted user message; standardized `copyToClipboard()` helper across all pages and fixed copy reliability; added Copy button for note content in the toolbar.
- **V1.3**: Integrated optional OpenAI-compatible LLM for dynamic practice partner replies; added `requests` dependency and `LLM_API_KEY`/`LLM_BASE_URL`/`LLM_MODEL` env vars; defaults to ai& (`https://api.aiand.com/v1`, `google/gemma-4-31b-it`); falls back to rule-based responses if LLM is unavailable.
- **V1.2**: Practice challenge now returns only an encrypted reply (requires logged-in user with saved public key); added RSA-2048/4096 practice key size selector; added My Profile tab to the right sidebar on every page showing the user's saved public key.
- **V1.1**: Fixed toolbar on Encrypt page (sidebar HTML moved before `<script>`, removed null `rightClose`). Removed private key storage entirely. Fixed copy keys with toast + fallback. Sidebar note encrypt/decrypt uses server API. 
- **V1.0**: Multi-page Flask app with auth, profile, PQML storage, saved keys, practice partner, server-side note encryption, right sidebar with Notes + Saved Keys, version badge.
- V1.0 includes: correct /api/encrypt response field (`encrypted`, not `encrypted_message`)

## Known Constraints / Gotchas
- **Build.io deploy latency**: each push takes ~2–3 minutes. Verify with `bld ps -a simple-encryption -j`.
- **Key format**: generated keys are custom PEM-base64 PGP blocks, NOT compatible with OpenPGP.js `readKey()`. Always use `/api/encrypt` and `/api/decrypt` for sidebar operations.
- **Copy function**: uses `navigator.clipboard.writeText()` with a robust off-screen `textarea` fallback (`focus()` + `select()` + `execCommand('copy')`) for older browsers and non-secure contexts.
- **LLM privacy**: enabling the LLM sends decrypted practice messages to the configured provider. Keep the API key secret and only enable it if users accept that.
- **No pipelines**: direct deploy to single app.

## File Structure
- `server.py` — Flask backend
- `index.html`, `encrypt.html`, `profile.html`, `saved-keys.html`, `practice.html` — frontend pages
- `intro.js` — reusable first-time introduction modal loaded on every page
