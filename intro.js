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
                position: fixed !important;
                top: 0 !important;
                left: 0 !important;
                width: 100% !important;
                height: 100% !important;
                background: rgba(0, 30, 80, 0.5) !important;
                backdrop-filter: blur(4px) !important;
                z-index: 3000 !important;
                opacity: 0;
                visibility: hidden;
                transition: all 0.35s ease;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
                padding: 20px !important;
            }
            .pgp-intro-overlay.active {
                opacity: 1;
                visibility: visible;
            }
            .pgp-intro-modal {
                width: 100% !important;
                max-width: 720px !important;
                max-height: 90vh !important;
                background: #ffffff !important;
                border: 3px solid #6699cc !important;
                border-radius: 16px !important;
                box-shadow: 0 16px 48px rgba(0, 51, 102, 0.25) !important;
                display: flex !important;
                flex-direction: column !important;
                overflow: hidden !important;
                transform: translateY(20px) scale(0.96);
                transition: transform 0.35s ease;
            }
            .pgp-intro-overlay.active .pgp-intro-modal {
                transform: translateY(0) scale(1);
            }
            .pgp-intro-header {
                padding: 1.6rem 2rem 1rem !important;
                text-align: center !important;
                background: linear-gradient(180deg, #e6f2ff 0%, #ffffff 100%) !important;
                border-bottom: 2px solid #b3d7ff !important;
            }
            .pgp-intro-header h2 {
                color: #003366 !important;
                font-size: 1.5rem !important;
                margin: 0 0 0.4rem !important;
                text-transform: uppercase !important;
                letter-spacing: 1px !important;
                text-shadow: none !important;
                font-family: 'Arial Black', 'Arial', sans-serif !important;
            }
            .pgp-intro-header p {
                color: #336699 !important;
                font-size: 0.92rem !important;
                margin: 0 !important;
                text-shadow: none !important;
            }
            .pgp-intro-body {
                padding: 1.5rem 2rem !important;
                overflow-y: auto !important;
                color: #003366 !important;
                font-size: 0.92rem !important;
                line-height: 1.65 !important;
                background: #ffffff !important;
            }
            .pgp-intro-body h3 {
                color: #0066cc !important;
                font-size: 0.98rem !important;
                margin: 1.3rem 0 0.5rem !important;
                display: flex !important;
                align-items: center !important;
                gap: 8px !important;
                text-shadow: none !important;
                font-family: 'Arial Black', 'Arial', sans-serif !important;
            }
            .pgp-intro-body h3:first-child {
                margin-top: 0 !important;
            }
            .pgp-intro-body p {
                margin: 0 0 0.8rem !important;
                color: #003366 !important;
            }
            .pgp-intro-body ul {
                margin: 0 0 1rem 1.2rem !important;
                padding: 0 !important;
            }
            .pgp-intro-body li {
                margin-bottom: 0.35rem !important;
                color: #003366 !important;
            }
            .pgp-intro-body strong {
                color: #003366 !important;
            }
            .pgp-intro-body .warning-box {
                background: #fff8e6 !important;
                border: 2px solid #ffc266 !important;
                border-radius: 10px !important;
                padding: 12px 16px !important;
                color: #664400 !important;
                margin-top: 1rem !important;
            }
            .pgp-intro-body .warning-box strong {
                color: #cc6600 !important;
            }
            .pgp-intro-body .step-grid {
                display: grid !important;
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)) !important;
                gap: 12px !important;
                margin: 1rem 0 !important;
            }
            .pgp-intro-body .step-card {
                background: #f0f7ff !important;
                border: 2px solid #b3d7ff !important;
                border-radius: 10px !important;
                padding: 14px !important;
                text-align: center !important;
            }
            .pgp-intro-body .step-card .emoji {
                font-size: 1.6rem !important;
                display: block !important;
                margin-bottom: 6px !important;
            }
            .pgp-intro-body .step-card .label {
                color: #0066cc !important;
                font-size: 0.85rem !important;
                font-weight: 600 !important;
            }
            .pgp-intro-body .step-list {
                margin: 0 0 1rem 1.4rem !important;
                padding: 0 !important;
                color: #003366 !important;
                font-size: 0.95rem !important;
                line-height: 1.7 !important;
            }
            .pgp-intro-body .step-list li {
                margin-bottom: 0.35rem !important;
                color: #003366 !important;
            }
            .pgp-intro-footer {
                padding: 1rem 2rem 1.6rem !important;
                display: flex !important;
                flex-direction: column !important;
                gap: 12px !important;
                align-items: center !important;
                background: linear-gradient(180deg, #ffffff 0%, #e6f2ff 100%) !important;
                border-top: 2px solid #b3d7ff !important;
            }
            .pgp-intro-footer label {
                color: #336699 !important;
                font-size: 0.88rem !important;
                display: flex !important;
                align-items: center !important;
                gap: 8px !important;
                cursor: pointer !important;
            }
            .pgp-intro-footer input[type="checkbox"] {
                width: 16px !important;
                height: 16px !important;
                accent-color: #0066cc !important;
                cursor: pointer !important;
            }
            .pgp-intro-btn {
                background: linear-gradient(180deg, #3399ff 0%, #0066cc 100%) !important;
                border: 2px outset #66a3ff !important;
                border-radius: 10px !important;
                color: #ffffff !important;
                padding: 12px 36px !important;
                font-size: 0.95rem !important;
                font-weight: bold !important;
                text-transform: uppercase !important;
                letter-spacing: 1px !important;
                cursor: pointer !important;
                box-shadow: 2px 2px 0 #336699 !important;
                transition: all 0.2s ease !important;
                text-shadow: none !important;
            }
            .pgp-intro-btn:hover {
                background: linear-gradient(180deg, #4da6ff 0%, #0077dd 100%) !important;
                transform: translateY(-1px) !important;
                box-shadow: 2px 3px 0 #336699 !important;
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
                    <h2 id="pgpIntroTitle">Welcome to Pretty Good Practice</h2>
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
