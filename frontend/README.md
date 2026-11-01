# Lost & Found: frontend

Next.js (App Router) + TypeScript + Tailwind + shadcn/ui. It talks to the FastAPI backend only through `src/lib/api.ts`.

```bash
npm ci
npm run dev        # http://localhost:3000  (API expected at NEXT_PUBLIC_API_URL, default http://localhost:8000)
npm run build && npm start
```

Roles: anonymous visitors can browse; signed-in users report items and file claims; `staff` and `admin` get the *Staff*
pages (claim queue, matches, audit log, analytics); only `admin` gets *Users & roles*. The pages hide what a role cannot use, but the
real enforcement is in the API and the database (row-level security and procedures), see `docs/schema.md`.

Layout: `src/app` routes, `src/components` UI (shadcn primitives in `components/ui`), `src/lib` API client, auth and types, `src/hooks` data hooks.
For the full stack, tests and demo accounts see the repository `README.md`.
