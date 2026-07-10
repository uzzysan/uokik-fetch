(() => {
  const links = Array.from(document.querySelectorAll('a'));
  const decLinks = links.filter(a => {
    const h = a.href || '';
    const t = a.textContent || '';
    return h.indexOf('dec_prez.nsf') > -1 || t.match(/\d{4}\//);
  });
  return JSON.stringify(decLinks.map(a => ({
    text: a.textContent.trim().substring(0, 60),
    href: a.href
  })).slice(0, 40));
})()
