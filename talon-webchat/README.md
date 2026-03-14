# Project Talon Webchat

React/Vite frontend for the Talon backend's public chat experience.

## Local Development

```bash
corepack enable
pnpm install --frozen-lockfile
pnpm dev
```

By default the setup screen targets `http://localhost:8000`. You can also provide a build-time backend URL with `VITE_API_URL`.

## Production Build

```bash
VITE_API_URL=https://api.example.com pnpm exec tsc -b
VITE_API_URL=https://api.example.com pnpm exec vite build
```

On Render, this app is deployed as a static site via the repo-root [`render.yaml`](/Users/ruiliu/Documents/Codex/EntAgentv2/code/render.yaml) and uses a rewrite rule so `react-router` routes resolve to `index.html`.

## Notes

- Chat session IDs are stored per agent in `localStorage`.
- Switching between agents now resets the in-memory transcript and reloads the correct history for that agent.
- The dashboard app in `talon-app` is a separate prototype and is not part of the production deployment path.
