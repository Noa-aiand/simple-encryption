# Simple Encryption — Agent Context

## Overview
Multi-page **PGP beginner practice / learning tool** with user accounts, persistent keys, practice challenge, and a multi-note manager. Deployed on Build.io with PostgreSQL for production persistence.

> This app is intentionally designed as a **learning environment**, not a high-security tool. Keys are stored server-side so beginners can focus on learning PGP without losing their first keys.

## Frontend
- **9 pages** sharing an early-2000s clunky & vibrant theme (light blue/white palette, 3D outset buttons, rainbow dividers, subtle grid background, scrolling marquee, and terminal-style inputs):
  - `index.html` — Home with auth, PGP feature overview
  - `encrypt.html` — Key generation, encrypt/decrypt with manual key input, keypair generation RSA 2048/4096
  - `profile.html` — Username, public key save/display, nav tabs
  - `saved-keys.html` — Key library CRUD (create, rename, delete saved public keys)
  - `practice.html` — Practice hub: chooser page with 4 tool cards linking to individual practice tools
  - `pgp-practice.html` — AI practice partner with RSA-2048/4096 keypair selector, plaintext rejection, and LLM-powered dynamic encrypted replies (moved from practice.html)
  - `fingerprint.html` — PGP fingerprint validation practice tool (compute fingerprint from pasted key + match/mismatch drill with scoring)
  - `password.html` — Password strength checker practice tool (live strength meter, entropy estimate, feedback, and weak vs strong teaching examples)
  - `learn.html` — Full OPSEC guide with tabbed lessons: Threat Modeling 101, Key Hygiene & Management, Sign vs. Encrypt vs. Both
  - `threat-model.html` — Interactive threat modeling quiz with 5 real-world scenarios, multiple-choice answers, explanations, and scoring
  - **Right sidebar (Tools)** on every page with Notes (multi-note CRUD), Saved Keys list, and My Profile public key
- **Nav**: responsive burger menu, auth status in top-right, logout button. Practice is positioned right after Home to signal it as the primary feature; Learn tab has a blinking "NEW!" badge. "My Profile" removed from nav-tabs; replaced with a fixed top-right "My Profile" link button on every page.
- **Version badge**: V1.28 in bottom-right corner on every page

## Backend
- **Framework**: Flask (`server.py`)
- **Database**: PostgreSQL via `SCHEMA_TO_GO_URL` (or SQLite for local dev)
- **Tables**: `users`, `saved_keys`, `notes`, `server_config` (practice bot keypairs), `practice_conversations` (per-user, per-bot chat history)
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
- `POST /api/fingerprint` → {public_key} → {fingerprint, key_size, algorithm, valid}

### Practice
- `GET /api/practice/key?bot=<chat|banana|apple>` → selected bot's public key + key_size + name + description
- `POST /api/practice/send` → {message, bot} (must be encrypted PGP block); returns LLM-powered contextual encrypted response using the bot's personality (Tim, Jim, or Dorothy). Rejects plaintext and requires a saved user public key. Maintains per-bot conversation history (last 10 messages) so the LLM can keep a natural ongoing conversation.
- `POST /api/practice/reset` → {bot} clears the logged-in user's conversation history with that bot

## Architecture Decisions
- **PostgreSQL** for production on Build.io (rolling deploys wipe local SQLite)
- **Private keys are stored server-side** — this is a deliberate beginner-friendly choice. Users often lose their first private keys, so the app saves them to the user's profile. A clear warning is shown that this is a practice tool and not for real secrets.
- **Sidebar note encryption** uses `/api/encrypt` (server-side RSA + AES-GCM). Notes are NOT encrypted with OpenPGP.js due to format mismatch.
- **OpenPGP.js** is loaded only on `encrypt.html` and `practice.html`
- **Practice partner** has both RSA-2048 and RSA-4096 keypairs stored in `server_config` table
- **Practice bots**: three bots defined in `PRACTICE_BOTS` dict — **Tim** (chat, RSA-4096, reuses existing practice keypair), **Jim** (banana, RSA-2048, own keypair), **Dorothy** (apple, RSA-4096, own keypair; investigative journalist who handles sensitive tips). Each bot has its own system prompt and keypair in `server_config`.
- **Conversation history** is stored in `practice_conversations` table (per-user, per-bot via `bot_id` column, capped at last 10 messages) so the LLM sees prior turns and can maintain a natural ongoing conversation. The `/api/practice/reset` endpoint clears it for a specific bot.
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
> - The badge lives in the bottom-right corner of **all 12 HTML pages**.
> - On each change, increment the patch number (`V1.0` → `V1.1` → `V1.2`, etc.).
> - After updating the version, commit, push, and deploy.
> - Also update this `AGENTS.md` Version History section.

