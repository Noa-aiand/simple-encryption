from flask import Flask, send_from_directory, request, session, jsonify, make_response
import os
import sys
import sqlite3
import base64
import secrets
import logging
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
        # Convert sqlite-style ? placeholders to psycopg2 %s
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
        # PostgreSQL: enable UUID extension if needed and use SERIAL
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

    # Migration: add public_key column if missing.
    # PostgreSQL: try to add and ignore "already exists" errors.
    # SQLite: same approach works via PRAGMA, but try/except is simpler.
    try:
        c.execute("ALTER TABLE users ADD COLUMN public_key TEXT")
        conn.commit()
        logger.info("Migrated DB: added public_key column")
    except Exception:
        # Column likely already exists or table wasn't created yet
        conn.rollback()

    # Create saved_keys table
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

    conn.close()


init_db()


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


# ============== Main ==============

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
