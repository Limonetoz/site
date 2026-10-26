const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const listeners = {};
const classes = new Set();
const button = {
  hidden: true,
  attrs: { 'aria-expanded': 'false' },
  getAttribute(key) { return this.attrs[key]; },
  setAttribute(key, value) { this.attrs[key] = value; },
  addEventListener(name, handler) { listeners[`button:${name}`] = handler; },
  focus() { this.focused = true; },
};
const navigation = {
  addEventListener(name, handler) { listeners[`navigation:${name}`] = handler; },
};
const header = {
  classList: {
    add(name) { classes.add(name); },
    toggle(name, enabled) { if (enabled) classes.add(name); else classes.delete(name); },
  },
  querySelector(selector) { return selector === '.menu-toggle' ? button : navigation; },
  addEventListener(name, handler) { listeners[`header:${name}`] = handler; },
};
const document = {
  readyState: 'loading',
  querySelector(selector) { return selector === '.header' ? header : null; },
  addEventListener(name, handler) { listeners[`document:${name}`] = handler; },
};

vm.runInNewContext(fs.readFileSync(0, 'utf8'), { document }, { timeout: 1000 });
assert.equal(button.hidden, true, 'Without JS initialization the navigation must remain available');
assert.equal(classes.has('menu-ready'), false);
listeners['document:DOMContentLoaded']();
assert.equal(button.hidden, false);
assert.equal(classes.has('menu-ready'), true);
listeners['button:click']();
assert.equal(button.getAttribute('aria-expanded'), 'true');
assert.equal(classes.has('menu-open'), true);
listeners['header:keydown']({ key: 'Escape' });
assert.equal(button.getAttribute('aria-expanded'), 'false');
assert.equal(classes.has('menu-open'), false);
assert.equal(button.focused, true, 'Escape returns focus to the menu control');
listeners['button:click']();
listeners['navigation:click']({ target: { closest: () => ({ tagName: 'A' }) } });
assert.equal(button.getAttribute('aria-expanded'), 'false', 'Following a link closes the menu');
console.log('PASS menu responsivo, Escape, foco e navegação sem JS');
