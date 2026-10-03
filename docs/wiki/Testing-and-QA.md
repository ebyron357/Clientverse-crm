# Testing and QA

Release validation should cover:
- backend API tests against a running API and MongoDB;
- frontend lint;
- production frontend build;
- tenant isolation;
- role enforcement;
- webhook signing / retry / replay;
- MCP approval / undo behavior;
- integration sync normalization;
- scheduler execution;
- provider error states;
- production health evidence.

A green CI run is necessary but does not prove:
- provider credentials are valid;
- OAuth grants refresh;
- production cron secrets match;
- email is certified for live sending;
- external providers accepted a request.
