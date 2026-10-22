const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(0, 'utf8');

function scenario(systemDark, saved, storageFails = false, language = 'pt') {
  const attrs = new Map();
  const handlers = {};
  const storage = new Map(saved ? [['site-theme', saved]] : []);
  const labels = language === 'en'
    ? { dark: 'Theme: dark', light: 'Theme: light', toDark: 'Activate dark mode', toLight: 'Activate light mode' }
    : { dark: 'Tema: escuro', light: 'Tema: claro', toDark: 'Ativar modo escuro', toLight: 'Ativar modo claro' };
  const button = {
    attrs: {
      'data-theme-current-dark': labels.dark,
      'data-theme-current-light': labels.light,
      'data-theme-activate-dark': labels.toDark,
      'data-theme-activate-light': labels.toLight,
    },
    addEventListener(type, callback) { handlers[`button:${type}`] = callback; },
    setAttribute(key, value) { this.attrs[key] = String(value); },
    getAttribute(key) { return this.attrs[key]; },
    textContent: '',
    hidden: true,
  };
  const browserColor = {
    attrs: {},
    setAttribute(key, value) { this.attrs[key] = String(value); },
  };
  const media = {
    matches: systemDark,
    addEventListener(type, callback) { handlers[`media:${type}`] = callback; },
  };
  const root = {
    dataset: {},
    setAttribute(key, value) {
      attrs.set(key, String(value));
      if (key === 'data-theme') this.dataset.theme = String(value);
    },
    getAttribute(key) { return attrs.get(key) ?? (key === 'data-theme' ? this.dataset.theme : null); },
  };
  const document = {
    documentElement: root,
    readyState: 'loading',
    getElementById(id) {
      return id === 'theme-toggle' ? button : id === 'theme-color' ? browserColor : null;
    },
    querySelector(selector) { return selector === '#theme-toggle' ? button : null; },
    addEventListener(type, callback) { handlers[`document:${type}`] = callback; },
  };
  const context = {
    document,
    localStorage: {
      getItem(key) {
        if (storageFails) throw new Error('storage blocked');
        return storage.get(key) ?? null;
      },
      setItem(key, value) {
        if (storageFails) throw new Error('storage blocked');
        storage.set(key, String(value));
      },
    },
    window: {
      matchMedia(query) {
        assert.equal(query, '(prefers-color-scheme: dark)');
        return media;
      },
      addEventListener(type, callback) { handlers[`window:${type}`] = callback; },
    },
    console,
  };
  context.window.document = document;
  context.window.localStorage = context.localStorage;
  context.matchMedia = context.window.matchMedia;
  vm.runInNewContext(source, context, { timeout: 1000, filename: 'theme.js' });
  for (const name of ['document:DOMContentLoaded', 'window:load']) {
    if (handlers[name]) handlers[name]();
  }
  const initial = saved || (systemDark ? 'dark' : 'light');
  assert.equal(root.getAttribute('data-theme'), initial,
    `initial theme with systemDark=${systemDark}, saved=${saved}`);
  assert.equal(button.hidden, false, 'toggle must become visible');
  assert.equal(button.textContent, labels[initial]);
  assert.equal(button.getAttribute('aria-label'), initial === 'dark' ? labels.toLight : labels.toDark);
  const initialBrowserColor = browserColor.attrs.content;
  assert.ok(initialBrowserColor, 'browser theme-color must be set');
  media.matches = !systemDark;
  handlers['media:change']();
  assert.equal(root.getAttribute('data-theme'), saved || (media.matches ? 'dark' : 'light'),
    'system preference should update only if no saved preference exists');
  media.matches = systemDark;
  handlers['media:change']();
  assert.equal(typeof handlers['button:click'], 'function', 'theme button must be clickable');
  handlers['button:click']();
  const next = initial === 'dark' ? 'light' : 'dark';
  assert.equal(root.getAttribute('data-theme'), next, 'click must change root theme');
  assert.ok(browserColor.attrs.content, 'browser theme-color must remain set');
  assert.notEqual(browserColor.attrs.content, initialBrowserColor,
    'browser theme-color must update with the selected theme');
  if (!storageFails) assert.equal(storage.get('site-theme'), next, 'click must persist preference');
  assert.equal(button.textContent, labels[next]);
  assert.equal(button.getAttribute('aria-label'), next === 'dark' ? labels.toLight : labels.toDark);
  media.matches = !systemDark;
  handlers['media:change']();
  media.matches = systemDark;
  handlers['media:change']();
  assert.equal(root.getAttribute('data-theme'), next,
    'manual choice must survive system preference changes even without storage');
}

try {
  scenario(true, null);
  scenario(false, null);
  scenario(false, 'dark');
  scenario(true, 'light');
  scenario(true, null, true);
  scenario(true, null, false, 'en');
  scenario(false, 'dark', false, 'en');
  console.log('PASS preferência do sistema, substituição e persistência');
} catch (error) {
  console.error(error);
  process.exitCode = 1;
}
