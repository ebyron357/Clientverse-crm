# Closeout and Evidence

## Do not call an item done because it is
- implemented;
- configured locally;
- submitted;
- in review;
- green in CI;
- reachable in the UI.

## Required evidence categories
- merged PR / exact SHA;
- CI on the final SHA;
- deployed release identity;
- production health;
- database connectivity;
- scheduler execution;
- provider connection health;
- end-to-end integration proof;
- owner/admin handoff;
- rollback / recovery instructions.

## Current closeout focus
Recent evidence indicates remaining work is concentrated around live provider readiness and owner/admin operations rather than basic repository setup. These must be verified against current production before the project is declared closed.
