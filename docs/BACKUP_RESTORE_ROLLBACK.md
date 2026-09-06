# Backup, restore, and rollback

Before runtime changes, record the current image digest, configuration checksums,
object-store recovery evidence, WAL and generator volume locations, and the prior
approved image. Rehearse rollback on an isolated instance and preserve queryability
before changing another instance.

This document does not execute a backup, restore, deployment, or rollback.
