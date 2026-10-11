// Dash's dcc.Tabs renders each tab as a plain div that only reacts to the mouse. This makes
// every tab reachable with Tab, announced as a tab with its selected state, and operable
// with Enter, Space and the arrow keys, as a WAI-ARIA tab list is.
(function () {
    function label(root) {
        root.querySelectorAll('.tab-container').forEach(function (list) {
            list.setAttribute('role', 'tablist');
            list.querySelectorAll('.tab').forEach(function (tab) {
                const selected = tab.classList.contains('tab--selected');
                if (tab.getAttribute('role') !== 'tab') tab.setAttribute('role', 'tab');
                if (tab.getAttribute('aria-selected') !== String(selected)) tab.setAttribute('aria-selected', String(selected));
                const index = selected ? '0' : '-1';
                if (tab.getAttribute('tabindex') !== index) tab.setAttribute('tabindex', index);
            });
        });
    }
    new MutationObserver(function () { label(document); })
        .observe(document.documentElement, {subtree: true, childList: true, attributes: true, attributeFilter: ['class']});
    document.addEventListener('keydown', function (event) {
        const tab = event.target.closest && event.target.closest('.tab-container .tab');
        if (!tab) return;
        const tabs = [...tab.parentElement.querySelectorAll('.tab')];
        let next = null;
        if (event.key === 'ArrowRight' || event.key === 'ArrowDown') next = tabs[(tabs.indexOf(tab) + 1) % tabs.length];
        else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') next = tabs[(tabs.indexOf(tab) - 1 + tabs.length) % tabs.length];
        else if (event.key === 'Home') next = tabs[0];
        else if (event.key === 'End') next = tabs[tabs.length - 1];
        else if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); tab.click(); return; }
        if (next) { event.preventDefault(); next.click(); next.focus(); }
    });
})();
