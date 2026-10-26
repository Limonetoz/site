// Run the actual published script in a dependency-free DOM/HTTP simulation.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(0, 'utf8');

class Node {
  constructor(tag = 'div') {
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.attrs = {};
    this.listeners = {};
    this.dataset = {};
    this.hidden = false;
    this.value = '';
    this._text = '';
    this.classList = {
      add: (...names) => { for (const name of names) this.attrs.class = [...new Set([...(this.attrs.class || '').split(' '), name])].join(' ').trim(); },
      remove: (...names) => { this.attrs.class = (this.attrs.class || '').split(' ').filter(name => !names.includes(name)).join(' '); },
      contains: name => (this.attrs.class || '').split(' ').includes(name),
      toggle: (name, force) => {
        const on = force ?? !this.classList.contains(name);
        this.classList[on ? 'add' : 'remove'](name);
        return on;
      },
    };
  }
  set textContent(text) { this._text = String(text); this.children = []; }
  get textContent() { return this._text + this.children.map(child => child.textContent).join(''); }
  set innerHTML(html) {
    assert.equal(html, '', 'Results must never render untrusted HTML');
    this.replaceChildren();
  }
  get innerHTML() { return this.children.map(child => child.textContent).join(''); }
  append(...children) { this.children.push(...children); }
  appendChild(child) { this.children.push(child); return child; }
  replaceChildren(...children) { this.children = children; this._text = ''; }
  setAttribute(name, value) { this.attrs[name] = String(value); if (name === 'hidden') this.hidden = true; }
  getAttribute(name) { return this.attrs[name] ?? null; }
  set href(value) { this.attrs.href = String(value); }
  get href() { return this.attrs.href; }
  removeAttribute(name) { delete this.attrs[name]; if (name === 'hidden') this.hidden = false; }
  addEventListener(name, handler) { (this.listeners[name] ??= []).push(handler); }
  dispatch(name, props = {}) {
    const event = { target: this, key: '', preventDefault() { this.defaultPrevented = true; }, ...props };
    for (const handler of this.listeners[name] || []) handler(event);
    return event;
  }
  focus() { this.focused = true; }
  matches(selector) {
    return selector.split(',').some(part => {
      const name = part.trim();
      const attr = /^\[([^\]]+)\]$/.exec(name);
      return attr ? Object.hasOwn(this.attrs, attr[1]) : this.tagName.toLowerCase() === name;
    });
  }
  querySelectorAll(selector) {
    return this.children.flatMap(child => [
      ...(child.matches(selector) ? [child] : []), ...child.querySelectorAll(selector),
    ]);
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] ?? null; }
}

const posts = [
  { lang: 'pt', title: '<img src=x onerror=alert(1)> Café', description: 'Guia sobre Árvore', categories: ['Tecnologia'], url: '/site/posts/cafe/' },
  { lang: 'pt', title: 'Segundo artigo', description: 'Outra descrição', categories: ['Estudos'], url: '/site/posts/segundo/' },
  { lang: 'en', title: 'English café', description: 'Tree guide', categories: ['Technology'], url: '/site/en/posts/coffee/' },
  { lang: 'pt', title: 'Trap script', description: 'trap', categories: [], url: 'javascript:alert(1)' },
  { lang: 'pt', title: 'Trap outside', description: 'trap', categories: [], url: '/other/posts/trap/' },
  ...Array.from({ length: 8 }, (_, n) => ({ lang: 'pt', title: `Item ${n}`, description: 'term comum', categories: ['tutorial'], url: `/site/posts/item-${n}/` })),
];

