# Experiment B ACL frame amendment B-ACL-S1-v1

Scope approved by the user's Experiment B Sampling-Frame Amendment instruction.
This records that approval without inventing an approval timestamp. Implementation
and validation are offline; **no HTTP requests are authorized here**.

Preserve the original protocol, request plans, failed receipts and raw evidence.
This is a new sampling-frame version, not a parser alias or retrospective change
to what earlier runs requested.

The unchanged selectors are P18/1, P19/1 and 2020.acl/main. P18's source title
explicitly specifies long papers. P19/1's captured source title does not establish
a long-only population; retaining its existing literal selector does not justify
an additional long-only claim.

For **2021**, include both explicit research volumes: `long` (571 records) and
`short` (139), totaling 710 source records. Preserve each record's actual volume
identity. Neither is renamed or treated as an alias for `main`.

For **2022 and 2023**, adopt prospectively, before collecting or examining those
files: include the official ACL annual-conference main research proceedings.
Use a single `main` representation when the source has that representation and
no separate `long`/`short` research representation. Otherwise require both `long`
and `short` and no competing `main`. Stop for mixed, incomplete, duplicate or
ambiguous structures, missing authoritative proceedings metadata or conflicting
track labels; request review instead of substituting volumes.

Exclude findings, demos, workshops, tutorials, industry tracks, student research
workshops and other non-main-research tracks. Validate selected volumes against
the pinned collection identity and source proceedings metadata, not just a
convenient string match. Report included and excluded source volume IDs explicitly.
Unexpected or misleading selected-volume titles must stop automatic enumeration.

The new scope is the union of approved research volumes within each year before
the existing SHA-256 two-record ACL panel ranking. Seeds, source-ID tie-breaks,
arXiv day frames, primary-cs.CL eligibility, identity policy, review requirements
and evaluation metrics remain unchanged. A source-record count is not a count of
verified distinct scholarly works. No automatic duplicate merging is permitted.

Reuse all four complete saved responses at the verified immutable commit. The
remaining network inventory must exclude P18, P19, 2020.acl and 2021.acl; it may
contain only two unattempted pinned XML files and the six initial/six conditional
arXiv day pages, at most 14 new requests. Exact live authorization is separate.
