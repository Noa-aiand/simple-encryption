from flask import Flask, send_from_directory, request, session, jsonify, make_response
import os
import sys
import sqlite3
import base64
import secrets
import logging
import random
from werkzeug.security import generate_password_hash, check_password_hash

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Base directory (absolute, so it works regardless of working directory)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
DATABASE = os.path.join(BASE_DIR, 'users.db')

# Optional cryptography module (check for graceful degradation)
try:
    from cryptography.hazmat.primitives.asymmetric import rsa, padding
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    CRYPTO_AVAILABLE = True
    logger.info("cryptography module loaded successfully")
except ImportError as e:
    logger.warning("cryptography module not available: %s", e)
    CRYPTO_AVAILABLE = False

# Database backend setup
try:
    import psycopg2
    from psycopg2 import sql as psycopg2_sql
    PSYCOPG2_AVAILABLE = True
    logger.info("psycopg2 available")
except ImportError:
    PSYCOPG2_AVAILABLE = False
    logger.info("psycopg2 not available, using sqlite3")

# Build.io sets SCHEMA_TO_GO_URL; also support standard DATABASE_URL
DATABASE_URL = os.environ.get('SCHEMA_TO_GO_URL') or os.environ.get('DATABASE_URL')
USE_POSTGRES = bool(DATABASE_URL) and PSYCOPG2_AVAILABLE


def db_connect():
    """Open a database connection (PostgreSQL if configured, else SQLite)."""
    if USE_POSTGRES:
        return psycopg2.connect(DATABASE_URL)
    return sqlite3.connect(DATABASE)


def db_execute(cursor, sql, params=()):
    """Execute SQL, translating ? placeholders to %s for PostgreSQL."""
    if USE_POSTGRES:
        sql = sql.replace('?', '%s')
    cursor.execute(sql, params)


def get_lastrowid(cursor):
    """Return the id of the last inserted row."""
    if USE_POSTGRES:
        cursor.execute("SELECT lastval()")
        return cursor.fetchone()[0]
    return cursor.lastrowid


def integrity_error():
    """Return the IntegrityError class for the active backend."""
    if USE_POSTGRES:
        return psycopg2.IntegrityError
    return sqlite3.IntegrityError


# ============== DB Setup & Migration ==============

