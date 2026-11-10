/* CiteProbe exploratory pilot. All visible values come from the reviewed draft export. */
const papersEl = document.getElementById('papers');
const comparisonEl = document.getElementById('comparison');
const countEl = document.getElementById('paper-count');
const dialog = document.getElementById('detail');
const detail = document.getElementById('detail-content');
let papers = [];
let cohort = 'all';
let loadState = 'loading';

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);
  return node;
}
function validate(data) {
  if (data.schema_version !== '1.0' || data.review_status !== 'owner_review_pending' || !Array.isArray(data.papers) || data.papers.length !== 8) throw new Error('Unexpected dataset');
  for (const p of data.papers) {
    if (!p.title || !p.id || !['1-7','8-14','15-30','31-60'].includes(p.cohort)) throw new Error('Invalid paper');
    for (const provider of ['openalex','crossref']) {
      const r = p.results?.[provider];
      if (!r || !['FOUND','NOT_FOUND'].includes(r.outcome) || !Array.isArray(r.candidates)) throw new Error('Invalid result');
    }
  }
  return data.papers;
}
function resultStatus(result, provider) {
  const box = el('div', 'status ' + (result.outcome === 'FOUND' ? 'found' : 'empty'));
  box.append(el('span', 'provider-name', provider));
  box.append(el('span', '', result.outcome === 'FOUND' ? '●  FOUND' : '○  NOT FOUND'));
  box.append(el('small', '', `${result.candidates.length} candidate${result.candidates.length === 1 ? '' : 's'}`));
  return box;
}
function drawComparison() {
  comparisonEl.replaceChildren();
  for (const [key, name] of [['openalex','OpenAlex'],['crossref','Crossref']]) {
    const results = papers.map(p => p.results[key]);
    const returned = results.filter(r => r.outcome === 'FOUND').length;
    const confirmed = results.filter(r => r.recall_at_5 === 'HIT').length;
    const uncertain = results.filter(r => r.recall_at_5 === 'UNDETERMINED').length;
    const card = el('article', 'provider-card');
    const title = el('div', 'provider-title'); title.append(el('h3','',name),el('span','','METADATA SEARCH')); card.append(title);
    const stats = el('div','provider-stats'); stats.append(el('strong','',`${returned} / ${results.length}`),el('span','','searches returned candidates')); card.append(stats);
    const bar = el('div','bar'); const fill = el('span'); fill.style.width = `${100 * returned / results.length}%`; bar.append(fill); card.append(bar);
    card.append(el('p','',`${results.length - returned} searches returned no candidates. Returned candidates are not automatically verified matches.`));
    const bounds = el('div','bounds'); bounds.append(el('span','','Verified recall@5 evidence bounds'),el('b','',`${confirmed}–${confirmed + uncertain} / ${results.length}`)); card.append(bounds); comparisonEl.append(card);
  }
}
function drawPapers() {
  papersEl.replaceChildren();
  if (loadState !== 'ready') {
    const failed = loadState === 'error';
    papersEl.append(el('div', failed ? 'error' : 'loading', failed
      ? 'The evaluation data could not be loaded. Refresh to try again.'
      : 'Loading papers…'));
    countEl.textContent = failed ? 'DATA UNAVAILABLE' : 'LOADING';
    return;
  }
  const subset = papers.filter(p => cohort === 'all' || p.cohort === cohort);
  if (!subset.length) papersEl.append(el('div','loading','No papers in this cohort.'));
  for (const paper of subset) {
    const row = el('button','paper-row'); row.type = 'button'; row.setAttribute('aria-label',`Inspect ${paper.title}`);
    const info = el('div'); info.append(el('div','paper-title',paper.title),el('div','paper-meta',`arXiv:${paper.id}  ·  ${paper.cohort} days`));
    row.append(info,resultStatus(paper.results.openalex, 'OpenAlex'),resultStatus(paper.results.crossref, 'Crossref'),el('span','arrow','↗'));
    row.addEventListener('click',()=>showDetail(paper)); papersEl.append(row);
  }
  countEl.textContent = `SHOWING ${subset.length} OF ${papers.length} PAPERS`;
}
function showDetail(paper) {
  detail.replaceChildren();
  const heading = el('h2','',paper.title); heading.id = 'detail-title'; detail.append(heading);
  detail.append(el('p','',`${paper.authors.join(', ')} · arXiv:${paper.id} · ${paper.cohort} days`));
  for (const [key,name] of [['openalex','OpenAlex'],['crossref','Crossref']]) {
    const result = paper.results[key]; const section = el('section','candidate');
    section.append(el('div','eyebrow',`${name.toUpperCase()} · ${result.outcome} · ${result.candidates.length} CANDIDATES`));
    if (!result.candidates.length) section.append(el('p','','No candidates were returned by this search. This does not establish absence from the provider’s database.'));
    for (const candidate of result.candidates) {
      const item = el('div','candidate');
      item.append(el('div','candidate-label',`RANK ${candidate.rank} · ${candidate.judgment}`));
      item.append(el('h3','',candidate.title || 'Title unavailable'));
      item.append(el('p','',`${candidate.authors.join(', ') || 'Authors unavailable'}${candidate.year ? ' · ' + candidate.year : ''}`));
      item.append(el('p','',candidate.doi ? `DOI: ${candidate.doi}` : candidate.arxiv_id ? `arXiv: ${candidate.arxiv_id}` : 'Identifier unavailable'));
      item.append(el('p','',candidate.reason)); section.append(item);
    }
    detail.append(section);
  }
  dialog.showModal();
}
document.getElementById('close-detail').addEventListener('click',()=>dialog.close());
document.querySelectorAll('[data-cohort]').forEach(button=>button.addEventListener('click',()=>{
  cohort=button.dataset.cohort; document.querySelectorAll('[data-cohort]').forEach(b=>{b.classList.toggle('active',b===button); b.setAttribute('aria-pressed',String(b===button));}); drawPapers();
}));
fetch('data.json').then(response=>{if(!response.ok) throw new Error('Data unavailable'); return response.json();}).then(data=>{papers=validate(data);loadState='ready';drawComparison();drawPapers();}).catch(()=>{loadState='error';drawPapers();comparisonEl.replaceChildren(el('div','error','Comparison unavailable because the evaluation data could not be loaded. Refresh to try again.'));});
