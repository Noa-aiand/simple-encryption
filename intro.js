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
                background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                border: 1px solid rgba(157, 78, 221, 0.5);
                border-radius: 20px;
                box-shadow: 0 24px 80px rgba(0, 0, 0, 0.6);
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
                border-bottom: 1px solid rgba(157, 78, 221, 0.2);
            }
            .pgp-intro-header h2 {
                color: #9d4edd;
                font-size: 1.6rem;
                margin: 0 0 0.4rem;
                text-transform: uppercase;
                letter-spacing: 2px;
            }
            .pgp-intro-header p {
                color: #c77dff;
                font-size: 0.95rem;
                margin: 0;
            }
            .pgp-intro-body {
                padding: 1.5rem 2rem;
                overflow-y: auto;
                color: #ddd;
                font-size: 0.95rem;
                line-height: 1.65;
            }
            .pgp-intro-body h3 {
                color: #c77dff;
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
                background: rgba(255, 152, 0, 0.12);
                border: 1px solid rgba(255, 152, 0, 0.35);
                border-radius: 10px;
                padding: 12px 16px;
                color: #ffb74d;
                margin-top: 1rem;
            }
            .pgp-intro-body .warning-box strong {
                color: #ff9800;
            }
            .pgp-intro-body .step-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                gap: 12px;
                margin: 1rem 0;
            }
            .pgp-intro-body .step-card {
                background: rgba(157, 78, 221, 0.1);
                border: 1px solid rgba(157, 78, 221, 0.25);
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
                color: #c77dff;
                font-size: 0.85rem;
                font-weight: 600;
            }
            .pgp-intro-footer {
                padding: 1rem 2rem 1.6rem;
                display: flex;
                flex-direction: column;
                gap: 12px;
                align-items: center;
                border-top: 1px solid rgba(157, 78, 221, 0.2);
            }
            .pgp-intro-footer label {
                color: #ccc;
                font-size: 0.9rem;
                display: flex;
                align-items: center;
                gap: 8px;
                cursor: pointer;
            }
            .pgp-intro-footer input[type="checkbox"] {
                width: 16px;
                height: 16px;
                accent-color: #9d4edd;
                cursor: pointer;
            }
            .pgp-intro-btn {
                background: linear-gradient(90deg, #7b2cbf, #9d4edd);
                border: none;
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
                background: linear-gradient(90deg, #9d4edd, #c77dff);
                transform: translateY(-2px);
                box-shadow: 0 4px 15px rgba(157, 78, 221, 0.4);
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
                    <h3><span>&#128161;</span> What is PGP?</h3>
                    <p>
                        PGP (Pretty Good Privacy) is a way to send messages that only the intended recipient can read.
                        It uses a <strong>key pair</strong>: a <strong>public key</strong> you can share with anyone, and a
                        <strong>private key</strong> you keep secret. Anyone can encrypt a message with your public key,
                        but only your private key can decrypt it.
                    </p>

                    <h3><span>&#128273;</span> Your first key pair</h3>
                    <p>Head to <strong>Encrypt / Decrypt</strong> and click <strong>Generate Key Pair</strong>. The tool will:</p>
                    <ul>
                        <li>Create an RSA public key and private key.</li>
                        <li>Save both to your profile automatically so you do not lose them.</li>
                        <li>Let you download a backup copy to your device.</li>
                    </ul>

                    <h3><span>&#128274;</span> How to practice</h3>
                    <div class="step-grid">
                        <div class="step-card"><span class="emoji">&#128221;</span><span class="label">Write a note</span></div>
                        <div class="step-card"><span class="emoji">&#128273;</span><span class="label">Grab a public key</span></div>
                        <div class="step-card"><span class="emoji">&#128274;</span><span class="label">Encrypt it</span></div>
                        <div class="step-card"><span class="emoji">&#128275;</span><span class="label">Decrypt later</span></div>
                    </div>

                    <h3><span>&#127919;</span> Practice Partner Challenge</h3>
                    <p>
                        On the <strong>Practice</strong> page you can exchange encrypted messages with an AI practice partner.
                        Copy the partner's public key, encrypt a message, paste it back, and the partner will reply with an
                        encrypted message only you can decrypt. It is a full end-to-end encryption loop!
                    </p>

                    <h3><span>&#128203;</span> Saved Keys & Notes</h3>
                    <p>
                        Use <strong>Saved Keys</strong> to store your friends' public keys. Use the <strong>Notes</strong> tab
                        in the right sidebar to write, encrypt, and decrypt quick practice notes.
                    </p>

                    <h3><span>&#128214;</span> Learn More on the Home Page</h3>
                    <p>
                        Scroll down on the Home page for a full beginner's guide covering
                        <strong>what PGP is, what it does, how to use it, and when to use it</strong>.
                    </p>

                    <div class="warning-box">
                        <strong>&#9888; Remember:</strong> This is a learning environment. Your keys are stored on the
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
