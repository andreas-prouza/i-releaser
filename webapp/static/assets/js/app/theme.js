/*
 * Theme (light or dark) and the collapsed navigation (docs/features/web-ui-layout.md).
 *
 * Loaded in <head> as a normal script, not as a module: it sets data-bs-theme and the class of the
 * navigation before the page is drawn, so nothing flickers. Without a stored choice the theme follows
 * the setting of the browser. Both choices are remembered per browser (localStorage).
 */
(() => {
    const root = document.documentElement;
    const THEME_KEY = 'ir-theme';
    const NAV_KEY = 'ir-nav';
    const COLLAPSED = 'ir-nav-collapsed';

    // localStorage can be switched off (private mode, policies): then nothing is remembered
    const read = (key) => {
        try {
            return localStorage.getItem(key);
        } catch {
            return null;
        }
    };
    const write = (key, value) => {
        try {
            localStorage.setItem(key, value);
        } catch {
            // not remembered
        }
    };

    const browser_dark = window.matchMedia('(prefers-color-scheme: dark)');
    const stored_theme = () => ['light', 'dark'].includes(read(THEME_KEY)) ? read(THEME_KEY) : null;
    const current_theme = () => stored_theme() || (browser_dark.matches ? 'dark' : 'light');

    const update_buttons = () => {
        const dark = root.dataset.bsTheme === 'dark';
        for (const button of document.querySelectorAll('[data-theme-toggle]')) {
            const label = dark ? 'Switch to light mode' : 'Switch to dark mode';
            button.setAttribute('aria-label', label);
            button.title = label;
            button.setAttribute('aria-pressed', String(dark));
        }
        const collapsed = root.classList.contains(COLLAPSED);
        for (const button of document.querySelectorAll('[data-nav-toggle]')) {
            const label = collapsed ? 'Expand navigation' : 'Collapse navigation';
            button.setAttribute('aria-label', label);
            button.title = label;
            button.setAttribute('aria-expanded', String(!collapsed));
        }
    };

    const apply_theme = (theme) => {
        root.dataset.bsTheme = theme;
        update_buttons();
    };

    apply_theme(current_theme());
    root.classList.toggle(COLLAPSED, read(NAV_KEY) === 'collapsed');

    // The setting of the browser changes (e.g. at night): follow it, unless the user has chosen
    browser_dark.addEventListener('change', () => {
        if (!stored_theme()) {
            apply_theme(current_theme());
        }
    });

    document.addEventListener('DOMContentLoaded', update_buttons);

    document.addEventListener('click', (event) => {
        if (event.target.closest('[data-theme-toggle]')) {
            const theme = root.dataset.bsTheme === 'dark' ? 'light' : 'dark';
            write(THEME_KEY, theme);
            apply_theme(theme);
        } else if (event.target.closest('[data-nav-toggle]')) {
            const collapsed = !root.classList.contains(COLLAPSED);
            root.classList.toggle(COLLAPSED, collapsed);
            write(NAV_KEY, collapsed ? 'collapsed' : 'open');
            update_buttons();
        }
    });
})();
