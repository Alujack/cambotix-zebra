# Zebra public site

Next.js 16 (App Router, TypeScript, Tailwind v4). Server-rendered pages read the public record JSON from `web/api.py`
through `API_URL` (the internal `api` compose service). See the "Public website" section of the repository README.

```bash
npm install
API_URL=http://127.0.0.1:8090 npm run dev   # against a locally exposed api
npm run lint && npm run build
```