def init_db():
    conn = db_connect()
    c = conn.cursor()

    if USE_POSTGRES:
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
        """)
    else:
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
        """)
    conn.commit()

    try:
        c.execute("ALTER TABLE users ADD COLUMN public_key TEXT")
        conn.commit()
        logger.info("Migrated DB: added public_key column")
    except Exception:
        conn.rollback()

    if USE_POSTGRES:
        c.execute("""
            CREATE TABLE IF NOT EXISTS saved_keys (
                id SERIAL PRIMARY KEY,
                owner_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                public_key TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
    else:
        c.execute("""
            CREATE TABLE IF NOT EXISTS saved_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                public_key TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
    conn.commit()

    # Create notes table
    if USE_POSTGRES:
        c.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id SERIAL PRIMARY KEY,
                owner_id INTEGER NOT NULL,
                title TEXT NOT NULL DEFAULT 'Untitled Note',
                content TEXT NOT NULL DEFAULT '',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
    else:
        c.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                title TEXT NOT NULL DEFAULT 'Untitled Note',
                content TEXT NOT NULL DEFAULT '',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
    conn.commit()

    try:
        c.execute("ALTER TABLE users ADD COLUMN encrypted_private_key TEXT")
        conn.commit()
        logger.info("Migrated DB: added encrypted_private_key column")
    except Exception:
        conn.rollback()

    conn.close()


init_db()


# ============== Practice Partner Keypair ==============

def init_practice_keys():
    """Generate or load the server's practice RSA keypair stored in the database."""
    conn = db_connect()
    c = conn.cursor()
    db_execute(c, """
        CREATE TABLE IF NOT EXISTS server_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.commit()

    db_execute(c, "SELECT value FROM server_config WHERE key = ?", ('practice_private_key',))
    row = c.fetchone()
    if row:
        conn.close()
        return

    if not CRYPTO_AVAILABLE:
        logger.warning("Cannot generate practice keys: cryptography not available")
        conn.close()
        return

    logger.info("Generating practice partner RSA-4096 keypair...")
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=4096
    )
    public_key = private_key.public_key()

    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')

    public_b64 = base64.b64encode(public_pem.encode()).decode()
    private_b64 = base64.b64encode(private_pem.encode()).decode()

    public_block = make_pgp_block('PUBLIC KEY BLOCK', public_b64, 'Practice Partner RSA-4096')
    private_block = make_pgp_block('PRIVATE KEY BLOCK', private_b64, 'Practice Partner RSA-4096')

    db_execute(c, "INSERT INTO server_config (key, value) VALUES (?, ?), (?, ?)",
               ('practice_private_key', private_block, 'practice_public_key', public_block))
    conn.commit()
    conn.close()
    logger.info("Practice partner keypair generated and stored")


def get_practice_keys():
    """Return (public_key_block, private_key_block) for the practice partner."""
    conn = db_connect()
    c = conn.cursor()
    db_execute(c, "SELECT value FROM server_config WHERE key = ?", ('practice_public_key',))
    pub_row = c.fetchone()
    db_execute(c, "SELECT value FROM server_config WHERE key = ?", ('practice_private_key',))
    priv_row = c.fetchone()
    conn.close()
    return (pub_row[0] if pub_row else None, priv_row[0] if priv_row else None)


# ============== Static Routes ==============

def _html_response(filepath):
    resp = make_response(send_from_directory(BASE_DIR, filepath))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp


@app.route('/')
@app.route('/index.html')
def index():
    return _html_response('index.html')


@app.route('/encrypt')
@app.route('/encrypt.html')
def encrypt_page():
    return _html_response('encrypt.html')


@app.route('/profile')
@app.route('/profile.html')
def profile_page():
    return _html_response('profile.html')


@app.route('/saved-keys')
@app.route('/saved-keys.html')
def saved_keys_page():
    return _html_response('saved-keys.html')


@app.route('/practice')
@app.route('/practice.html')
def practice_page():
    return _html_response('practice.html')


@app.route('/<path:filename>')
def static_files(filename):
    """
    Serve known safe static file types from the base directory.
    This avoids accidentally serving sensitive files like .env, .db, .py, etc.
    """
    SAFE_EXTENSIONS = {
        '.html', '.htm', '.css', '.js', '.json', '.xml',
        '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico',
        '.txt', '.md', '.pdf', '.woff', '.woff2', '.ttf', '.eot'
    }

    if filename.startswith('.') or filename.startswith('_'):
        return jsonify({'error': 'Not found'}), 404

    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    if not ext or ext not in SAFE_EXTENSIONS:
        return jsonify({'error': 'Not found'}), 404

    requested_path = os.path.join(BASE_DIR, filename)
    real_requested = os.path.realpath(requested_path)
    real_base = os.path.realpath(BASE_DIR)

    if not real_requested.startswith(real_base + os.sep) and real_requested != real_base:
        return jsonify({'error': 'Not found'}), 404

    if not os.path.isfile(real_requested):
        return jsonify({'error': 'Not found'}), 404

    return send_from_directory(BASE_DIR, filename)


# ============== Auth Routes ==============

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'error': 'Username and password are required'}), 400

    if len(password) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400

    password_hash = generate_password_hash(password)

    conn = db_connect()
    c = conn.cursor()
    try:
        db_execute(c, 'INSERT INTO users (username, password_hash) VALUES (?, ?)', (username, password_hash))
        conn.commit()
        return jsonify({'message': 'Account created successfully'}), 201
    except integrity_error():
        return jsonify({'error': 'Username already exists'}), 409
    finally:
        conn.close()


@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    password = data.get('password', '')

    conn = db_connect()
    c = conn.cursor()
    db_execute(c, 'SELECT id, username, password_hash FROM users WHERE username = ?', (username,))
    user = c.fetchone()
    conn.close()

    if user and check_password_hash(user[2], password):
        session['user_id'] = user[0]
        session['username'] = user[1]
        return jsonify({'message': 'Logged in successfully', 'username': user[1]}), 200

    return jsonify({'error': 'Invalid username or password'}), 401


@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'message': 'Logged out successfully'}), 200


@app.route('/api/me', methods=['GET'])
def me():
    if 'user_id' in session:
        return jsonify({'logged_in': True, 'username': session['username']}), 200
    return jsonify({'logged_in': False}), 200


# ============== Profile Routes ==============

@app.route('/api/profile', methods=['GET'])
def get_profile():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    conn = db_connect()
    c = conn.cursor()
    db_execute(c, 'SELECT username, public_key FROM users WHERE id = ?', (session['user_id'],))
    row = c.fetchone()
    conn.close()

    if not row:
        return jsonify({'error': 'User not found'}), 404

    return jsonify({
        'username': row[0],
        'public_key': row[1] or ''
    }), 200


@app.route('/api/update-public-key', methods=['POST'])
def update_public_key():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json() or {}
    public_key = data.get('public_key', '')

    conn = db_connect()
    c = conn.cursor()
    db_execute(c, 'UPDATE users SET public_key = ? WHERE id = ?', (public_key, session['user_id']))
    conn.commit()
    conn.close()

    return jsonify({'message': 'Public key saved successfully'}), 200


# ============== Saved Keys Routes ==============

@app.route('/api/saved-keys', methods=['GET'])
def get_saved_keys():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    conn = db_connect()
    c = conn.cursor()
    db_execute(c, 'SELECT id, name, public_key, created_at FROM saved_keys WHERE owner_id = ? ORDER BY created_at DESC', (session['user_id'],))
    rows = c.fetchall()
    conn.close()

    keys = []
    for row in rows:
        keys.append({
            'id': row[0],
            'name': row[1],
            'public_key': row[2],
            'created_at': row[3]
        })

    return jsonify({'keys': keys}), 200


@app.route('/api/saved-keys', methods=['POST'])
def create_saved_key():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    public_key = (data.get('public_key') or '').strip()

    if not name:
        return jsonify({'error': 'Name is required'}), 400
    if not public_key:
        return jsonify({'error': 'Public key is required'}), 400

    conn = db_connect()
    c = conn.cursor()
    if USE_POSTGRES:
        c.execute(
            'INSERT INTO saved_keys (owner_id, name, public_key) VALUES (%s, %s, %s) RETURNING id',
            (session['user_id'], name, public_key)
        )
        key_id = c.fetchone()[0]
    else:
        db_execute(c, 'INSERT INTO saved_keys (owner_id, name, public_key) VALUES (?, ?, ?)',
                   (session['user_id'], name, public_key))
        key_id = get_lastrowid(c)
    conn.commit()
    conn.close()

    return jsonify({'message': 'Key saved successfully', 'id': key_id}), 201


@app.route('/api/saved-keys/<int:key_id>', methods=['PUT'])
def update_saved_key(key_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    public_key = (data.get('public_key') or '').strip()

    if not name:
        return jsonify({'error': 'Name is required'}), 400
    if not public_key:
        return jsonify({'error': 'Public key is required'}), 400

    conn = db_connect()
    c = conn.cursor()
    db_execute(c, 'UPDATE saved_keys SET name = ?, public_key = ? WHERE id = ? AND owner_id = ?',
               (name, public_key, key_id, session['user_id']))
    conn.commit()
    updated = c.rowcount
    conn.close()

    if updated == 0:
        return jsonify({'error': 'Key not found'}), 404

    return jsonify({'message': 'Key updated successfully'}), 200


@app.route('/api/saved-keys/<int:key_id>', methods=['DELETE'])
def delete_saved_key(key_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    conn = db_connect()
    c = conn.cursor()
    db_execute(c, 'DELETE FROM saved_keys WHERE id = ? AND owner_id = ?', (key_id, session['user_id']))
    conn.commit()
    deleted = c.rowcount
    conn.close()

    if deleted == 0:
        return jsonify({'error': 'Key not found'}), 404

    return jsonify({'message': 'Key deleted successfully'}), 200


# ============== Notes Routes ==============

@app.route('/api/notes', methods=['GET'])
def get_notes():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    conn = db_connect()
    c = conn.cursor()
    db_execute(c, 'SELECT id, title, content, updated_at FROM notes WHERE owner_id = ? ORDER BY updated_at DESC', (session['user_id'],))
    rows = c.fetchall()
    conn.close()

    notes = []
    for row in rows:
        notes.append({
            'id': row[0],
            'title': row[1],
            'content': row[2],
            'updated_at': row[3]
        })

    return jsonify({'notes': notes}), 200


@app.route('/api/notes', methods=['POST'])
def create_note():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json() or {}
    title = (data.get('title') or 'Untitled Note').strip() or 'Untitled Note'
    content = data.get('content', '')

    conn = db_connect()
    c = conn.cursor()
    if USE_POSTGRES:
        c.execute(
            'INSERT INTO notes (owner_id, title, content) VALUES (%s, %s, %s) RETURNING id',
            (session['user_id'], title, content)
        )
        note_id = c.fetchone()[0]
    else:
        db_execute(c, 'INSERT INTO notes (owner_id, title, content) VALUES (?, ?, ?)',
                   (session['user_id'], title, content))
        note_id = get_lastrowid(c)
    conn.commit()
    conn.close()

    return jsonify({'message': 'Note created', 'id': note_id, 'title': title}), 201


@app.route('/api/notes/<int:note_id>', methods=['PUT'])
def update_note(note_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json() or {}
    title = data.get('title')
    content = data.get('content')

    if title is None and content is None:
        return jsonify({'error': 'Nothing to update'}), 400

    conn = db_connect()
    c = conn.cursor()
    if title is not None and content is not None:
        db_execute(c, 'UPDATE notes SET title = ?, content = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND owner_id = ?',
                   (title.strip() or 'Untitled Note', content, note_id, session['user_id']))
    elif title is not None:
        db_execute(c, 'UPDATE notes SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND owner_id = ?',
                   (title.strip() or 'Untitled Note', note_id, session['user_id']))
    else:
        db_execute(c, 'UPDATE notes SET content = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND owner_id = ?',
                   (content, note_id, session['user_id']))
    conn.commit()
    updated = c.rowcount
    conn.close()

    if updated == 0:
        return jsonify({'error': 'Note not found'}), 404

    return jsonify({'message': 'Note updated'}), 200


@app.route('/api/notes/<int:note_id>', methods=['DELETE'])
def delete_note(note_id):
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    conn = db_connect()
    c = conn.cursor()
    db_execute(c, 'DELETE FROM notes WHERE id = ? AND owner_id = ?', (note_id, session['user_id']))
    conn.commit()
    deleted = c.rowcount
    conn.close()

    if deleted == 0:
        return jsonify({'error': 'Note not found'}), 404

    return jsonify({'message': 'Note deleted'}), 200


# ============== Practice Challenge Routes ==============

@app.route('/api/practice/key', methods=['GET'])
def practice_key():
    """Return the practice partner's public key so users can encrypt messages to it."""
    if not CRYPTO_AVAILABLE:
        return jsonify({'error': 'Cryptography not available'}), 503
    pub, _priv = get_practice_keys()
    if not pub:
        return jsonify({'error': 'Practice keypair not initialized'}), 500
    resp = jsonify({'public_key': pub})
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp, 200


def generate_ai_response(user_text):
    """Generate a contextual response based on the decrypted user message."""
    text = user_text.lower().strip()

    if any(k in text for k in ['hello', 'hi', 'hey', 'greetings']):
        responses = [
            "Hello! Your encryption looks perfect. This response is encrypted just for you. Welcome to the PGP practice challenge!",
            "Hi there! I successfully decrypted your message. Can you decrypt my reply? That's the whole point of end-to-end encryption!",
            "Greetings! Your PGP message arrived safely. Only someone with your private key can read what I'm saying right now."
        ]
        return random.choice(responses)

    if any(k in text for k in ['how', 'what', 'why', 'when', 'where', 'who']):
        responses = [
            "Great question! Since you encrypted this, only you can read my answer. That's the power of asymmetric cryptography!",
            "You asked something interesting. Notice how this entire conversation is protected? No eavesdropper can read what either of us wrote.",
            "Excellent curiosity! PGP encrypts a random AES key with RSA, then uses AES-GCM for the message body. Pretty clever, right?"
        ]
        return random.choice(responses)

    if any(k in text for k in ['test', 'challenge', 'try', 'practice', 'demo']):
        responses = [
            "Challenge accepted! Your message was properly encrypted and decrypted. You've passed this round of the PGP practice challenge!",
            "Test received loud and clear. If you can read this, it means you successfully decrypted my response. Well done!",
            "Practice makes perfect! You clearly understand how to use PGP. Keep encrypting everything you send."
        ]
        return random.choice(responses)

    if any(k in text for k in ['pgp', 'encrypt', 'crypto', 'rsa', 'security', 'cipher', 'decrypt']):
        responses = [
            "Absolutely! Cryptographic security ensures only the intended recipient can read a message. You're proving you understand that now.",
            "Security through encryption is the foundation of private communication. Every encrypted message is a win for digital privacy.",
            "PGP remains one of the most trusted encryption standards. Practicing with it builds skills that protect real-world communications."
        ]
        return random.choice(responses)

    if any(k in text for k in ['nice', 'good', 'great', 'cool', 'awesome', 'thanks', 'thank you', 'amazing']):
        responses = [
            "Thanks! I'm glad you're enjoying the practice. Always remember to verify public keys before trusting them in real scenarios.",
            "Appreciate the kind words! Keep practicing with different key sizes to build real confidence with PGP tools.",
            "You're very welcome! The fact that you're taking time to practice PGP means you're serious about secure communication."
        ]
        return random.choice(responses)

    short = user_text[:40] + ('...' if len(user_text) > 40 else '')
    responses = [
        f"Message received: '{short}'\n\nYour encryption worked perfectly. If you can read this, you've completed a full encrypt-send-decrypt cycle. That's exactly how secure messaging works!",
        "I received your encrypted message and this is my encrypted reply. Notice how the entire conversation is protected? Neither of us had to share a secret key.",
        "Your message arrived safely through the encrypted channel. This practice session is a great way to build confidence before handling sensitive data."
    ]
    return random.choice(responses)


@app.route('/api/practice/send', methods=['POST'])
def practice_send():
    """
    Receive an encrypted message from the user, decrypt it, generate an AI response,
    and optionally encrypt the reply back to the user's saved public key.
    """
    if not CRYPTO_AVAILABLE:
        return jsonify({'error': 'Cryptography not available on this server'}), 503

    data = request.get_json() or {}
    message_block = data.get('message', '').strip()

    if not message_block:
        return jsonify({'error': 'Message is required'}), 400

    # ---- CHALLENGE FAILED: plaintext detected ----
    if '-----BEGIN PGP' not in message_block:
        return jsonify({
            'status': 'failed',
            'reason': 'plaintext',
            'message': (
                'CHALLENGE FAILED!\n\n'
                'You sent unencrypted text. The practice challenge requires you to encrypt your message '
                'with the practice partner\'s public key before sending.\n\n'
                'Steps to pass:\n'
                '1. Copy the practice public key displayed on this page\n'
                '2. Go to the Encrypt / Decrypt page\n'
                '3. Paste the practice key, type your message, and encrypt it\n'
                '4. Paste the resulting PGP MESSAGE block here and try again'
            )
        }), 400

    _pub, priv_block = get_practice_keys()
    if not priv_block:
        return jsonify({'error': 'Practice keypair not initialized'}), 500

    # ---- Decrypt the user's message ----
    try:
        b64_pem = parse_pgp_block(priv_block, 'PRIVATE KEY BLOCK')
        pem_bytes = base64.b64decode(b64_pem)
        private_key = serialization.load_pem_private_key(pem_bytes, password=None)

        b64_payload = parse_pgp_block(message_block, 'MESSAGE')
        payload = base64.b64decode(b64_payload)

        key_len = int.from_bytes(payload[:2], 'big')
        encrypted_key = payload[2:2+key_len]
        nonce = payload[2+key_len:2+key_len+12]
        ciphertext = payload[2+key_len+12:]

        aes_key = private_key.decrypt(
            encrypted_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

        aesgcm = AESGCM(aes_key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None).decode('utf-8')
    except Exception as e:
        logger.exception("Practice decryption failed")
        return jsonify({
            'status': 'failed',
            'reason': 'decrypt_error',
            'message': (
                'Could not decrypt your message.\n\n'
                'Make sure you:\n'
                '1. Used the correct practice partner public key to encrypt\n'
                '2. Copied the entire PGP MESSAGE block (including -----BEGIN/END markers)\n'
                '3. The message format is valid'
            )
        }), 400

    # ---- Generate contextual AI response ----
    ai_response = generate_ai_response(plaintext)

    # ---- Try to encrypt response back to user's public key ----
    user_encrypted = None
    user_has_key = False
    if 'user_id' in session:
        conn = db_connect()
        c = conn.cursor()
        db_execute(c, 'SELECT public_key FROM users WHERE id = ?', (session['user_id'],))
        row = c.fetchone()
        conn.close()
        if row and row[0]:
            user_has_key = True
            user_public_key = row[0]
            try:
                b64_pem_user = parse_pgp_block(user_public_key, 'PUBLIC KEY BLOCK')
                pem_bytes_user = base64.b64decode(b64_pem_user)
                user_pubkey = serialization.load_pem_public_key(pem_bytes_user)

                aes_key = secrets.token_bytes(32)
                nonce = secrets.token_bytes(12)
                aesgcm = AESGCM(aes_key)
                ciphertext = aesgcm.encrypt(nonce, ai_response.encode('utf-8'), None)

                encrypted_key = user_pubkey.encrypt(
                    aes_key,
                    padding.OAEP(
                        mgf=padding.MGF1(algorithm=hashes.SHA256()),
                        algorithm=hashes.SHA256(),
                        label=None
                    )
                )

                key_len = len(encrypted_key)
                payload = key_len.to_bytes(2, 'big') + encrypted_key + nonce + ciphertext
                payload_b64 = base64.b64encode(payload).decode()

                user_encrypted = make_pgp_block('MESSAGE', payload_b64, 'Practice Partner Encrypted Reply')
            except Exception as e:
                logger.warning("Could not encrypt reply to user's key: %s", e)

    tip = None
    if user_encrypted is None and 'user_id' in session:
        if user_has_key:
            tip = "I couldn't encrypt my reply back to your saved key (the format may be unsupported). But here's the plaintext response:"
        else:
            tip = "Tip: Save your public key in your Profile page so I can encrypt my replies back to you!"
    elif 'user_id' not in session:
        tip = "Tip: Log in and save your public key in your Profile so I can encrypt my replies back to you!"

    return jsonify({
        'status': 'success',
        'decrypted': plaintext,
        'response': ai_response,
        'encrypted_response': user_encrypted,
        'tip': tip
    }), 200


# ============== Health / Status ==============

@app.route('/api/status', methods=['GET'])
def status():
    return jsonify({'status': 'ok', 'crypto_available': CRYPTO_AVAILABLE}), 200


# ============== Encryption Utilities ==============

def parse_pgp_block(block_text, block_type):
    begin_marker = f'-----BEGIN PGP {block_type}-----'
    end_marker = f'-----END PGP {block_type}-----'

    begin_idx = block_text.find(begin_marker)
    end_idx = block_text.find(end_marker)

    if begin_idx == -1 or end_idx == -1 or end_idx < begin_idx:
        raise ValueError(f'Invalid PGP {block_type} block: missing or malformed markers')

    content = block_text[begin_idx + len(begin_marker):end_idx]
    lines = content.strip().split('\n')
    b64_lines = []
    in_body = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            in_body = True
            continue
        if stripped.startswith('Version:') or stripped.startswith('Comment:'):
            continue
        in_body = True
        if in_body:
            b64_lines.append(stripped)
    result = ''.join(b64_lines)
    if not result:
        raise ValueError(f'Invalid PGP {block_type} block: no base64 content found')
    return result


def make_pgp_block(block_type, base64_content, comment=''):
    header = f'-----BEGIN PGP {block_type}-----\nVersion: PGP Encryption Tool 1.0'
    if comment:
        header += f'\nComment: {comment}'
    lines = []
    for i in range(0, len(base64_content), 64):
        lines.append(base64_content[i:i+64])
    body = '\n'.join(lines)
    footer = f'-----END PGP {block_type}-----'
    return f'{header}\n\n{body}\n{footer}'


# ============== Key Generation ==============

@app.route('/api/generate-keys', methods=['POST'])
def generate_keys():
    if not CRYPTO_AVAILABLE:
        return jsonify({
            'error': 'The cryptography module is not available on this server. '
                     'Please redeploy after ensuring "cryptography" is in requirements.txt.'
        }), 503

    data = request.get_json() or {}
    key_size = data.get('key_size', 4096)

    if key_size not in (2048, 4096):
        return jsonify({'error': 'Key size must be 2048 or 4096'}), 400

    try:
        logger.info("Generating RSA-%d key pair...", key_size)
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=key_size
        )
        public_key = private_key.public_key()

        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')

        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')

        public_b64 = base64.b64encode(public_pem.encode()).decode()
        private_b64 = base64.b64encode(private_pem.encode()).decode()

        public_block = make_pgp_block('PUBLIC KEY BLOCK', public_b64, f'RSA-{key_size}')
        private_block = make_pgp_block('PRIVATE KEY BLOCK', private_b64, f'RSA-{key_size}')

        logger.info("RSA-%d key pair generated successfully", key_size)
        return jsonify({
            'public_key': public_block,
            'private_key': private_block,
            'key_size': key_size
        }), 200
    except Exception as e:
        logger.exception("Key generation failed")
        return jsonify({'error': f'Key generation failed: {str(e)}'}), 500


# ============== Encrypt ==============

@app.route('/api/encrypt', methods=['POST'])
def encrypt_message():
    if not CRYPTO_AVAILABLE:
        return jsonify({
            'error': 'The cryptography module is not available on this server.'
        }), 503

    data = request.get_json() or {}
    public_key_block = data.get('public_key', '')
    message = data.get('message', '')
    key_size = data.get('key_size', 4096)

    if not public_key_block or not message:
        return jsonify({'error': 'Public key and message are required'}), 400

    try:
        logger.info("Encrypting message with RSA-%d...", key_size)
        b64_pem = parse_pgp_block(public_key_block, 'PUBLIC KEY BLOCK')
        pem_bytes = base64.b64decode(b64_pem)
        public_key = serialization.load_pem_public_key(pem_bytes)

        aes_key = secrets.token_bytes(32)
        nonce = secrets.token_bytes(12)

        aesgcm = AESGCM(aes_key)
        ciphertext = aesgcm.encrypt(nonce, message.encode('utf-8'), None)

        encrypted_key = public_key.encrypt(
            aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

        key_len = len(encrypted_key)
        payload = key_len.to_bytes(2, 'big') + encrypted_key + nonce + ciphertext
        payload_b64 = base64.b64encode(payload).decode()

        encrypted_block = make_pgp_block('MESSAGE', payload_b64, f'RSA-{key_size} Encrypted')

        logger.info("Message encrypted successfully")
        return jsonify({
            'encrypted': encrypted_block,
            'key_size': key_size
        }), 200
    except Exception as e:
        logger.exception("Encryption failed")
        return jsonify({'error': f'Encryption failed: {str(e)}'}), 500


# ============== Decrypt ==============

@app.route('/api/decrypt', methods=['POST'])
def decrypt_message():
    if not CRYPTO_AVAILABLE:
        return jsonify({
            'error': 'The cryptography module is not available on this server.'
        }), 503

    data = request.get_json() or {}
    private_key_block = data.get('private_key', '')
    encrypted_block = data.get('encrypted_message', '')

    if not private_key_block or not encrypted_block:
        return jsonify({'error': 'Private key and encrypted message are required'}), 400

    try:
        logger.info("Decrypting message...")
        b64_pem = parse_pgp_block(private_key_block, 'PRIVATE KEY BLOCK')
        pem_bytes = base64.b64decode(b64_pem)
        private_key = serialization.load_pem_private_key(pem_bytes, password=None)

        b64_payload = parse_pgp_block(encrypted_block, 'MESSAGE')
        payload = base64.b64decode(b64_payload)

        key_len = int.from_bytes(payload[:2], 'big')
        encrypted_key = payload[2:2+key_len]
        nonce = payload[2+key_len:2+key_len+12]
        ciphertext = payload[2+key_len+12:]

        aes_key = private_key.decrypt(
            encrypted_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )

        aesgcm = AESGCM(aes_key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None).decode('utf-8')

        logger.info("Message decrypted successfully")
        return jsonify({'decrypted': plaintext}), 200
    except Exception as e:
        logger.exception("Decryption failed")
        return jsonify({'error': f'Decryption failed: {str(e)}'}), 500


# ============== Private Key Routes ==============

@app.route('/api/private-key', methods=['GET'])
def get_private_key():
    """Return the user's stored encrypted private key payload (opaque blob)."""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    conn = db_connect()
    c = conn.cursor()
    db_execute(c, 'SELECT encrypted_private_key FROM users WHERE id = ?', (session['user_id'],))
    row = c.fetchone()
    conn.close()

    if not row or not row[0]:
        return jsonify({'encrypted_private_key': None}), 200

    return jsonify({'encrypted_private_key': row[0]}), 200


@app.route('/api/private-key', methods=['POST'])
def save_private_key():
    """Save an encrypted private key payload (opaque JSON blob) for the user."""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json() or {}
    payload = data.get('encrypted_private_key')
    if payload is None:
        return jsonify({'error': 'encrypted_private_key is required'}), 400

    conn = db_connect()
    c = conn.cursor()
    db_execute(c, 'UPDATE users SET encrypted_private_key = ? WHERE id = ?',
               (payload, session['user_id']))
    conn.commit()
    conn.close()

    return jsonify({'message': 'Private key saved'}), 200


@app.route('/api/private-key', methods=['DELETE'])
def delete_private_key():
    """Remove the stored encrypted private key for the user."""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    conn = db_connect()
    c = conn.cursor()
    db_execute(c, 'UPDATE users SET encrypted_private_key = NULL WHERE id = ?',
               (session['user_id'],))
    conn.commit()
    conn.close()

    return jsonify({'message': 'Private key removed'}), 200


init_practice_keys()


# ============== Main ==============

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
