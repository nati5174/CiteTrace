# B-ACL-R1-v1: ACL 2023 resource-limit amendment

Approved scope: preparation and offline validation only. Live acquisition requires separate authorization of a sealed plan hash and authorization reference.

For the exact immutable ACL Anthology 2023 source URL at commit 032cc14d4a17181e8754f33512c22ff53d9cbbc6, permit one separately recorded new GET with capture, decoded-body and XML limits of 4,000,000 bytes. All other requests retain 2,000,000-byte limits. This does not authorize automatic retries.

Reuse the five complete ACL files byte-identically. Preserve the previous incomplete 2023 body, prefix hash, receipt and source timestamps. The new representation must match the preserved prefix and advertised full length; differences require review. Retain at most 12 arXiv requests, including conditional second pages. The combined new request ceiling is 13.

The B-ACL-S1-v1 sampling-frame amendment continues unchanged, with explicit long/short volume provenance and stopping on ambiguity. No source identity is inferred and no unreviewed dataset is frozen. Planned windows never substitute for actual capture timestamps.

The machine-readable companion b-acl-resource-v1.json is hashed into the resource continuation plan. The v3.1 plan additionally seals its proposed authorization reference. Existing policy documents, historical receipts, v3.0 plan and evidence are preserved.
