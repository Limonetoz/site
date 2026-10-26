(() => {
  function ready() {
    const header = document.querySelector('.header');
    const button = header?.querySelector('.menu-toggle');
    const navigation = header?.querySelector('.navigation');
    if (!button || !navigation) return;

    function setOpen(open) {
      header.classList.toggle('menu-open', open);
      button.setAttribute('aria-expanded', String(open));
    }

    header.classList.add('menu-ready');
    button.hidden = false;
    button.addEventListener('click', () => setOpen(button.getAttribute('aria-expanded') !== 'true'));
    navigation.addEventListener('click', (event) => {
      if (event.target.closest('a')) setOpen(false);
    });
    header.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && button.getAttribute('aria-expanded') === 'true') {
        setOpen(false);
        button.focus();
      }
    });
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', ready);
  else ready();
})();
