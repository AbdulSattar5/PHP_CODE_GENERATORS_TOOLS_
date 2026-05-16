/**
 * GenCode AI — global theme manager (dark / light / system)
 */
(function () {
    const STORAGE_KEY = 'gencode-theme';

    function getSystemTheme() {
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }

    function resolveTheme(theme) {
        if (theme === 'system') return getSystemTheme();
        return theme === 'light' ? 'light' : 'dark';
    }

    function applyResolved(resolved) {
        document.documentElement.setAttribute('data-theme', resolved);
        document.documentElement.style.colorScheme = resolved;
    }

    function syncHighlightTheme(resolved) {
        const link = document.getElementById('hljs-theme');
        if (!link) return;
        link.href = resolved === 'light'
            ? 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css'
            : 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css';
    }

    window.applyTheme = function applyTheme(theme) {
        const choice = theme || 'dark';
        localStorage.setItem(STORAGE_KEY, choice);
        const resolved = resolveTheme(choice);
        applyResolved(resolved);
        syncHighlightTheme(resolved);
        if (typeof window.updateThemeButtons === 'function') {
            window.updateThemeButtons(choice);
        }
    };

    window.getStoredTheme = function getStoredTheme() {
        return localStorage.getItem(STORAGE_KEY) || 'dark';
    };

    window.setStoredTheme = function setStoredTheme(theme) {
        localStorage.setItem(STORAGE_KEY, theme);
    };

    window.applySystemTheme = function applySystemTheme() {
        applyResolved(getSystemTheme());
    };

    window.updateThemeButtons = function updateThemeButtons(activeTheme) {
        const stored = activeTheme || getStoredTheme();
        document.querySelectorAll('[data-theme-choice]').forEach((btn) => {
            const value = btn.getAttribute('data-theme-choice');
            btn.classList.toggle('active', value === stored);
            btn.setAttribute('aria-pressed', value === stored ? 'true' : 'false');
        });
    };

    window.initThemeManager = function initThemeManager() {
        const stored = getStoredTheme();
        applyTheme(stored);

        document.querySelectorAll('[data-theme-choice]').forEach((btn) => {
            btn.addEventListener('click', () => {
                applyTheme(btn.getAttribute('data-theme-choice'));
            });
        });

        const mq = window.matchMedia('(prefers-color-scheme: dark)');
        const onSystemChange = () => {
            if (getStoredTheme() === 'system') {
                applySystemTheme();
            }
        };
        if (typeof mq.addEventListener === 'function') {
            mq.addEventListener('change', onSystemChange);
        } else if (typeof mq.addListener === 'function') {
            mq.addListener(onSystemChange);
        }
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initThemeManager);
    } else {
        initThemeManager();
    }
})();
