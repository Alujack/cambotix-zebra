# Zebra public site

Next.js 16 (App Router, TypeScript, Tailwind v4). Server-rendered pages read the public record JSON from `web/api.py`
through `API_URL` (the internal `api` compose service). See the "Public website" section of the repository README.

```bash
npm install
npm run dev -- -p 3001                       # api on 127.0.0.1:8091 (API_PORT); 3000 is the Docker site
npm run lint && npm run build
```
