(() => {
  function ready() {
    const search = document.querySelector('[data-search]');
    if (!search) return;
    const input = search.querySelector('[data-search-input]');
    const results = search.querySelector('[data-search-results]');
    const status = search.querySelector('[data-search-status]');
    if (!input || !results || !status) return;

    const indexUrl = new URL(search.dataset.indexUrl, window.location.href);
    const basePath = indexUrl.pathname.slice(0, -'search.json'.length);
    if (indexUrl.origin !== window.location.origin || !indexUrl.pathname.endsWith('/search.json')) return;

    const normalize = (text) => text.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
    let index;
    let pending;
    let sequence = 0;

    function safeUrl(value) {
      if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//') || value.includes('\\')) return null;
      if (/%(?:2f|5c|2e)/i.test(value) || value.includes('?') || value.includes('#')) return null;
      const url = new URL(value, window.location.origin);
      if (url.origin !== window.location.origin || !url.pathname.startsWith(basePath)) return null;
      return url.pathname;
    }

    function load() {
      if (index) return Promise.resolve(index);
      if (!pending) {
        pending = fetch(indexUrl.href)
          .then((response) => {
            if (!response.ok) throw new Error('Search index unavailable');
            return response.json();
          })
          .then((data) => {
            if (!Array.isArray(data)) throw new Error('Invalid search index');
            index = data.filter((post) => post && post.lang === search.dataset.lang &&
              typeof post.title === 'string' && typeof post.description === 'string' &&
              Array.isArray(post.categories) && post.categories.every((category) => typeof category === 'string'));
            return index;
          })
          .finally(() => { pending = null; });
      }
      return pending;
    }

    function clear() {
      results.replaceChildren();
      results.hidden = true;
    }

    function showMessage(message) {
      clear();
      const item = document.createElement('li');
      item.className = 'search-message';
      item.textContent = message;
      results.append(item);
      results.hidden = false;
    }

    function update() {
      const request = ++sequence;
      const terms = normalize(input.value.trim()).split(/\s+/).filter(Boolean);
      clear();
      if (!terms.length) {
        status.textContent = status.dataset.empty;
        return;
      }
      status.textContent = status.dataset.loading;
      showMessage(status.dataset.loading);
      load().then((posts) => {
        if (request !== sequence) return;
        const matches = posts.filter((post) => {
          const url = safeUrl(post.url);
          if (!url) return false;
          return terms.every((term) => normalize([post.title, post.description, ...post.categories].join(' ')).includes(term));
        }).slice(0, 6);
        if (!matches.length) {
          status.textContent = status.dataset.none;
          showMessage(status.dataset.none);
          return;
        }
        clear();
        matches.forEach((post) => {
          const item = document.createElement('li');
          const link = document.createElement('a');
          link.href = safeUrl(post.url);
          link.textContent = post.title;
          item.append(link);
          results.append(item);
        });
        results.hidden = false;
        status.textContent = `${status.dataset.found} ${matches.length}`;
      }).catch(() => {
        if (request === sequence) {
          status.textContent = status.dataset.error;
          showMessage(status.dataset.error);
        }
      });
    }

    input.addEventListener('input', update);
    input.addEventListener('focus', () => {
      if (input.value.trim()) update();
    });
    function close() {
      ++sequence;
      clear();
      input.value = '';
      status.textContent = status.dataset.empty;
    }

    input.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') close();
      else if (event.key === 'Enter') {
        const first = results.querySelector('a');
        if (first && !results.hidden) {
          event.preventDefault();
          window.location.assign(first.href);
        }
      }
    });
    search.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && event.target !== input) {
        close();
        input.focus();
      }
    });
    search.hidden = false;
    status.textContent = status.dataset.empty;
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', ready);
  } else {
    ready();
  }
})();
