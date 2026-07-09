# Frontend (Next.js + TypeScript)

The UI for GitHub Resume Assistant. Calls the Flask JSON API in
`resume_assistant/web/` — see the [root README](../README.md) for the full
project overview, running both services locally, and deployment.

```bash
npm install
cp .env.local.example .env.local   # set NEXT_PUBLIC_API_URL if the API isn't local
npm run dev      # http://127.0.0.1:3000, expects the API running (see root README)
npm run build    # production build
npm run lint      # eslint
npm test          # vitest
```
