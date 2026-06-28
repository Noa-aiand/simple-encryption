/* Y2K Hit Counter — a fun fake visitor counter using localStorage.
   Mimics the classic early-2000s odometer-style hit counters. */
(function () {
    'use strict';

    var KEY = 'y2k_visits';
    var visits = parseInt(localStorage.getItem(KEY) || '0', 10) || 0;
    visits += 1;
    localStorage.setItem(KEY, String(visits));

    // Pad to 6 digits like a real counter
    var padded = String(visits).padStart(6, '0');

    function init() {
        var el = document.getElementById('hitCounter');
        if (!el) {
            el = document.createElement('div');
            el.id = 'hitCounter';
            el.className = 'hit-counter';
            el.innerHTML = '<span class="counter-digits">' + padded + '</span>';
            document.body.appendChild(el);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