async function scenario(language, failed = false) {
  const root = new Node();
  const widget = new Node('div');
  widget.attrs['data-search'] = '';
  widget.attrs['data-index-url'] = '/site/search.json';
  widget.attrs['data-lang'] = language;
  widget.dataset = { indexUrl: '/site/search.json', lang: language };
  const input = new Node('input'); input.attrs['data-search-input'] = '';
  const results = new Node('ul'); results.attrs['data-search-results'] = '';
  const status = new Node('p'); status.attrs['data-search-status'] = '';
  widget.hidden = true;
  results.hidden = true;
  status.dataset = { empty: 'Start typing', loading: 'Loading', none: 'No results',
    found: 'Found', error: 'Search failed' };
  widget.append(input, results, status); root.append(widget);
  let requested = 0;
  const document = {
    readyState: 'complete',
    querySelector: selector => root.querySelector(selector),
    querySelectorAll: selector => root.querySelectorAll(selector),
    createElement: tag => new Node(tag),
    addEventListener(name, handler) { (this.listeners[name] ??= []).push(handler); },
    listeners: {},
  };
  const window = { location: { href: 'https://example.test/site/', origin: 'https://example.test',
    assign(url) { this.href = url; } }, document };
  const context = { document, window, console, URL, setTimeout, clearTimeout,
    fetch: async url => {
      requested++;
      assert.equal(String(url), 'https://example.test/site/search.json', 'Fetch must use the configured baseurl');
      if (failed) throw Error('network unavailable');
      return { ok: true, json: async () => posts };
    },
  };
  window.fetch = context.fetch;
  vm.runInNewContext(source, context, { filename: 'search.js', timeout: 1000 });
  for (const handler of document.listeners.DOMContentLoaded || []) handler();
  const tick = async () => { await new Promise(resolve => setTimeout(resolve, 30)); };
  const search = async value => { input.value = value; input.dispatch('input'); await tick(); };
  assert.equal(widget.hidden, false, 'JS should reveal the search control');
  await search('');
  assert.equal(results.querySelectorAll('a').length, 0, 'Empty input should have no results');
  assert.equal(status.textContent, status.dataset.empty, 'Empty status');
  if (failed) {
    await search('cafe');
    assert.equal(results.querySelectorAll('a').length, 0, 'Network errors must not show stale results');
    assert.equal(status.textContent, status.dataset.error, 'Network failure needs an error status');
    assert.equal(results.textContent, status.dataset.error, 'Network error must be visible in the results panel');
    return;
  }
  await search(language === 'pt' ? 'CAFE arVore' : 'cafe tree');
  let links = results.querySelectorAll('a');
  assert.equal(links.length, 1, `All terms, accent/case folding, and language filtering (status: ${status.textContent}; fetches: ${requested})`);
  assert.equal(links[0].getAttribute('href'), language === 'pt' ? '/site/posts/cafe/' : '/site/en/posts/coffee/');
  if (language === 'pt') {
    assert.equal(links[0].querySelector('img'), null, 'Index title must remain text, not HTML');
    await search('TECNOLOGIA');
    assert.equal(results.querySelectorAll('a').length, 1, 'Localized categories are searchable');
    await search('term');
    assert.equal(results.querySelectorAll('a').length, 6, 'Result limit must be six');
    await search('inexistente');
    assert.equal(results.querySelectorAll('a').length, 0);
    assert.equal(status.textContent, status.dataset.none, 'No-match status must be visible');
    assert.equal(results.textContent, status.dataset.none, 'No-match message must be visible in the results panel');
    await search('trap');
    assert.equal(results.querySelectorAll('a').length, 0, 'Unsafe and off-prefix URLs must never render');
    await search('cafe');
    links = results.querySelectorAll('a');
    const event = input.dispatch('keydown', { key: 'Enter' });
    assert.ok(event.defaultPrevented, 'Enter should activate first match');
    assert.equal(window.location.href, links[0].getAttribute('href'));
    input.dispatch('keydown', { key: 'Escape' });
    assert.equal(results.querySelectorAll('a').length, 0, 'Escape must close results');
  }
  assert.ok(requested > 0, 'Search must fetch the JSON index');
}

(async () => {
  await scenario('pt');
  await scenario('en');
  await scenario('pt', true);
  console.log('PASS busca localizada, filtro, teclado, erro e texto seguro');
})().catch(error => { console.error(error); process.exitCode = 1; });