## Current Version
**V1.28**

## Version History
- **V1.28**: Major update across crypto, learning, and visual design. Added RSA-3072, ECC-256, ECC-384, and ECC-521 key types to server.py: new `resolve_key_type()`, `generate_keypair()`, `encrypt_with_public_key()`, and `decrypt_with_private_key()` helpers handle both RSA (OAEP) and ECC (ECDH-based ECIES) in a unified interface. Updated `/api/generate-keys` and `/api/encrypt` endpoints to accept `key_type` parameter (backwards-compatible with bare integers for RSA). Added `/api/sign` and `/api/verify` endpoints supporting RSA-PSS-SHA256 and ECDSA-SHA256 signatures. Created `sign-verify.html` practice tool: generate keys, sign messages, verify signatures (including a "tamper with message" button to demonstrate verification failure), added to Practice hub. Restructured `learn.html` into 8 categorized tabs: PGP Basics, Key Management, Key Sizes & Algorithms (with security equivalence table for RSA vs ECC), Key Servers, Passphrases, General OPSEC (metadata, data minimization, tool comparison, device security, social engineering awareness). All guides written for PGP/OPSEC beginners. Enhanced `y2k-fun.css` with more early-2000s color: pastel gradient page background, rainbow top-border on cards, colorful h2 underlines, gradient marquee banner, pastel subtitle shimmer, glossy button gradients, sidebar accent borders, toast notification colored borders. All text remains legible on light backgrounds. Bumped version badge to V1.28.
- **V1.24**: Added two new practice tools to the Practice hub. New `social-engineering.html` — a Social Engineering Red Flags quiz with 6 real-world scenarios (phishing email, typosquatted domain, fake IT call, CEO gift card scam, macro-enabled attachment, smishing text). Multi-select format: users pick ALL red flags they spot, then get explanations for correct and missed flags. Includes a "7 Red Flags to Watch For" reference card. New `eavesdropper.html` — "What the Eavesdropper Sees" visualizer. Users type a message and see a side-by-side comparison of what an attacker can read on an unencrypted connection (full message + metadata) vs. a PGP-encrypted connection (ciphertext only, metadata still visible). Three view modes: unencrypted only, encrypted only, compare both. Shows simulated network packets with source/destination IPs, protocol, timestamps, SMTP headers, and message content. Includes key takeaways about metadata, WiFi exposure, HTTPS vs PGP, and "store now, crack later." Added both as tool cards on the Practice hub page. Added `/social-engineering` and `/eavesdropper` server routes. Bumped version badge to V1.24.
- **V1.22**: Converted the Practice page into a hub/chooser with 4 tool cards (PGP Bot Practice, Fingerprint Validator, Password Strength Checker, Threat Modeling) linking to individual tool pages. Moved the original PGP bot practice to `pgp-practice.html`. Created `threat-model.html` — an interactive threat modeling quiz with 5 real-world scenarios (journalist/source, shared laptop, cloud backup, activist group chat, too-perfect app), multiple-choice answers, explanations, and scoring with a results screen. Added a link from the Learn page's Threat Modeling 101 tab to the new practice tool. Removed "My Profile" from the nav-tabs across all pages to declutter; added a fixed top-right "My Profile" link button on every page instead. Standardized nav-tab formatting: fixed the purple border leak on hover/active tabs (added `border-color` overrides), and converted `encrypt.html` and `index.html` sidebar-navs from inline-styled links to the clean class-based form used by all other pages. Added `/pgp-practice` and `/threat-model` server routes. Fixed the sidebar Notes tool: users can now start typing their first note immediately without clicking "+ New" — the note is auto-created with their content on the first keystroke (applied across all 10 pages). Bumped version badge to V1.22.
- **V1.19**: Added a prominent "Start Practicing" CTA button to the homepage hero section, with bot preview chips showing Tim, Jim, and Dorothy. The CTA links directly to the practice page and sits above the educational content, making practice the first action users see. Styled as a large 3D blue button matching the site theme. No backend changes.
- **V1.18**: Redesigned the practice page for clarity. Named the three bots — **Tim** (Practice Partner, RSA-4096), **Jim** (Banana Seller, RSA-2048), and **Dorothy** (Apple Seller, RSA-4096). Replaced the dropdown bot selector with visual clickable bot cards showing each bot's name, role, key size badge, and a tagline. Added detailed descriptions loaded from the server that explain what each bot does, their personality, and which key size they use. Simplified the "How It Works" instructions from 7 steps to 4 clear steps with a prerequisite note. Updated the response card heading and toast messages to use the selected bot's name. Renamed buttons for clarity ("Send Encrypted Message", "Load into Send Box"). Updated bot system prompts to reference their names. No backend API changes beyond bot name/description fields.
- **V1.17**: Added multiple practice bots with distinct personalities, keypairs, and per-bot conversation history. Three bots available via a dropdown selector on the practice page: **Practice Partner** (RSA-4096, casual chat — reuses the existing keypair), **Banana Seller** (RSA-2048, asks how many bananas and delivery address with a warning not to use real addresses), and **Apple Seller** (RSA-4096, asks how many apples and delivery address with same warning). Each bot has its own keypair stored in `server_config` and its own system prompt. Conversation history is now per-bot (new `bot_id` column in `practice_conversations` table), so resetting one bot doesn't lose another bot's chat. Updated `/api/practice/key`, `/api/practice/send`, and `/api/practice/reset` to accept a `bot` parameter. Replaced the key size dropdown with a bot selector dropdown on the practice page frontend. The encrypt box key size auto-syncs to the selected bot's key size.
- **V1.16**: Removed the manual private key textarea from the decrypt section on both `encrypt.html` and `practice.html`. The decrypt handler now automatically fetches the user's saved private key from `/api/me` (stored in My Profile), removing a redundant copy-paste step. Shows a helpful error if the user is not logged in or has no saved private key. Added an info note linking to My Profile. No backend changes.
- **V1.15**: Fixed unreadable encrypt/decrypt output text. The `.result-box` on `encrypt.html` and `.encrypted-output` / `.fail-card` on `practice.html` still used the old dark-theme styling (dark grey backgrounds with light neon green `#81c784` / light purple `#c77dff` text), making encrypted/decrypted output nearly impossible to read. Replaced all with readable white/light-blue backgrounds and dark navy text matching the site theme. Also fixed `.key-box`, `.server-status`, `showGenStatus()`, and inline purple labels on `encrypt.html`. Added an inline Encrypt/Decrypt card to the Practice page so users can encrypt a message for the practice partner and decrypt the partner's reply without leaving the page. Includes a "Send to Partner" convenience button that auto-fills the encrypted result into the Send box, and auto-fills the practice partner's public key into the encrypt box when it loads. No backend changes.
- **V1.14**: Fixed dead LLM API key (old key was getting 0 pings — silently falling back to rule-based responses). Set a new working `LLM_API_KEY` on Build.io. Made the practice partner conversational: added a `practice_conversations` DB table that stores per-user chat history, wired conversation history through `llm_reply()` → `generate_ai_response()` → `/api/practice/send` so the LLM sees prior turns and can maintain a natural ongoing conversation (capped at last 10 messages). Improved the system prompt for natural conversation. Added `/api/practice/reset` endpoint and a "Reset Conversation" button on the practice page to clear history. Added visible `logger.info` logging on every LLM call (URL, model, message count, reply length) so pings are traceable. New table: `practice_conversations` (id, owner_id, role, content, created_at).
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
- `index.html`, `encrypt.html`, `profile.html`, `saved-keys.html`, `practice.html`, `pgp-practice.html`, `fingerprint.html`, `password.html`, `learn.html`, `threat-model.html`, `social-engineering.html`, `eavesdropper.html` — frontend pages
- `intro.js` — reusable first-time introduction modal loaded on every page
- `y2k-fun.css` — shared early-2000s fun visual effects (animated rainbow divider, CTA glow, title shimmer, NEW badge, hit counter)
- `y2k-fun.js` — localStorage-based Y2K hit counter widget
