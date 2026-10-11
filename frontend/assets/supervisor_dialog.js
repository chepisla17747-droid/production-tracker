// Keep focus inside the quantity dialog; Escape uses the same Cancel action.
// While it is open the rest of the page is inert, so neither Tab nor a screen reader can
// reach content behind it. Focus then returns to the button that opened it.
(function () {
    let previousFocus, previousId;
    function setBackgroundInert(modal, inert) {
        // The dialog sits inside the page layout, so its siblings up the tree are made inert.
        for (let node = modal; node && node !== document.body; node = node.parentElement) {
            for (const sibling of node.parentElement ? node.parentElement.children : []) {
                if (sibling !== node) sibling.inert = inert;
            }
        }
    }
    function remember(element) {
        previousFocus = element;
        previousId = element && element.id;
    }
    document.addEventListener('click', function (event) {
        const button = event.target.closest('button');
        if (button && ['part-start','part-complete','part-skip','part-scrap'].includes(button.id)) remember(button);
    }, true);
    const observer = new MutationObserver(function () {
        const modal = document.getElementById('part-modal');
        const visible = modal && modal.style.display !== 'none';
        if (visible && !modal.dataset.focused) {
            if (!modal.contains(document.activeElement)) remember(document.activeElement);
            modal.dataset.focused = 'true';
            setBackgroundInert(modal, true);
            requestAnimationFrame(function () {
                const input = document.getElementById('part-quantity');
                if (input && modal.style.display !== 'none') { input.focus(); input.select(); }
            });
        } else if (modal && !visible && modal.dataset.focused) {
            delete modal.dataset.focused;
            setBackgroundInert(modal, false);
            // Dash may have re-rendered the opener; find its replacement by id.
            const target = previousFocus && previousFocus.isConnected ? previousFocus
                : (previousId && document.getElementById(previousId));
            if (target && !target.disabled) target.focus();
            else { const heading = document.querySelector('.part-detail h2'); if (heading) { heading.tabIndex = -1; heading.focus(); } }
        }
    });
    observer.observe(document.documentElement, {subtree:true,childList:true,attributes:true,attributeFilter:['style']});
    document.addEventListener('keydown', function (event) {
        const modal = document.getElementById('part-modal');
        if (!modal || modal.style.display === 'none') return;
        if (event.key === 'Escape') document.getElementById('part-cancel').click();
        if (event.key !== 'Tab') return;
        const items = [...modal.querySelectorAll('input,button,select,textarea,[href]')].filter(e => !e.disabled);
        const first = items[0], last = items[items.length-1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    });
})();
