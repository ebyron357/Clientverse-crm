# ClientVerse frontend

React SPA (Create React App via CRACO) with Tailwind CSS and shadcn/ui.
See the [root README](../README.md) for the full platform documentation.

## Setup

```bash
yarn install          # use yarn, not npm
cp .env.example .env  # set REACT_APP_BACKEND_URL
```

## Scripts

| Command | Purpose |
|---|---|
| `yarn start` | Dev server on http://localhost:3000 |
| `yarn build` | Production build into `build/` (run with `CI=true` to fail on warnings) |
| `yarn test` | CRA test runner |

## Configuration

- `REACT_APP_BACKEND_URL` — backend base URL, baked into the bundle at build
  time. All API calls are prefixed with `/api`.
- `ENABLE_HEALTH_CHECK=true` — optional dev-server health endpoints
  (`plugins/health-check`).

## Notes

- `@` resolves to `src/` (see `craco.config.js` and `jsconfig.json`).
- The production HTML shell loads no analytics or third-party scripts.
- Deploy `build/` to any static host with SPA fallback to `index.html`.
