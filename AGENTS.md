# Simple Encryption — Agent Context

## Overview
Multi-page PGP encryption web app with user accounts, persistent keys, practice challenge, and a multi-note manager. Deployed on Build.io with PostgreSQL for production persistence.

## Frontend
- **5 pages** sharing a consistent purple gradient theme (`#1a1a2e` → `#16213e`, Segoe UI):
  - `index.html` — Home with auth, PGP feature overview
  - `encrypt.html` — Key generation, encrypt/decrypt with manual key input, keypair generation RSA 2048/4096
  - `profile.html` — Username, public key save/display, nav tabs
  - `saved-keys.html` — Key library CRUD (create, rename, delete saved public keys)
  - `practice.html` — AI practice partner with RSA-4096 keypair, plaintext rejection, contextual encrypted responses
- **Right sidebar (Tools)** on every page with Notes (multi-note CRUD) + Saved Keys list
- **Nav**: responsive burger menu, auth status in top-right, logout button
- **Version badge**: V1.0 in bottom-right corner on every page

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
- `POST /api/practice/send` → {message} (must be encrypted PGP block); returns AI contextual encrypted response. Rejects plaintext.

## Architecture Decisions
- **PostgreSQL** for production on Build.io (rolling deploys wipe local SQLite)
- **No private key storage** — server never stores or sees private keys. Users are told to save keys to their device.
- **Sidebar note encryption** uses `/api/encrypt` (server-side RSA + AES-GCM). Notes are NOT encrypted with OpenPGP.js due to format mismatch.
- **OpenPGP.js** is loaded only on `encrypt.html` and `practice.html`
- **Practice partner** has a fixed RSA-4096 keypair stored in `server_config` table
- **Auto-save on notes** with 800ms debounce

## Deployment
- **Platform**: Build.io (Heroku-compatible)
- **Git remotes**: `origin` (GitHub), `build` (Build.io git URL)
- **Deploy**: `git push origin main && git push build main`
- **Stack**: heroku-24
- **Dyno**: Standard-1X, process `web: gunicorn server:app`
- **App URL**: https://simple-encryption-06d36746.onbld.com

## Version History
- **V1.0**: Current. Multi-page Flask app with auth, profile, PQML storage, saved keys, practice partner, server-side note encryption, right sidebar with Notes + Saved Keys, version badge.
- V1.0 includes: correct /api/encrypt response field (`encrypted`, not `encrypted_message`)

## Known Constraints / Gotchas
- **Build.io deploy latency**: each push takes ~2–3 minutes. Verify with `bld ps -a simple-encryption -j`.
- **Key format**: generated keys are custom PEM-base64 PGP blocks, NOT compatible with OpenPGP.js `readKey()`. Always use `/api/encrypt` and `/api/decrypt` for sidebar operations.
- **Copy function**: uses `navigator.clipboard.writeText()` with `textarea fallback + focus()` for older browsers.
- **No pipelines**: direct deploy to single app.

## File Structure
- `server.py` — Flask backend
- `index.html`, `encrypt.html`, `profile.html`, `saved-keys.html`, `practice.html` — frontend pages
