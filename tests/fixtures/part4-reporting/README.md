# Part 4 demonstration study — simulated only

All dates, citations, identity mappings, provenance events and responses in this
demonstration are constructed test data. They are not observed research findings.

`study.json` refers to the six-case fixture in `../part3-final-verification`.
Constructed paper ages at the fixed study reference date are 3, 10, 25, 45, 0 and
61 days. Experiment A includes the first four papers and explicitly accounts for
the two out-of-range papers. It does not infer dates from their citation years.
The provenance `verified` flags describe simulated verification events only.

First produce the Part 3 evaluation using that fixture's dataset, mappings and
simulated-origin configuration; then pass it to `citeprobe report` with this study
manifest and the original lookup bundle. See the root README for commands.

The six-case source bundle has canonical baseline observations only. Its Experiment
B report demonstrates baseline/error reporting and explicitly notes that no
mutation observations were supplied. Tests generate controlled mutation bundles
using mocked HTTP to verify mutation comparisons and paired cluster resampling.

`recent-preprints-config.json` and `mutation-config.json` retain default SVG output
and disable statistical bootstrap. Neither this six-paper fixture nor the original
five-paper pilot is large enough for the default cluster-interval threshold.
