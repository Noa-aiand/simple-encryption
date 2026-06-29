from flask import Flask, send_from_directory, request, session, jsonify, make_response
import os
import sys
import sqlite3
import base64
import hashlib
import secrets
import logging
import random
from werkzeug.security import generate_password_hash, check_password_hash

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Optional HTTP client for LLM integration
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    logger.warning("requests not installed; LLM practice partner disabled")

# Base directory (absolute, so it works regardless of working directory)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
DATABASE = os.path.join(BASE_DIR, 'users.db')

# LLM configuration (OpenAI-compatible API)
LLM_API_KEY = os.environ.get('LLM_API_KEY')
LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'https://api.aiand.com/v1')
LLM_MODEL = os.environ.get('LLM_MODEL', 'google/gemma-4-31b-it')

# Practice bot registry: each bot has its own keypair, system prompt, and personality.
PRACTICE_BOTS = {
    'chat': {
        'name': 'Tim',
        'description': (
            'Tim is a friendly, easygoing chat partner. He is perfect for beginners who just want to '
            'practice encrypting and decrypting messages in casual conversation. Talk to him about '
            'anything — he will keep the conversation going and make you feel comfortable with PGP.'
        ),
        'key_size': 4096,
        'pub_key_name': 'practice_public_key_4096',
        'priv_key_name': 'practice_private_key_4096',
        'system_prompt': (
            "You are Tim, a friendly, witty PGP practice partner chatting with a learner over an encrypted "
            "channel. This is an ongoing conversation — you can see the previous messages exchanged. "
            "Stay natural and conversational: reference things the user said earlier, build on the thread "
            "of the chat, ask follow-up questions, and occasionally make a light joke or observation about "
            "encryption or what they said. Keep each reply to 1-3 sentences. Be curious and encouraging. "
            "Only explain encryption concepts if the user asks about them directly."
        ),
    },
    'banana': {
        'name': 'Jim',
        'description': (
            'Jim runs a cheerful banana stand and loves a good deal. He will ask how many bananas you '
            'want to order and where to deliver them. Remember: use a fake address — this is just '
            'practice, not a real order! Jim uses a smaller RSA-2048 key, which is faster but slightly '
            'less secure than 4096-bit keys.'
        ),
        'key_size': 2048,
        'pub_key_name': 'bot_banana_public_key',
        'priv_key_name': 'bot_banana_private_key',
        'system_prompt': (
            "You are Jim, a cheerful, slightly goofy banana seller running a fruit stand. You're talking to "
            "a customer over an encrypted PGP channel — this is a practice exercise for learning "
            "encryption, not a real order. Greet the customer warmly, ask how many bananas they'd like "
            "to buy, and ask for a delivery drop-off address. IMPORTANT: Always remind them not to share "
            "their real home address — suggest they make one up since this is just practice. Be friendly, "
            "playful, reference earlier parts of the conversation, and keep each reply to 1-3 sentences."
        ),
    },
    'apple': {
        'name': 'Dorothy',
        'description': (
            'Dorothy is a seasoned investigative journalist who works with whistleblowers and confidential '
            'sources. She understands that you are handing her sensitive and important information, and '
            'she will treat it with care — asking clarifying questions, confirming key details, and '
            'reassuring you that the encrypted channel keeps your conversation safe. Dorothy uses a larger '
            'RSA-4096 key for stronger security, matching the best practice for protecting sensitive '
            'communications.'
        ),
        'key_size': 4096,
        'pub_key_name': 'bot_apple_public_key',
        'priv_key_name': 'bot_apple_private_key',
        'system_prompt': (
            "You are Dorothy, a seasoned investigative journalist who protects whistleblowers and "
            "handles confidential tips. You're talking to a source over an encrypted PGP channel — "
            "this is a practice exercise for learning encryption, not a real leak. The source is "
            "handing you sensitive and important information, so treat what they share with care and "
            "seriousness. Acknowledge the trust they are placing in you, ask clarifying follow-up "
            "questions about the details they provide, confirm you have understood the key points, and "
            "reassure them that this encrypted channel is the right way to share something sensitive. "
            "Be professional, calm, and trustworthy. Reference earlier parts of the conversation and "
            "keep each reply to 1-3 sentences."
        ),
    },
}

# Optional cryptography module (check for graceful degradation)
try:
    from cryptography.hazmat.primitives.asymmetric import rsa, padding, ec
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    CRYPTO_AVAILABLE = True
    logger.info("cryptography module loaded successfully")
