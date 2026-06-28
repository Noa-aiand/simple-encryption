(function() {
    'use strict';

    const MODAL_ID = 'pgpIntroModal';
    const OVERLAY_ID = 'pgpIntroOverlay';

    function injectStyles() {
        if (document.getElementById('pgpIntroStyles')) return;
        const style = document.createElement('style');
        style.id = 'pgpIntroStyles';
        style.textContent = `
            .pgp-intro-overlay {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background: rgba(0, 0, 0, 0.75);
                backdrop-filter: blur(6px);
                z-index: 3000;
                opacity: 0;
                visibility: hidden;
                transition: all 0.35s ease;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }
            .pgp-intro-overlay.active {
                opacity: 1;
                visibility: visible;
            }
            .pgp-intro-modal {
                width: 100%;
                max-width: 720px;
                max-height: 90vh;
                background: linear-gradient(135deg, #ffffff 0%, #e6f2ff 100%);
                border: 2px solid #99ccff;
                border-radius: 20px;
                box-shadow: 0 24px 80px rgba(0, 51, 102, 0.35);
                display: flex;
                flex-direction: column;
                overflow: hidden;
                transform: translateY(20px) scale(0.96);
                transition: transform 0.35s ease;
            }
            .pgp-intro-overlay.active .pgp-intro-modal {
                transform: translateY(0) scale(1);
            }
            .pgp-intro-header {
                padding: 1.6rem 2rem 1rem;
                text-align: center;
                border-bottom: 2px solid #b3d7ff;
            }
            .pgp-intro-header h2 {
                color: #0066cc;
                font-size: 1.6rem;
                margin: 0 0 0.4rem;
                text-transform: uppercase;
                letter-spacing: 2px;
            }
            .pgp-intro-header p {
                color: #003366;
                font-size: 0.95rem;
                margin: 0;
            }
            .pgp-intro-body {
                padding: 1.5rem 2rem;
                overflow-y: auto;
                color: #003366;
                font-size: 0.95rem;
                line-height: 1.65;
            }
            .pgp-intro-body h3 {
                color: #0066cc;
                font-size: 1rem;
                margin: 1.3rem 0 0.5rem;
                display: flex;
                align-items: center;
                gap: 8px;
            }
            .pgp-intro-body h3:first-child {
                margin-top: 0;
            }
            .pgp-intro-body p {
                margin: 0 0 0.8rem;
            }
            .pgp-intro-body ul {
                margin: 0 0 1rem 1.2rem;
                padding: 0;
            }
            .pgp-intro-body li {
                margin-bottom: 0.35rem;
            }
            .pgp-intro-body .warning-box {
                background: #fff4e6;
                border: 2px solid #ffb74d;
                border-radius: 10px;
                padding: 12px 16px;
                color: #8a4b00;
                margin-top: 1rem;
            }
            .pgp-intro-body .warning-box strong {
                color: #cc6600;
            }
            .pgp-intro-body .step-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                gap: 12px;
                margin: 1rem 0;
            }
            .pgp-intro-body .step-card {
                background: #f0f7ff;
                border: 2px solid #b3d7ff;
                border-radius: 10px;
                padding: 14px;
                text-align: center;
            }
            .pgp-intro-body .step-card .emoji {
                font-size: 1.6rem;
                display: block;
                margin-bottom: 6px;
            }
        .pgp-intro-body .step-card .label {
            color: #0066cc;
            font-size: 0.85rem;
            font-weight: 600;
        }
        .pgp-intro-body .step-list {
            margin: 0 0 1rem 1.4rem;
            padding: 0;
            color: #003366;
            font-size: 0.95rem;
            line-height: 1.7;
        }
        .pgp-intro-body .step-list li {
            margin-bottom: 0.35rem;
        }

            .pgp-intro-footer {
                padding: 1rem 2rem 1.6rem;
                display: flex;
                flex-direction: column;
                gap: 12px;
                align-items: center;
                border-top: 2px solid #b3d7ff;
            }
            .pgp-intro-footer label {
                color: #003366;
                font-size: 0.9rem;
                display: flex;
                align-items: center;
                gap: 8px;
                cursor: pointer;
            }
            .pgp-intro-footer input[type="checkbox"] {
                width: 16px;
                height: 16px;
                accent-color: #0066cc;
                cursor: pointer;
            }
            .pgp-intro-btn {
                background: linear-gradient(90deg, #0066cc, #3399ff);
                border: 2px outset #66a3ff;
                border-radius: 10px;
                color: #fff;
                padding: 14px 32px;
                font-size: 1rem;
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 1px;
                cursor: pointer;
                transition: all 0.3s ease;
            }
            .pgp-intro-btn:hover {
                background: linear-gradient(90deg, #0052a3, #1a80e0);
                transform: translateY(-2px);
                box-shadow: 0 4px 15px rgba(0, 102, 204, 0.4);
            }
            @media (max-width: 600px) {
                .pgp-intro-modal {
                    max-height: 95vh;
                }
                .pgp-intro-header, .pgp-intro-body, .pgp-intro-footer {
                    padding-left: 1.2rem;
                    padding-right: 1.2rem;
                }
            }
        `;
        document.head.appendChild(style);
    }

    function createModal() {
        if (document.getElementById(MODAL_ID)) return;
        const overlay = document.createElement('div');
        overlay.id = OVERLAY_ID;
        overlay.className = 'pgp-intro-overlay';
        overlay.innerHTML = `
            <div class="pgp-intro-modal" id="${MODAL_ID}" role="dialog" aria-modal="true" aria-labelledby="pgpIntroTitle">
                <div class="pgp-intro-header">
                    <h2 id="pgpIntroTitle">Welcome to the PGP Practice Tool</h2>
                    <p>Your safe space to learn encryption by doing.</p>
                </div>
                <div class="pgp-intro-body">
                    <h3>What is PGP?</h3>
                    <p>
                        PGP (Pretty Good Privacy) is a way to send messages that only the intended recipient can read.
                        It uses a <strong>key pair</strong>: a <strong>public key</strong> you can share with anyone, and a
                        <strong>private key</strong> you keep secret. Anyone can encrypt a message with your public key,
                        but only your private key can decrypt it.
                    </p>

                    <h3>Your first key pair</h3>
                    <p>Head to <strong>Encrypt / Decrypt</strong> and click <strong>Generate Key Pair</strong>. The tool will:</p>
                    <ul>
                        <li>Create an RSA public key and private key.</li>
                        <li>Save both to your profile automatically so you do not lose them.</li>
                        <li>Let you download a backup copy to your device.</li>
                    </ul>

                    <h3>How to practice</h3>
                    <ol class="step-list"><li>Write a note</li><li>Grab a public key</li><li>Encrypt it</li><li>Decrypt later</li></ol>

                    <h3>Practice Partner Challenge</h3>
                    <p>
                        On the <strong>Practice</strong> page you can exchange encrypted messages with an AI practice partner.
                        Copy the partner's public key, encrypt a message, paste it back, and the partner will reply with an
                        encrypted message only you can decrypt. It is a full end-to-end encryption loop!
                    </p>

                    <h3>Saved Keys & Notes</h3>
                    <p>
                        Use <strong>Saved Keys</strong> to store your friends' public keys. Use the <strong>Notes</strong> tab
                        in the right sidebar to write, encrypt, and decrypt quick practice notes.
                    </p>

                    <h3>Learn More on the Home Page</h3>
                    <p>
                        Scroll down on the Home page for a full beginner's guide covering
                        <strong>what PGP is, what it does, how to use it, and when to use it</strong>.
                    </p>

                    <div class="warning-box">
                        <strong>Remember:</strong> This is a learning environment. Your keys are stored on the
                        server so beginners cannot lose them. <strong>Never use this app for real secrets.</strong>
                    </div>
                </div>
                <div class="pgp-intro-footer">
                    <button class="pgp-intro-btn" id="pgpIntroCloseBtn">Got it — Let's practice!</button>
                    <label>
                        <input type="checkbox" id="pgpIntroRememberCheckbox" checked>
                        Don't show this introduction again
                    </label>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);

        document.getElementById('pgpIntroCloseBtn').addEventListener('click', async () => {
            const remember = document.getElementById('pgpIntroRememberCheckbox').checked;
            if (remember) {
                try {
                    await fetch('/api/intro-seen', { method: 'POST' });
                } catch (e) {
                    console.error('Failed to mark intro seen:', e);
                }
            }
            overlay.classList.remove('active');
            setTimeout(() => overlay.remove(), 350);
        });
    }

    async function maybeShowIntro() {
        try {
            const res = await fetch('/api/me', { cache: 'no-store' });
            const data = await res.json();
            if (data.logged_in && data.intro_seen === false) {
                injectStyles();
                createModal();
                // Small delay to allow the DOM to settle before animating in
                setTimeout(() => {
                    const overlay = document.getElementById(OVERLAY_ID);
                    if (overlay) overlay.classList.add('active');
                }, 100);
            }
        } catch (e) {
            console.error('Intro check failed:', e);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', maybeShowIntro);
    } else {
        maybeShowIntro();
    }
})();
