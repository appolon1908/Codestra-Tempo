# Security policy

Report vulnerabilities privately to the repository owner. Do not place tokens,
credentials, private keys, trace payloads, or incident data in public issues.

All image inputs and workflow actions are digest or commit pinned. Runtime secret
values must be mounted as files. Production activation requires protected lineage,
independent infrastructure review, and distributed-HA evidence outside this change.
