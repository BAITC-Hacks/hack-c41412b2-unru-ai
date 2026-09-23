'use strict';
function revealMethodAnchor() {
  const id = decodeURIComponent(location.hash.slice(1));
  const target = document.getElementById(id);
  if (!target) return;
  const section = target.closest('details');
  if (section) section.open = true;
  target.scrollIntoView({block:'start'});
}
window.addEventListener('hashchange', revealMethodAnchor);
revealMethodAnchor();