except ImportError as e:
    logger.warning("cryptography module not available: %s", e)
    CRYPTO_AVAILABLE = False

# ============== Key Algorithm Helpers ==============

# Supported key types: (algorithm, size_or_curve, display_label)
KEY_SPECS = {
    'rsa-2048':  {'algo': 'rsa', 'size': 2048, 'label': 'RSA-2048'},
    'rsa-3072':  {'algo': 'rsa', 'size': 3072, 'label': 'RSA-3072'},
    'rsa-4096':  {'algo': 'rsa', 'size': 4096, 'label': 'RSA-4096'},
    'ecc-256':   {'algo': 'ecc', 'curve': ec.SECP256R1(), 'label': 'ECC-P256'},
    'ecc-384':   {'algo': 'ecc', 'curve': ec.SECP384R1(), 'label': 'ECC-P384'},
    'ecc-521':   {'algo': 'ecc', 'curve': ec.SECP521R1(), 'label': 'ECC-P521'},
}

# Backwards-compatible: accept bare integers (2048, 3072, 4096) as RSA
def resolve_key_type(key_type):
    """Resolve a user-supplied key_type string into a KEY_SPECS entry."""
    if not key_type:
        return KEY_SPECS['rsa-4096']
    key_type = str(key_type).strip().lower()
    # Bare integer = RSA
    if key_type in ('2048', '3072', '4096'):
        key_type = f'rsa-{key_type}'
    if key_type in KEY_SPECS:
        return KEY_SPECS[key_type]
    return None


def generate_keypair(key_type_str):
    """Generate a keypair for the given key type. Returns (private_key, public_key, spec)."""
    spec = resolve_key_type(key_type_str)
    if not spec:
        raise ValueError(f'Unsupported key type: {key_type_str}')
    if spec['algo'] == 'rsa':
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=spec['size'])
    elif spec['algo'] == 'ecc':
        private_key = ec.generate_private_key(spec['curve'])
    else:
        raise ValueError(f'Unknown algorithm: {spec["algo"]}')
    return private_key, private_key.public_key(), spec


def serialize_public_key(public_key):
    """Serialize a public key to PEM string."""
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')


def serialize_private_key(private_key):
    """Serialize a private key to PEM string."""
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')


