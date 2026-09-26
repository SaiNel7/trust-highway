# Trust Highway — web app

Hello-world starter for the Trust Highway front end.

## Stack

- [Next.js](https://nextjs.org) (App Router) + React + TypeScript
- [Tailwind CSS](https://tailwindcss.com) v4
- [Lucide](https://lucide.dev) icons

## Local development

```bash
cd src
npm install
npm run dev        # http://localhost:3000
```

## Build (static export)

The app is configured for static export (`output: "export"` in `next.config.ts`),
which is what GitHub Pages serves.

```bash
npm run build      # writes static site to src/out
npm run preview    # serve the built site locally
```

## Deploy to GitHub Pages

Deployment is automated by `.github/workflows/deploy.yml`.

One-time setup:

1. In the repo, go to **Settings → Pages**.
2. Under **Build and deployment → Source**, choose **GitHub Actions**.
3. Push to `main` (or run the workflow manually from the **Actions** tab).

For a project repo the site is published at
`https://<owner>.github.io/<repo>/`. The workflow passes that subpath into the
build via `PAGES_BASE_PATH`; `next.config.ts` applies it as `basePath`. Locally
the variable is unset, so the app runs at the site root.