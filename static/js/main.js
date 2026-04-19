// main.js — students will add JavaScript here as features are built

(function () {
    const overlay = document.getElementById('videoModal');
    if (!overlay) return;

    const frame = document.getElementById('videoFrame');
    const openBtn = document.getElementById('openVideoModal');
    const closeBtn = document.getElementById('closeVideoModal');

    function openModal() {
        frame.src = frame.dataset.src;
        overlay.classList.add('is-open');
        overlay.setAttribute('aria-hidden', 'false');
    }

    function closeModal() {
        overlay.classList.remove('is-open');
        overlay.setAttribute('aria-hidden', 'true');
        // Stop video by clearing src, then restore data-src for next open
        frame.src = '';
    }

    openBtn.addEventListener('click', openModal);
    closeBtn.addEventListener('click', closeModal);

    // Close on backdrop click (but not on the modal box itself)
    overlay.addEventListener('click', function (e) {
        if (e.target === overlay) closeModal();
    });

    // Close on Escape key
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && overlay.classList.contains('is-open')) closeModal();
    });
}());
