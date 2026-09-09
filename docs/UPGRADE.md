# Upgrade policy

Import an exact upstream commit on a feature branch, verify its official and
sanitized tree identities, update every digest-pinned build input, build and inspect
the image in CI, and promote the same protected source through development, test,
staging, production, and main. Never build the production image on a server.

The repository-readiness gate computes `git rev-parse HEAD:upstream` and requires
that tree identity to equal `CODESTRA_UPSTREAM_LOCK.json#imported_tree_sha` before
an image can be built or released. If the gate fails, restore the last protected
source tree or regenerate all source-lock evidence in a separately reviewed sync
change; never alter only the duplicated JSON fields.
