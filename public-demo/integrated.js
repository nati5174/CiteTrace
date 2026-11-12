/* Local prototype only. Atlas cells map to frozen records, never match confidence. */
let atlasPair = 0;
let narrowAtlas = matchMedia('(max-width:800px)').matches;
function atlasLink(text, href, cls) {
  const a = link(text, href); a.className = cls; return a;
}
function renderAtlas() {
  const area = $('#specimen');
  area.replaceChildren();
  const heading = node('div', undefined, 'evidence-head');
  heading.append(node('h2', 'Retrieval results'),
    node('p', 'Select a paper or provider to inspect its retrieval record.'));
  area.append(heading);
  const mobile = matchMedia('(max-width:800px)').matches;
  const subset = mobile ? papers.slice(atlasPair * 2, atlasPair * 2 + 2) : papers;
  if (mobile) {
    const controls = node('nav', undefined, 'atlas-controls');
    controls.setAttribute('aria-label', 'Browse all eight Atlas sources');
    const count = node('p', `Sources ${atlasPair * 2 + 1}–${atlasPair * 2 + 2} of ${papers.length}`);
    count.setAttribute('role', 'status');
    controls.append(count);
    for (const [label, delta] of [['Previous pair', -1], ['Next pair', 1]]) {
      const button = node('button', label);button.type = 'button';
      button.disabled = atlasPair + delta < 0 || atlasPair + delta >= papers.length / 2;
      button.addEventListener('click', () => {
        atlasPair += delta; renderAtlas();
        const buttons = [...document.querySelectorAll('.atlas-controls button')];
        const equivalent = buttons.find(b => b.textContent === label && !b.disabled);
        (equivalent || buttons.find(b => !b.disabled)).focus({preventScroll:true});
      });
      controls.append(button);
    }
    area.append(controls);
  }
  const map = node('div', undefined, 'pilot-map');
  map.setAttribute('role', 'group');map.setAttribute('aria-label', 'Frozen source papers and recorded provider searches');
  map.append(node('div', 'Source paper', 'map-cell map-label source-axis'));
  for (const paper of subset) {
    const a = atlasLink('', '#paper=' + paper.id, 'map-cell map-source');
    a.title = paper.title;
    a.dataset.sourceId = paper.id;
    a.setAttribute('aria-label', `Inspect source arXiv:${paper.id}: ${paper.title}`);
    a.append(node('code', paper.id), node('span', paper.title, 'source-short-title'));
    map.append(a);
  }
  for (const provider of providers) {
    map.append(node('div', providerNames[provider], 'map-cell map-label'));
    for (const paper of subset) {
      const candidates = paper.results[provider].candidates;
      const a = atlasLink('', `#paper=${paper.id}&provider=${provider}`, 'map-cell map-result');
      a.dataset.sourceId = paper.id; a.dataset.provider = provider;
      a.setAttribute('aria-label', `Inspect arXiv:${paper.id}, ${providerNames[provider]}: ${candidates.length} returned candidate entries. `
        + (candidates.length ? 'All identities undetermined.' : 'No candidates to assess.'));
      if (candidates.length) {
        const marks = node('div', undefined, 'rank-cells');marks.setAttribute('aria-hidden', 'true');
        for (const c of candidates) marks.append(node('span', String(c.rank), 'rank-cell'));
        a.append(marks, node('small', `${candidates.length} returned`));
      } else a.append(node('span', '0 returned', 'empty-mark'));
      map.append(a);
    }
  }
  area.append(map);
  const note = node('div', undefined, 'evidence-foot');
  note.append(node('p', 'Numbers show provider ranks. OpenAlex used one anonymous and seven API-key searches; Crossref used eight anonymous searches.'),
    atlasLink('Study limitations', 'methodology.html#limitations', ''));
  area.append(note);
}
function jumpToRecord(record) {
  const heading = record.querySelector('h3');heading.tabIndex = -1;heading.focus({preventScroll:true});
  record.scrollIntoView({block:'start'});
  const source = $('.source');
  if (matchMedia('(max-width:800px)').matches && getComputedStyle(source).position === 'sticky')
    window.scrollBy(0, -(source.getBoundingClientRect().height + 16));
}
function renderPath() {
  if ($('#inspection').hidden || $('.evidence-path') || !$('.results-head')) return;
  const {id, provider} = readRoute(location.hash);
  const paper = papers.find(p => p.id === id);
  if (!paper) return;
  const active = selectedProvider(paper, provider);
  const candidates = paper.results[active].candidates;
  const path = node('details', undefined, 'evidence-path');
  path.open = matchMedia('(min-width:801px)').matches;
  path.append(node('summary', 'Source → search → candidates → identity'));
  const stages = node('ol', undefined, 'path-stages');
  for (const [label, value] of [
    ['Source paper', 'arXiv:' + paper.id],
    ['Provider search', `${providerNames[active]} · title, authors and year`],
    ['Ranked candidates', candidates.length ? `${candidates.length} returned · original provider order` : 'None returned'],
    ['Identity evidence', candidates.length ? 'Undetermined in the frozen pilot' : 'No returned candidates to assess'],
  ]) {
    const item = node('li');item.append(node('strong', label), node('span', value));stages.append(item);
  }
  path.append(stages);
  // Replace the repeated general ranking disclaimer; leave actual access/HTTP metadata intact.
  $('.results-head .note')?.remove();
  $('.results-head').after(path);
  if (candidates.length) {
    const jumps = node('nav', undefined, 'rank-jumps');
    jumps.setAttribute('aria-label', 'Jump to original provider rank');
    jumps.append(node('p', 'Jump to rank'));
    for (const record of document.querySelectorAll('.candidate-record')) {
      const rank = Number(record.querySelector('.rank').textContent);
      const button = node('button', String(rank).padStart(2, '0'));button.type = 'button';
      button.setAttribute('aria-label', `Jump to provider rank ${rank}`);
      button.addEventListener('click', () => jumpToRecord(record));jumps.append(button);
    }
    path.after(jumps);
  }
}
const initialAtlas = new MutationObserver(() => {
  if (!papers.length || !$('#specimen').children.length) return;
  initialAtlas.disconnect();renderAtlas();
});
initialAtlas.observe($('#specimen'), {childList:true});
const pathObserver = new MutationObserver(renderPath);
pathObserver.observe($('#inspection'), {childList:true, subtree:true});
window.addEventListener('resize', () => {
  const narrow = matchMedia('(max-width:800px)').matches;
  if (narrow !== narrowAtlas && papers.length) { narrowAtlas = narrow;renderAtlas(); }
});
