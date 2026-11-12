/* Frozen research records are rendered without modification. */
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

const providerNames = {openalex: 'OpenAlex', crossref: 'Crossref'};
const providers = Object.keys(providerNames);
let papers = [];
let searches = [];
let cohort = 'all';
let inspectedId = null;
const $ = selector => document.querySelector(selector);

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}

function link(text, href) {
  const element = node('a', text);
  element.href = href;
  return element;
}

function validateManifest(manifest, data) {
  if (!manifest || manifest.schema_version !== '1.0'
      || manifest.evaluation_id !== data.evaluation_id
      || manifest.dataset_sha256 !== data.dataset_sha256
      || !Array.isArray(manifest.searches) || manifest.searches.length !== 16)
    throw Error('Invalid experiment manifest');
  for (const paper of data.papers) {
    for (const provider of providers) {
      const rows = manifest.searches.filter(s =>
        s.source_paper_id === paper.id && s.provider === provider);
      const result = paper.results[provider];
      if (rows.length !== 1 || rows[0].http_status !== 200
          || !['anonymous', 'api_key_query_parameter'].includes(rows[0].authentication_mode)
          || rows[0].outcome !== result.outcome
          || JSON.stringify(rows[0].candidate_ranks)
            !== JSON.stringify(result.candidates.map(c => c.rank)))
        throw Error('Inconsistent request metadata');
    }
  }
  return manifest.searches;
}

