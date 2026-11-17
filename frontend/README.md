# Ognex RAG — frontend

React 19 + TypeScript + Vite + Tailwind CSS 4, packaged as a PWA.

```bash
npm install
npm run dev      # http://localhost:5731
npm run build    # type-check + production bundle
```

The dev server binds to your LAN (`host: true`) and proxies `/api/*` to
`http://127.0.0.1:5000` (see `vite.config.ts`), so no CORS setup is needed
locally. To call the backend directly, set `VITE_API_BASE_URL` in `.env`.

Key modules:

- `src/lib/api.ts` — typed API client and streaming reader.
- `src/lib/richText.ts` — splits streamed ` thinking` / `<ref>` blocks.
- `src/pages/ChatPage.tsx` — conversation state, streaming, persistence.
- `src/pages/KnowledgeBasePage.tsx` — PDF ingestion and deletion.
- `public/manifest.webmanifest`, `public/sw.js` — PWA metadata and offline
  shell. Service workers require HTTPS or `localhost`.