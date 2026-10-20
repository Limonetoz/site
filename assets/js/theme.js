(() => {
  const key = 'site-theme';
  const root = document.documentElement;
  const system = window.matchMedia('(prefers-color-scheme: dark)');
  let manualChoice = null;

  function savedTheme() {
    try {
      const value = localStorage.getItem(key);
      return value === 'light' || value === 'dark' ? value : null;
    } catch {
      return null;
    }
  }

  function currentTheme() {
    return manualChoice || savedTheme() || (system.matches ? 'dark' : 'light');
  }

  function apply(theme) {
    root.setAttribute('data-theme', theme);
    const browserColor = document.getElementById('theme-color');
    if (browserColor) browserColor.setAttribute('content', theme === 'dark' ? '#050505' : '#f4f3ee');
    const button = document.getElementById('theme-toggle');
    if (button) {
      button.hidden = false;
      button.textContent = button.getAttribute(`data-theme-current-${theme}`);
      button.setAttribute('aria-label', button.getAttribute(`data-theme-activate-${theme === 'dark' ? 'light' : 'dark'}`));
    }
  }

  // This script loads before the stylesheet to avoid flashing the wrong theme.
  apply(currentTheme());

  function ready() {
    const button = document.getElementById('theme-toggle');
    if (!button) return;
    apply(currentTheme());
    button.addEventListener('click', () => {
      const next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      manualChoice = next;
      try {
        localStorage.setItem(key, next);
      } catch {
        // Browsers with disabled storage can still switch for this page.
      }
      apply(next);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', ready);
  } else {
    ready();
  }

  if (system.addEventListener) {
    system.addEventListener('change', () => {
      if (!manualChoice && !savedTheme()) apply(currentTheme());
    });
  }
})();