function readRoute(hash) {
  const params = new URLSearchParams(hash.replace(/^#/, ''));
  return {id: params.get('paper'), provider: params.get('provider')};
}

function selectedProvider(paper, requested) {
  return providers.includes(requested) ? requested
    : providers.find(provider => paper.results[provider].candidates.length) || providers[0];
}

function drawOverview() {
  const list = $('#paper-list');
  list.replaceChildren();
  const subset = papers.filter(p => cohort === 'all' || p.cohort === cohort);
  $('#count').textContent = `Showing ${subset.length} of ${papers.length} source papers`;
  if (!subset.length) list.append(node('p', 'No papers in this cohort. Choose All papers.'));
  for (const paper of subset) {
    const row = link('', '#paper=' + paper.id);
    row.className = 'paper-link';
    const descriptions = providers.map(provider => {
      const count = paper.results[provider].candidates.length;
      return `${providerNames[provider]}: ${count} candidate entries returned; `
        + (count ? 'identities undetermined' : 'no candidates to assess');
    });
    row.setAttribute('aria-label', `Inspect ${paper.title}. ${descriptions.join('. ')}.`);
    const source = node('div');
    source.append(node('strong', paper.title),
      node('small', `arXiv:${paper.id} · ${paper.cohort} days`));
    row.append(source);
    for (const provider of providers) {
      const status = node('div', providerNames[provider], 'status');
      status.append(node('small', `${paper.results[provider].candidates.length} candidate entries`));
      row.append(status);
    }
    list.append(row);
  }
}

function drawFindings() {
  const labels = ['Provider', 'Searches returning records', 'Candidate entries',
    'Identity evidence', 'Recall@5 bounds', 'Recorded access'];
  $('#matrix').replaceChildren();
  for (const provider of providers) {
    const results = papers.map(p => p.results[provider]);
    const returned = results.filter(r => r.candidates.length).length;
    const entries = results.reduce((sum, r) => sum + r.candidates.length, 0);
    const hits = results.filter(r => r.recall_at_5 === 'HIT').length;
    const uncertain = results.filter(r => r.recall_at_5 === 'UNDETERMINED').length;
    const requests = searches.filter(s => s.provider === provider);
    const anonymous = requests.filter(s => s.authentication_mode === 'anonymous').length;
    const access = [`${anonymous} anonymous`];
    if (requests.length > anonymous) access.push(`${requests.length - anonymous} API key`);
    const values = [providerNames[provider], `${returned} / ${results.length}`, String(entries),
      'Undetermined (frozen labels)', `${hits}–${hits + uncertain} / ${results.length}`,
      access.join('; ')];
    const row = node('tr');
    row.setAttribute('role', 'row');
    values.forEach((value, index) => {
      const cell = node(index === 0 ? 'th' : 'td', value);
      cell.setAttribute('role', index === 0 ? 'rowheader' : 'cell');
      if (index === 0) cell.scope = 'row';
      cell.dataset.label = labels[index];
      row.append(cell);
    });
    $('#matrix').append(row);
  }
}

function drawSpecimen() {
  const paper = papers[0];
  const candidate = paper.results.crossref.candidates[0];
  const area = $('#specimen');
  area.replaceChildren(node('h2', 'Recorded example'),
    node('p', `Source · arXiv:${paper.id}`, 'meta'), node('h3', paper.title));
  const result = node('div', undefined, 'sample-result');
  result.append(node('span', `Crossref · provider rank ${candidate.rank}`, 'meta'),
    node('h3', candidate.title),
    node('p', 'Identity undetermined · ' + candidate.reason, 'tag'),
    link(`View ${paper.results.crossref.candidates.length} candidates`,
      '#paper=' + paper.id));
  area.append(result);
}

function changeProvider(id, provider) {
  history.replaceState(null, '', `#paper=${id}&provider=${provider}`);
  drawRoute();
  $('.provider-nav button[aria-pressed=true]').focus({preventScroll: true});
}

function sourceContext(paper) {
  const source = node('aside', undefined, 'source');
  source.setAttribute('aria-label', 'Source paper context');
  source.append(node('h2', 'Source paper'),
    node('span', `arXiv:${paper.id}`, 'mobile-summary'), node('h3', paper.title),
    node('p', `arXiv:${paper.id} · ${paper.cohort} days`, 'meta'));
  const details = node('details');
  details.append(node('summary', 'Source and provenance'), node('p', paper.title),
    node('p', paper.authors.join(', ')),
    link('Source record on arXiv', 'https://arxiv.org/abs/' + paper.id),
    node('p', 'Curator-reviewed source metadata; frozen candidate labels.'),
    link('Recorded request metadata · JSON', 'experiment-manifest.json'));
  details.open = matchMedia('(min-width: 801px)').matches;
  source.append(details);
  return source;
}

function candidateRecord(candidate) {
  const record = node('article', undefined, 'candidate-record');
  const rank = node('span', String(candidate.rank).padStart(2, '0'), 'rank');
  rank.setAttribute('aria-label', `Provider rank ${candidate.rank}`);
  record.append(rank);
  const body = node('div');
  body.append(node('span', 'Identity undetermined', 'identity'),
    node('h3', candidate.title || 'Title unavailable'),
    node('p', `${candidate.authors.join(', ') || 'Authors unavailable'}`
      + (candidate.year ? ' · ' + candidate.year : '')));
  if (candidate.doi) body.append(link('DOI: ' + candidate.doi, 'https://doi.org/' + candidate.doi));
  else if (candidate.arxiv_id)
    body.append(link('arXiv: ' + candidate.arxiv_id, 'https://arxiv.org/abs/' + candidate.arxiv_id));
  else body.append(node('p', 'Identifier unavailable'));
  body.append(node('p', candidate.reason, 'note'));
  record.append(body);
  return record;
}

function drawInspection(paper, requested) {
  const area = $('#inspection');
  area.replaceChildren();
  const top = node('div', undefined, 'inspection-top');
  top.append(link('All papers', '#explore'));
  const tools = node('div');
  const index = papers.indexOf(paper);
  if (index > 0) tools.append(link('Previous', '#paper=' + papers[index - 1].id));
  if (index < papers.length - 1) tools.append(link('Next', '#paper=' + papers[index + 1].id));
  const copy = node('button', 'Copy link');
  copy.type = 'button';
  const feedback = node('span', '', 'copy-status');
  feedback.setAttribute('role', 'status');
  copy.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(location.href);
      feedback.textContent = 'Link copied';
    } catch {
      feedback.textContent = 'Copy this page URL from your address bar';
    }
  });
  tools.append(copy, feedback);
  top.append(tools);
  const heading = node('h1', `Paper ${index + 1} of ${papers.length}`);
  heading.id = 'inspection-title';
  heading.tabIndex = -1;
  area.append(top, heading);
  const bench = node('div', undefined, 'workbench');
  bench.append(sourceContext(paper));
  const results = node('div');
  const navigation = node('nav', undefined, 'provider-nav');
  navigation.setAttribute('aria-label', 'Jump to provider results');
  const active = selectedProvider(paper, requested);
  for (const provider of providers) {
    const button = node('button', `${providerNames[provider]} · `
      + `${paper.results[provider].candidates.length} candidates`);
    button.type = 'button';
    button.setAttribute('aria-pressed', String(active === provider));
    button.addEventListener('click', () => changeProvider(paper.id, provider));
    navigation.append(button);
  }
  results.append(navigation);
  const result = paper.results[active];
  const request = searches.find(s => s.source_paper_id === paper.id && s.provider === active);
  const summary = node('div', undefined, 'results-head');
  summary.append(node('h2', providerNames[active] + ' search'),
    node('p', `${result.candidates.length} candidate entries · `
      + `${request.authentication_mode === 'anonymous' ? 'Anonymous access' : 'API key access'}`
      + ` · HTTP ${request.http_status}`, 'meta'),
    node('p', 'Provider ranking preserved. Returned does not mean verified.', 'note'));
  results.append(summary);
  if (!result.candidates.length) {
    results.append(node('p', 'No candidates returned. '
      + 'This does not establish absence from the provider database.'));
    for (const provider of providers.filter(p => paper.results[p].candidates.length)) {
      const button = node('button', `View ${providerNames[provider]} · `
        + `${paper.results[provider].candidates.length} candidates`);
      button.type = 'button';
      button.addEventListener('click', () => changeProvider(paper.id, provider));
      results.append(button);
    }
  }
  for (const candidate of result.candidates) results.append(candidateRecord(candidate));
  bench.append(results);
  area.append(bench);
}

