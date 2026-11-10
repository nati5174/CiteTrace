/* Frozen pilot presentation. Rendering and arithmetic never change the public records. */
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
  const text = value => typeof value === 'string' && value.trim().length > 0;
  const authors = value => Array.isArray(value) && value.every(text);
  const hash = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
  const identifier = value => typeof value === 'string' && /^\d{4}\.\d{4,5}$/.test(value);
  if (!data || data.schema_version !== '1.0' || data.review_status !== 'owner_approved'
      || !hash(data.evaluation_id) || !hash(data.dataset_sha256)
      || !Array.isArray(data.papers) || data.papers.length !== 8) throw Error('Unexpected dataset');
  const ids = new Set();
  let candidateCount = 0;
  for (const paper of data.papers) {
    if (!paper || !text(paper.title) || !identifier(paper.id) || ids.has(paper.id)
        || !authors(paper.authors) || !paper.authors.length
        || !['1-7', '8-14', '15-30', '31-60'].includes(paper.cohort)) throw Error('Invalid source');
    ids.add(paper.id);
    for (const provider of ['openalex', 'crossref']) {
      const result = paper.results?.[provider];
      if (!result || !['FOUND', 'NOT_FOUND'].includes(result.outcome)
          || !Array.isArray(result.candidates) || result.candidates.length > 5
          || (result.outcome === 'FOUND') !== (result.candidates.length > 0)
          || !['HIT', 'MISS', 'UNDETERMINED'].includes(result.recall_at_1)
          || !['HIT', 'MISS', 'UNDETERMINED'].includes(result.recall_at_5)
          || !['UNDETERMINED', null].includes(result.rank_one_judgment)) throw Error('Invalid result');
      const expectedRecall = result.outcome === 'FOUND' ? 'UNDETERMINED' : 'MISS';
      if (result.recall_at_1 !== expectedRecall || result.recall_at_5 !== expectedRecall
          || result.rank_one_judgment !== (result.outcome === 'FOUND' ? 'UNDETERMINED' : null))
        throw Error('Inconsistent frozen identity evidence');
      let rank = 0;
      for (const candidate of result.candidates) {
        if (!candidate || !Number.isInteger(candidate.rank) || candidate.rank <= rank
            || candidate.rank > 5 || (candidate.title !== null && !text(candidate.title))
            || !authors(candidate.authors) || candidate.judgment !== 'UNDETERMINED'
            || !text(candidate.reason)
            || (candidate.year !== null && (!Number.isInteger(candidate.year) || candidate.year < 1))
            || (candidate.doi !== null && !/^10\.\d{4,9}\/\S+$/.test(candidate.doi))
            || (candidate.arxiv_id !== null && !text(candidate.arxiv_id))) throw Error('Invalid candidate');
        rank = candidate.rank;
        candidateCount += 1;
      }
    }
  }
  if (candidateCount !== 41) throw Error('Unexpected frozen candidate inventory');
  return data.papers;
}
function resultLabel(result) {
  return result.outcome === 'FOUND' ? 'Candidates returned' : 'No candidates returned';
}
function resultStatus(result, provider) {
  const box = el('div', 'status ' + (result.outcome === 'FOUND' ? 'found' : 'empty'));
  box.append(el('span', 'provider-name', provider));
  box.append(el('span', '', resultLabel(result)));
  box.append(el('small', '', `${result.candidates.length} candidate ${result.candidates.length === 1 ? 'entry' : 'entries'}`));
  return box;
}
function drawComparison() {
  comparisonEl.replaceChildren();
  for (const [key, name] of [['openalex', 'OpenAlex'], ['crossref', 'Crossref']]) {
    const results = papers.map(p => p.results[key]);
    const returned = results.filter(r => r.outcome === 'FOUND').length;
    const entries = results.reduce((total, r) => total + r.candidates.length, 0);
    const confirmed = results.filter(r => r.recall_at_5 === 'HIT').length;
    const uncertain = results.filter(r => r.recall_at_5 === 'UNDETERMINED').length;
    const card = el('article', 'provider-card');
    const title = el('div', 'provider-title');
    title.append(el('h3', '', name), el('span', '', 'RECORDED SEARCHES'));
    const stats = el('div', 'provider-stats');
    stats.append(el('strong', '', `${returned} / ${results.length}`), el('span', '', 'searches returned candidates'));
    card.append(title, stats);
    card.append(el('p', '', `${entries} candidate ${entries === 1 ? 'entry' : 'entries'} returned. ${results.length - returned} searches returned no candidates.`));
    card.append(el('p', '', 'All candidate identities are undetermined. Return counts are not verified matches or accuracy scores.'));
    const bounds = el('div', 'bounds');
    bounds.append(el('span', '', 'Recall@5 identity-evidence bounds'), el('b', '', `${confirmed}–${confirmed + uncertain} / ${results.length}`));
    card.append(bounds);
    comparisonEl.append(card);
  }
}
function drawPapers() {
  papersEl.replaceChildren();
  if (loadState !== 'ready') {
    const failed = loadState === 'error';
    papersEl.append(el('p', failed ? 'error' : 'loading', failed
      ? 'The evaluation data could not be loaded. Refresh to try again.' : 'Loading papers…'));
    countEl.textContent = failed ? 'DATA UNAVAILABLE' : 'LOADING';
    return;
  }
  const subset = papers.filter(p => cohort === 'all' || p.cohort === cohort);
  if (!subset.length) papersEl.append(el('p', 'loading', 'No papers in this cohort.'));
  for (const paper of subset) {
    const row = el('button', 'paper-row');
    row.type = 'button';
    row.setAttribute('aria-label', `Inspect source paper: ${paper.title}`);
    const info = el('div');
    const meta = el('div', 'paper-meta', `arXiv:${paper.id} · ${paper.cohort} days`);
    meta.id = `source-${paper.id}-meta`;
    info.append(el('div', 'paper-title', paper.title), meta);
    const openalex = resultStatus(paper.results.openalex, 'OpenAlex');
    const crossref = resultStatus(paper.results.crossref, 'Crossref');
    openalex.id = `source-${paper.id}-openalex`;
    crossref.id = `source-${paper.id}-crossref`;
    row.setAttribute('aria-describedby', `${meta.id} ${openalex.id} ${crossref.id}`);
    const arrow = el('span', 'arrow icon-arrow');
    arrow.setAttribute('aria-hidden', 'true');
    row.append(info, openalex, crossref, arrow);
    row.addEventListener('click', () => showDetail(paper));
    papersEl.append(row);
  }
  countEl.textContent = `SHOWING ${subset.length} OF ${papers.length} PAPERS`;
}
function showDetail(paper) {
  detail.replaceChildren();
  const source = el('div', 'source-record');
  const heading = el('h2', '', paper.title);
  heading.id = 'detail-title';
  source.append(el('div', 'eyebrow', 'SOURCE PAPER'), heading);
  source.append(el('p', '', `arXiv:${paper.id} · ${paper.cohort} days`));
  const sourceAuthors = el('details', 'source-authors');
  sourceAuthors.append(el('summary', '', 'Source authors'), el('p', '', paper.authors.join(', ')));
  source.append(sourceAuthors);
  const sourceLink = el('a', 'text-link', 'View the source record on arXiv');
  sourceLink.href = `https://arxiv.org/abs/${paper.id}`;
  sourceLink.target = '_blank';
  sourceLink.rel = 'noopener noreferrer';
  source.append(sourceLink);
  detail.append(source, el('p', 'request-note', 'Source metadata is separate from the returned candidates below. Undetermined does not mean incorrect.'));
  const provenance = el('a', 'text-link', 'Inspect recorded request metadata (JSON)');
  provenance.href = 'experiment-manifest.json';
  provenance.setAttribute('download', 'experiment-manifest.json');
  detail.append(provenance);
  for (const [key, name] of [['openalex', 'OpenAlex'], ['crossref', 'Crossref']]) {
    const result = paper.results[key];
    const section = el('section', 'provider-results');
    section.append(el('h3', '', `${name} recorded search`));
    section.append(el('p', 'search-summary', `${resultLabel(result)} · ${result.candidates.length} candidate entries`));
    if (!result.candidates.length) section.append(el('p', '', 'No candidates were returned by this search. This does not establish absence from the provider’s database.'));
    for (const candidate of result.candidates) {
      const item = el('article', 'candidate');
      item.append(el('div', 'candidate-label', `RANK ${candidate.rank} · ${candidate.judgment}`));
      item.append(el('h4', '', candidate.title || 'Title unavailable'));
      item.append(el('p', '', `${candidate.authors.join(', ') || 'Authors unavailable'}${candidate.year ? ' · ' + candidate.year : ''}`));
      const identifier = candidate.doi ? `DOI: ${candidate.doi}` : candidate.arxiv_id ? `arXiv: ${candidate.arxiv_id}` : 'Identifier unavailable';
      const identifierNode = el(candidate.doi || candidate.arxiv_id ? 'a' : 'p', '', identifier);
      if (candidate.doi || candidate.arxiv_id) {
        identifierNode.href = candidate.doi ? `https://doi.org/${candidate.doi}` : `https://arxiv.org/abs/${candidate.arxiv_id}`;
        identifierNode.target = '_blank';
        identifierNode.rel = 'noopener noreferrer';
      }
      item.append(identifierNode, el('p', '', candidate.reason));
      section.append(item);
    }
    detail.append(section);
  }
  dialog.showModal();
}
document.getElementById('close-detail').addEventListener('click', () => dialog.close());
document.querySelectorAll('[data-cohort]').forEach(button => button.addEventListener('click', () => {
  cohort = button.dataset.cohort;
  document.querySelectorAll('[data-cohort]').forEach(b => {
    b.classList.toggle('active', b === button);
    b.setAttribute('aria-pressed', String(b === button));
  });
  drawPapers();
}));
async function loadPilot() {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch('data.json', {signal: controller.signal});
    if (!response.ok) throw Error('Data unavailable');
    papers = validate(await response.json());
    loadState = 'ready';
    drawComparison();
    drawPapers();
  } catch {
    loadState = 'error';
    drawPapers();
    comparisonEl.replaceChildren(el('p', 'error', 'Comparison unavailable because the evaluation data could not be loaded. Refresh to try again.'));
  } finally {
    clearTimeout(timeout);
  }
}
loadPilot();