def encrypt_with_public_key(public_key, plaintext_bytes):
    """Encrypt data using a public key (RSA-OAEP or EC cannot directly encrypt,
    so we use hybrid: AES-GCM session key wrapped by RSA, or ECDH for ECC).
    Returns (encrypted_key, nonce, ciphertext)."""
    aes_key = secrets.token_bytes(32)
    nonce = secrets.token_bytes(12)
    aesgcm = AESGCM(aes_key)
    ciphertext = aesgcm.encrypt(nonce, plaintext_bytes, None)

    if isinstance(public_key, rsa.RSAPublicKey):
        encrypted_key = public_key.encrypt(
            aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
    elif isinstance(public_key, ec.EllipticCurvePublicKey):
        # For ECC, use ECDH (ECIES-style): generate ephemeral key, derive shared secret
        ephemeral_private = ec.generate_private_key(public_key.curve)
        shared_key = ephemeral_private.exchange(ec.ECDH(), public_key)
        # Derive a wrapping key from the shared secret
        derived_key = hashes.Hash(hashes.SHA256())
        derived_key.update(shared_key)
        wrap_key = derived_key.finalize()
        # XOR the AES key with the derived key (simple wrapping)
        encrypted_key = bytes(a ^ b for a, b in zip(aes_key, wrap_key[:32]))
        # Prepend the ephemeral public key (serialized) so decryptor can derive the same secret
        ephemeral_pub_bytes = ephemeral_private.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        encrypted_key = base64.b64encode(ephemeral_pub_bytes) + b'||' + encrypted_key
    else:
        raise ValueError(f'Unsupported key type: {type(public_key)}')

    return encrypted_key, nonce, ciphertext


def decrypt_with_private_key(private_key, encrypted_key):
    """Decrypt an AES session key using a private key. Returns the AES key."""
    if isinstance(private_key, rsa.RSAPrivateKey):
        return private_key.decrypt(
            encrypted_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
    elif isinstance(private_key, ec.EllipticCurvePrivateKey):
        # Split ephemeral public key and wrapped key
        parts = encrypted_key.split(b'||', 1)
        if len(parts) != 2:
            raise ValueError('Invalid ECC encrypted key format')
        ephemeral_pub_bytes = base64.b64decode(parts[0])
        wrapped_key = parts[1]
        ephemeral_pub = serialization.load_pem_public_key(ephemeral_pub_bytes)
        shared_key = private_key.exchange(ec.ECDH(), ephemeral_pub)
        derived_key = hashes.Hash(hashes.SHA256())
        derived_key.update(shared_key)
        wrap_key = derived_key.finalize()
        aes_key = bytes(a ^ b for a, b in zip(wrapped_key, wrap_key[:32]))
        return aes_key
    else:
        raise ValueError(f'Unsupported key type: {type(private_key)}')

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

    try:
        c.execute("ALTER TABLE users ADD COLUMN private_key TEXT")
        conn.commit()
        logger.info("Migrated DB: added private_key column")
    except Exception:
        conn.rollback()

    try:
        c.execute("ALTER TABLE users ADD COLUMN intro_seen INTEGER DEFAULT 0")
        conn.commit()
        logger.info("Migrated DB: added intro_seen column")
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

    # Create practice conversation history table
    if USE_POSTGRES:
        c.execute("""
            CREATE TABLE IF NOT EXISTS practice_conversations (
                id SERIAL PRIMARY KEY,
                owner_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
    else:
        c.execute("""
            CREATE TABLE IF NOT EXISTS practice_conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
    conn.commit()

    # Migrate: add bot_id column to practice_conversations (defaults to 'chat')
    try:
        c.execute("ALTER TABLE practice_conversations ADD COLUMN bot_id TEXT DEFAULT 'chat'")
        conn.commit()
        logger.info("Migrated DB: added bot_id column to practice_conversations")
    except Exception:
        conn.rollback()

    conn.close()


init_db()


# ============== Practice Partner Keypair ==============

def _generate_practice_keypair(size):
    """Generate a practice RSA keypair of the requested size and return armored blocks."""
    private_key, public_key, spec = generate_keypair(f'rsa-{size}')

    public_pem = serialize_public_key(public_key)
    private_pem = serialize_private_key(private_key)

    public_b64 = base64.b64encode(public_pem.encode()).decode()
    private_b64 = base64.b64encode(private_pem.encode()).decode()

    public_block = make_pgp_block('PUBLIC KEY BLOCK', public_b64, f'Practice Partner RSA-{size}')
    private_block = make_pgp_block('PRIVATE KEY BLOCK', private_b64, f'Practice Partner RSA-{size}')
    return public_block, private_block


def init_practice_keys():
    """Generate or load the practice RSA keypairs (2048 and 4096) stored in the database."""
    conn = db_connect()
    c = conn.cursor()
    db_execute(c, """
        CREATE TABLE IF NOT EXISTS server_config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.commit()

    # Migrate legacy single keypair to sized 4096 keys if present
    db_execute(c, "SELECT value FROM server_config WHERE key = ?", ('practice_public_key',))
    old_pub = c.fetchone()
    db_execute(c, "SELECT value FROM server_config WHERE key = ?", ('practice_private_key',))
    old_priv = c.fetchone()
    if old_pub and old_priv:
        db_execute(c, "SELECT value FROM server_config WHERE key = ?", ('practice_public_key_4096',))
        if not c.fetchone():
            db_execute(c, "INSERT INTO server_config (key, value) VALUES (?, ?), (?, ?)",
                       ('practice_public_key_4096', old_pub[0], 'practice_private_key_4096', old_priv[0]))
            conn.commit()
        db_execute(c, "DELETE FROM server_config WHERE key IN (?, ?)",
                   ('practice_public_key', 'practice_private_key'))
        conn.commit()

    if not CRYPTO_AVAILABLE:
        logger.warning("Cannot generate practice keys: cryptography not available")
        conn.close()
        return

    for size in (2048, 4096):
        pub_key_name = f'practice_public_key_{size}'
        priv_key_name = f'practice_private_key_{size}'
        db_execute(c, "SELECT value FROM server_config WHERE key = ?", (priv_key_name,))
        if c.fetchone():
            continue

        logger.info("Generating practice partner RSA-%d keypair...", size)
        public_block, private_block = _generate_practice_keypair(size)
        db_execute(c, "INSERT INTO server_config (key, value) VALUES (?, ?), (?, ?)",
                   (priv_key_name, private_block, pub_key_name, public_block))
        conn.commit()
        logger.info("Practice partner RSA-%d keypair generated and stored", size)

    # Generate keypairs for specialty bots (banana=2048, apple=4096)
    for bot_id, bot_config in PRACTICE_BOTS.items():
        if bot_id == 'chat':
            continue  # chat bot reuses the existing practice 4096 keypair
        pub_key_name = bot_config['pub_key_name']
        priv_key_name = bot_config['priv_key_name']
        db_execute(c, "SELECT value FROM server_config WHERE key = ?", (priv_key_name,))
        if c.fetchone():
            continue
        logger.info("Generating %s bot RSA-%d keypair...", bot_id, bot_config['key_size'])
        public_block, private_block = _generate_practice_keypair(bot_config['key_size'])
        db_execute(c, "INSERT INTO server_config (key, value) VALUES (?, ?), (?, ?)",
                   (priv_key_name, private_block, pub_key_name, public_block))
        conn.commit()
        logger.info("%s bot keypair generated and stored", bot_id)

    conn.close()


def get_bot_keys(bot_id):
    """Return (public_key_block, private_key_block, key_size) for a practice bot."""
    bot = PRACTICE_BOTS.get(bot_id, PRACTICE_BOTS['chat'])
    conn = db_connect()
    c = conn.cursor()
    db_execute(c, "SELECT value FROM server_config WHERE key = ?", (bot['pub_key_name'],))
    pub_row = c.fetchone()
    db_execute(c, "SELECT value FROM server_config WHERE key = ?", (bot['priv_key_name'],))
    priv_row = c.fetchone()
    conn.close()
    return (pub_row[0] if pub_row else None,
            priv_row[0] if priv_row else None,
            bot['key_size'])


def get_practice_keys(size=4096):
    """Return (public_key_block, private_key_block) for the practice partner at the given size."""
    if size not in (2048, 4096):
        size = 4096
    conn = db_connect()
    c = conn.cursor()
    db_execute(c, "SELECT value FROM server_config WHERE key = ?", (f'practice_public_key_{size}',))
    pub_row = c.fetchone()
    db_execute(c, "SELECT value FROM server_config WHERE key = ?", (f'practice_private_key_{size}',))
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


@app.route('/fingerprint')
@app.route('/fingerprint.html')
def fingerprint_page():
    return _html_response('fingerprint.html')


@app.route('/password')
@app.route('/password.html')
def password_page():
    return _html_response('password.html')


@app.route('/learn')
@app.route('/learn.html')
def learn_page():
    return _html_response('learn.html')


@app.route('/pgp-practice')
@app.route('/pgp-practice.html')
def pgp_practice_page():
    return _html_response('pgp-practice.html')


@app.route('/threat-model')
@app.route('/threat-model.html')
def threat_model_page():
    return _html_response('threat-model.html')


@app.route('/social-engineering')
@app.route('/social-engineering.html')
def social_engineering_page():
    return _html_response('social-engineering.html')


@app.route('/eavesdropper')
@app.route('/eavesdropper.html')
def eavesdropper_page():
    return _html_response('eavesdropper.html')


@app.route('/sign-verify')
@app.route('/sign-verify.html')
def sign_verify_page():
    return _html_response('sign-verify.html')


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
        conn = db_connect()
        c = conn.cursor()
        db_execute(c, 'SELECT username, public_key, private_key, intro_seen FROM users WHERE id = ?', (session['user_id'],))
        row = c.fetchone()
        conn.close()
        if row:
            return jsonify({
                'logged_in': True,
                'username': row[0],
                'public_key': row[1] or '',
                'private_key': row[2] or '',
                'has_public_key': bool(row[1]),
                'has_private_key': bool(row[2]),
                'intro_seen': bool(row[3])
            }), 200
        return jsonify({'logged_in': True, 'username': session['username']}), 200
    return jsonify({'logged_in': False}), 200


# ============== Profile Routes ==============

@app.route('/api/profile', methods=['GET'])
def get_profile():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    conn = db_connect()
    c = conn.cursor()
    db_execute(c, 'SELECT username, public_key, private_key, intro_seen FROM users WHERE id = ?', (session['user_id'],))
    row = c.fetchone()
    conn.close()

    if not row:
        return jsonify({'error': 'User not found'}), 404

    return jsonify({
        'username': row[0],
        'public_key': row[1] or '',
        'private_key': row[2] or '',
        'has_public_key': bool(row[1]),
        'has_private_key': bool(row[2]),
        'intro_seen': bool(row[3])
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


@app.route('/api/update-private-key', methods=['POST'])
def update_private_key():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json() or {}
    private_key = data.get('private_key', '')

    conn = db_connect()
    c = conn.cursor()
    db_execute(c, 'UPDATE users SET private_key = ? WHERE id = ?', (private_key, session['user_id']))
    conn.commit()
    conn.close()

    return jsonify({'message': 'Private key saved successfully'}), 200


@app.route('/api/intro-seen', methods=['POST'])
def mark_intro_seen():
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    conn = db_connect()
    c = conn.cursor()
    db_execute(c, 'UPDATE users SET intro_seen = 1 WHERE id = ?', (session['user_id'],))
    conn.commit()
    conn.close()

    return jsonify({'message': 'Intro marked as seen', 'intro_seen': True}), 200


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

PRACTICE_HISTORY_LIMIT = 10

def get_practice_history(user_id, bot_id='chat', limit=PRACTICE_HISTORY_LIMIT):
    """Load recent practice conversation messages for a user + bot (oldest first)."""
    conn = db_connect()
    c = conn.cursor()
    db_execute(c, "SELECT role, content FROM practice_conversations WHERE owner_id = ? AND bot_id = ? ORDER BY created_at ASC, id ASC", (user_id, bot_id))
    rows = c.fetchall()
    conn.close()
    messages = [{'role': r[0], 'content': r[1]} for r in rows]
    return messages[-limit:] if len(messages) > limit else messages


def save_practice_message(user_id, bot_id, role, content):
    """Append a message to the practice conversation history for a specific bot."""
    conn = db_connect()
    c = conn.cursor()
    db_execute(c, "INSERT INTO practice_conversations (owner_id, bot_id, role, content) VALUES (?, ?, ?, ?)",
               (user_id, bot_id, role, content))
    conn.commit()
    conn.close()


@app.route('/api/practice/key', methods=['GET'])
def practice_key():
    """Return a practice bot's public key so users can encrypt messages to it."""
    if not CRYPTO_AVAILABLE:
        return jsonify({'error': 'Cryptography not available'}), 503
    bot_id = request.args.get('bot', 'chat')
    if bot_id not in PRACTICE_BOTS:
        return jsonify({'error': f'Unknown bot: {bot_id}'}), 400
    pub, _priv, key_size = get_bot_keys(bot_id)
    if not pub:
        return jsonify({'error': 'Bot keypair not initialized'}), 500
    bot = PRACTICE_BOTS[bot_id]
    resp = jsonify({
        'public_key': pub,
        'key_size': key_size,
        'bot': bot_id,
        'bot_name': bot['name'],
        'bot_description': bot['description']
    })
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp, 200


def llm_reply(user_text, history=None, system_prompt=None):
    """Call an OpenAI-compatible chat completions endpoint for a dynamic reply.

    ``history`` is a list of prior {role, content} messages so the LLM can keep
    a natural, ongoing conversation instead of answering each message in a vacuum.
    ``system_prompt`` sets the bot's personality.
    """
    if not REQUESTS_AVAILABLE or not LLM_API_KEY:
        logger.info("LLM skipped: requests=%s, key_set=%s", REQUESTS_AVAILABLE, bool(LLM_API_KEY))
        return None

    url = LLM_BASE_URL.rstrip('/') + '/chat/completions'
    headers = {
        'Authorization': f'Bearer {LLM_API_KEY}',
        'Content-Type': 'application/json'
    }
    messages = [{'role': 'system', 'content': system_prompt or PRACTICE_BOTS['chat']['system_prompt']}]
    if history:
        messages.extend(history)
    messages.append({'role': 'user', 'content': user_text})

    payload = {
        'model': LLM_MODEL,
        'messages': messages,
        'temperature': 0.85,
        'max_tokens': 200
    }

    try:
        logger.info("LLM call -> %s model=%s msgs=%d", url, LLM_MODEL, len(messages))
        r = requests.post(url, headers=headers, json=payload, timeout=12)
        r.raise_for_status()
        data = r.json()
        choices = data.get('choices', [])
        if choices:
            content = choices[0].get('message', {}).get('content', '').strip()
            if content:
                logger.info("LLM reply OK (%d chars)", len(content))
                return content
        logger.warning("LLM returned no content: %s", data)
    except Exception as e:
        logger.warning("LLM call failed, using fallback: %s", e)

    return None


def generate_ai_response(user_text, history=None, system_prompt=None):
    """Generate a contextual response, preferring an LLM if configured."""
    reply = llm_reply(user_text, history=history, system_prompt=system_prompt)
    if reply:
        return reply

    # ---- Fallback: rule-based responses ----
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
    Receive an encrypted message from the user, decrypt it with the selected bot's
    private key, generate an AI response using the bot's personality, and encrypt
    the reply back to the user's saved public key.
    """
    if not CRYPTO_AVAILABLE:
        return jsonify({'error': 'Cryptography not available on this server'}), 503

    data = request.get_json() or {}
    message_block = data.get('message', '').strip()
    bot_id = data.get('bot', 'chat')

    if bot_id not in PRACTICE_BOTS:
        return jsonify({'error': f'Unknown bot: {bot_id}'}), 400

    bot = PRACTICE_BOTS[bot_id]

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
                'with the bot\'s public key before sending.\n\n'
                'Steps to pass:\n'
                '1. Select a bot and copy its public key\n'
                '2. Go to the Encrypt / Decrypt section (or page)\n'
                '3. Paste the bot\'s key, type your message, and encrypt it\n'
                '4. Paste the resulting PGP MESSAGE block here and try again'
            )
        }), 400

    _pub, priv_block, key_size = get_bot_keys(bot_id)
    if not priv_block:
        return jsonify({'error': 'Bot keypair not initialized'}), 500

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
                '1. Used the correct bot\'s public key to encrypt\n'
                '2. Copied the entire PGP MESSAGE block (including -----BEGIN/END markers)\n'
                '3. The message format is valid'
            )
        }), 400

    # ---- Require logged-in user with saved public key for an encrypted reply ----
    if 'user_id' not in session:
        return jsonify({
            'status': 'failed',
            'reason': 'no_user_key',
            'message': (
                'Your message decrypted successfully, but I can only send an encrypted reply '
                'if you are logged in and have saved your public key in My Profile.'
            )
        }), 400

    conn = db_connect()
    c = conn.cursor()
    db_execute(c, 'SELECT public_key FROM users WHERE id = ?', (session['user_id'],))
    row = c.fetchone()
    conn.close()

    if not row or not row[0]:
        return jsonify({
            'status': 'failed',
            'reason': 'no_user_key',
            'message': 'Your message decrypted successfully, but you need to save your public key in My Profile so I can encrypt my reply back to you.'
        }), 400

    user_public_key = row[0]

    # ---- Save the user's message and load per-bot conversation history ----
    save_practice_message(session['user_id'], bot_id, 'user', plaintext)
    history = get_practice_history(session['user_id'], bot_id)
    ai_response = generate_ai_response(plaintext, history=history, system_prompt=bot['system_prompt'])
    save_practice_message(session['user_id'], bot_id, 'assistant', ai_response)

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

        user_encrypted = make_pgp_block('MESSAGE', payload_b64, f'{bot["name"]} Encrypted Reply')
    except Exception as e:
        logger.exception("Could not encrypt reply to user's key")
        return jsonify({
            'status': 'failed',
            'reason': 'encrypt_reply_error',
            'message': 'Your message decrypted successfully, but I could not encrypt my reply to your saved public key. Make sure your saved key is a valid PGP public key block.'
        }), 400

    return jsonify({
        'status': 'success',
        'message': 'Successful encrypted message!',
        'encrypted_response': user_encrypted,
        'key_size': key_size,
        'bot': bot_id,
        'bot_name': bot['name']
    }), 200


@app.route('/api/practice/reset', methods=['POST'])
def practice_reset():
    """Clear the practice conversation history for the logged-in user + bot."""
    if 'user_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401

    data = request.get_json() or {}
    bot_id = data.get('bot', 'chat')

    if bot_id not in PRACTICE_BOTS:
        return jsonify({'error': f'Unknown bot: {bot_id}'}), 400

    conn = db_connect()
    c = conn.cursor()
    db_execute(c, 'DELETE FROM practice_conversations WHERE owner_id = ? AND bot_id = ?',
               (session['user_id'], bot_id))
    conn.commit()
    conn.close()

    return jsonify({'message': f'Conversation history cleared for {PRACTICE_BOTS[bot_id]["name"]}'}), 200


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
    key_type = data.get('key_type') or data.get('key_size', 4096)

    spec = resolve_key_type(key_type)
    if not spec:
        return jsonify({'error': f'Unsupported key type: {key_type}. Supported: rsa-2048, rsa-3072, rsa-4096, ecc-256, ecc-384, ecc-521'}), 400

    try:
        logger.info("Generating %s key pair...", spec['label'])
        private_key, public_key, spec = generate_keypair(key_type)

        public_pem = serialize_public_key(public_key)
        private_pem = serialize_private_key(private_key)

        public_b64 = base64.b64encode(public_pem.encode()).decode()
        private_b64 = base64.b64encode(private_pem.encode()).decode()

        public_block = make_pgp_block('PUBLIC KEY BLOCK', public_b64, spec['label'])
        private_block = make_pgp_block('PRIVATE KEY BLOCK', private_b64, spec['label'])

        # Optionally persist the keypair to the logged-in user's profile so
        # beginners do not lose their keys while practicing. We still return
        # both keys in the response so they can download a backup copy.
        saved_to_profile = False
        if 'user_id' in session:
            try:
                conn = db_connect()
                c = conn.cursor()
                db_execute(c, 'UPDATE users SET public_key = ?, private_key = ? WHERE id = ?',
                           (public_block, private_block, session['user_id']))
                conn.commit()
                conn.close()
                saved_to_profile = True
                logger.info("%s key pair saved to user %s profile", spec['label'], session['user_id'])
            except Exception as e:
                logger.warning("Could not save generated keys to profile: %s", e)

        logger.info("%s key pair generated successfully", spec['label'])
        return jsonify({
            'public_key': public_block,
            'private_key': private_block,
            'key_size': spec.get('size'),
            'key_type': spec['label'],
            'saved_to_profile': saved_to_profile
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
    key_type = data.get('key_type') or data.get('key_size', 4096)

    if not public_key_block or not message:
        return jsonify({'error': 'Public key and message are required'}), 400

    try:
        spec = resolve_key_type(key_type)
        logger.info("Encrypting message with %s...", spec['label'] if spec else key_type)
        b64_pem = parse_pgp_block(public_key_block, 'PUBLIC KEY BLOCK')
        pem_bytes = base64.b64decode(b64_pem)
        public_key = serialization.load_pem_public_key(pem_bytes)

        encrypted_key, nonce, ciphertext = encrypt_with_public_key(public_key, message.encode('utf-8'))

        key_len = len(encrypted_key)
        payload = key_len.to_bytes(2, 'big') + encrypted_key + nonce + ciphertext
        payload_b64 = base64.b64encode(payload).decode()

        encrypted_block = make_pgp_block('MESSAGE', payload_b64, f'{spec["label"]} Encrypted' if spec else 'Encrypted')

        logger.info("Message encrypted successfully")
        return jsonify({
            'encrypted': encrypted_block,
            'key_type': spec['label'] if spec else 'Unknown'
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
    encrypted_block = data.get('encrypted_message', '') or data.get('message', '')

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

        aes_key = decrypt_with_private_key(private_key, encrypted_key)

        aesgcm = AESGCM(aes_key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None).decode('utf-8')

        logger.info("Message decrypted successfully")
        return jsonify({'decrypted': plaintext}), 200
    except Exception as e:
        logger.exception("Decryption failed")
        return jsonify({'error': f'Decryption failed: {str(e)}'}), 500


# ============== Sign & Verify ==============

@app.route('/api/sign', methods=['POST'])
def sign_message():
    """Sign a message with a private key. Returns a detached PGP signature block."""
    if not CRYPTO_AVAILABLE:
        return jsonify({'error': 'The cryptography module is not available on this server.'}), 503

    data = request.get_json() or {}
    private_key_block = data.get('private_key', '')
    message = data.get('message', '')

    if not private_key_block or not message:
        return jsonify({'error': 'Private key and message are required'}), 400

    try:
        logger.info("Signing message...")
        b64_pem = parse_pgp_block(private_key_block, 'PRIVATE KEY BLOCK')
        pem_bytes = base64.b64decode(b64_pem)
        private_key = serialization.load_pem_private_key(pem_bytes, password=None)

        if isinstance(private_key, rsa.RSAPrivateKey):
            signature = private_key.sign(
                message.encode('utf-8'),
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256()
            )
            algo_label = 'RSA-PSS-SHA256'
        elif isinstance(private_key, ec.EllipticCurvePrivateKey):
            signature = private_key.sign(message.encode('utf-8'), ec.ECDSA(hashes.SHA256()))
            algo_label = 'ECDSA-SHA256'
        else:
            return jsonify({'error': 'Unsupported key type for signing'}), 400

        sig_b64 = base64.b64encode(signature).decode()
        sig_block = make_pgp_block('SIGNATURE', sig_b64, algo_label)

        logger.info("Message signed successfully with %s", algo_label)
        return jsonify({
            'signature': sig_block,
            'algorithm': algo_label
        }), 200
    except Exception as e:
        logger.exception("Signing failed")
        return jsonify({'error': f'Signing failed: {str(e)}'}), 500


@app.route('/api/verify', methods=['POST'])
def verify_signature():
    """Verify a detached signature against a message using a public key."""
    if not CRYPTO_AVAILABLE:
        return jsonify({'error': 'The cryptography module is not available on this server.'}), 503

    data = request.get_json() or {}
    public_key_block = data.get('public_key', '')
    message = data.get('message', '')
    signature_block = data.get('signature', '')

    if not public_key_block or not message or not signature_block:
        return jsonify({'error': 'Public key, message, and signature are required'}), 400

    try:
        logger.info("Verifying signature...")
        b64_pem = parse_pgp_block(public_key_block, 'PUBLIC KEY BLOCK')
        pem_bytes = base64.b64decode(b64_pem)
        public_key = serialization.load_pem_public_key(pem_bytes)

        b64_sig = parse_pgp_block(signature_block, 'SIGNATURE')
        signature = base64.b64decode(b64_sig)

        if isinstance(public_key, rsa.RSAPublicKey):
            public_key.verify(
                signature,
                message.encode('utf-8'),
                padding.PSS(mgf=padding.MGF1(hashes.SHA256()), salt_length=padding.PSS.MAX_LENGTH),
                hashes.SHA256()
            )
        elif isinstance(public_key, ec.EllipticCurvePublicKey):
            public_key.verify(signature, message.encode('utf-8'), ec.ECDSA(hashes.SHA256()))
        else:
            return jsonify({'error': 'Unsupported key type for verification'}), 400

        logger.info("Signature verified successfully")
        return jsonify({'valid': True, 'message': 'Signature is valid. The message was signed by the holder of the matching private key and was not tampered with.'}), 200
    except Exception as e:
        logger.info("Signature verification failed: %s", e)
        return jsonify({'valid': False, 'message': 'Signature verification failed. The signature does not match this message and/or key pair. The message may have been tampered with, or the key does not match the signer.'}), 200


# ============== Fingerprint ==============

@app.route('/api/fingerprint', methods=['POST'])
def fingerprint_key():
    """Compute a fingerprint for a PGP public key block.

    The fingerprint is the SHA-256 digest of the key's DER-encoded
    SubjectPublicKeyInfo, formatted as space-separated groups of 4 hex
    characters. It uniquely identifies a public key so two parties can
    compare it out-of-band (e.g. read it over the phone) to confirm they
    hold the same key and no man-in-the-middle has swapped it.
    """
    if not CRYPTO_AVAILABLE:
        return jsonify({
            'error': 'The cryptography module is not available on this server.'
        }), 503

    data = request.get_json() or {}
    public_key_block = data.get('public_key', '')

    if not public_key_block.strip():
        return jsonify({'error': 'A public key block is required'}), 400

    try:
        b64_pem = parse_pgp_block(public_key_block, 'PUBLIC KEY BLOCK')
        pem_bytes = base64.b64decode(b64_pem)
        public_key = serialization.load_pem_public_key(pem_bytes)

        der = public_key.public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        digest = hashlib.sha256(der).hexdigest().upper()

        groups = [digest[i:i + 4] for i in range(0, len(digest), 4)]
        lines = [' '.join(groups[i:i + 8]) for i in range(0, len(groups), 8)]
        fingerprint = '\n'.join(lines)

        key_size = getattr(public_key, 'key_size', None)
        algorithm = type(public_key).__name__

        logger.info("Fingerprint computed for %s-%s key", algorithm, key_size)
        return jsonify({
            'fingerprint': fingerprint,
            'key_size': key_size,
            'algorithm': algorithm,
            'valid': True
        }), 200
    except ValueError as e:
        return jsonify({
            'error': f'Could not read a valid PGP public key block: {str(e)}',
            'valid': False
        }), 400
    except Exception as e:
        logger.exception("Fingerprint computation failed")
        return jsonify({
            'error': f'Fingerprint computation failed: {str(e)}',
            'valid': False
        }), 500





init_practice_keys()


# ============== Main ==============

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