function drawRoute() {
  const {id, provider} = readRoute(location.hash);
  const oldId = inspectedId;
  $('#overview').hidden = Boolean(id);
  $('#inspection').hidden = !id;
  if (!id) {
    document.title = 'CiteProbe — Exploratory citation-retrieval pilot';
    if (oldId) {
      const row = [...document.querySelectorAll('.paper-link')]
        .find(a => a.hash === '#paper=' + oldId);
      (row || $('#explore')).focus({preventScroll: true});
    }
    // Honor explicit navigation anchors instead of always jumping back to Explore.
    const anchor = ['#findings', '#explore', '#reproduce', '#main'].includes(location.hash)
      ? $(location.hash) : oldId ? $('#explore') : null;
    anchor?.scrollIntoView();
    inspectedId = null;
    return;
  }
  const paper = papers.find(p => p.id === id);
  if (!paper) {
    $('#inspection').replaceChildren(node('h1', 'Source paper not found'),
      link('Return to all eight papers', '#explore'));
    return;
  }
  inspectedId = id;
  document.title = `${paper.title} — CiteProbe inspection`;
  drawInspection(paper, provider);
  if (oldId !== id) {
    window.scrollTo(0, 0);
    $('#inspection-title').focus({preventScroll: true});
  }
}

async function loadPilot() {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const responses = await Promise.all(['data.json', 'experiment-manifest.json']
      .map(file => fetch(file, {signal: controller.signal})));
    if (responses.some(response => !response.ok)) throw Error('Data unavailable');
    const [data, manifest] = await Promise.all(responses.map(response => response.json()));
    const validated = validate(data);
    searches = validateManifest(manifest, data);
    papers = validated;
    drawFindings();
    drawOverview();
    drawSpecimen();
    $('#cohort').disabled = false;
    $('#loading').hidden = true;
    drawRoute();
  } catch {
    $('#overview').hidden = true;
    $('#inspection').hidden = true;
    $('#cohort').disabled = true;
    $('#loading').hidden = false;
    $('#loading').className = 'error';
    $('#loading').setAttribute('role', 'alert');
    $('#loading').replaceChildren(
      node('p', 'The frozen records could not be loaded. Refresh to try again.'),
      link('Read methodology', 'methodology.html'));
  } finally {
    clearTimeout(timeout);
  }
}

if (typeof document !== 'undefined') {
  $('#cohort').addEventListener('change', event => {
    cohort = event.target.value;
    drawOverview();
  });
  window.addEventListener('hashchange', () => { if (papers.length) drawRoute(); });
  loadPilot();
}
