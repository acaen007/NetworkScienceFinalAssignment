# ManyWorlds Prototype

Welcome to the **ManyWorlds** prototype.  This repository is a monorepo that contains
both the user‑facing applications (web and mobile) and the back‑end services
needed to ingest and serve scientific content.  The goal of this prototype is
to provide a working foundation that you can clone, run locally with one
command, and iteratively extend into a production‑ready system.

## Repository layout

```
manyworlds/
├─ apps/
│  ├─ web/                      # Next.js web application (App Router)
│  └─ app/                      # Expo/React Native app using Expo Router
├─ services/
│  ├─ ingestion/                # FastAPI service for ingesting sources
│  └─ nlp/                      # FastAPI service for embeddings/RAG
├─ packages/
│  ├─ ui/                       # Shared UI components
│  ├─ theme/                    # Design tokens (colors, spacing)
│  └─ api/                      # Placeholder for shared API client
├─ infra/
│  ├─ docker-compose.yml        # Local development infrastructure
│  └─ migrations/               # Placeholder for SQL migrations
├─ .github/workflows/           # CI configuration
├─ turbo.json                   # Turborepo pipeline definition
├─ package.json                 # Workspace definitions and scripts
└─ .env.local                   # Environment variables for services
```

### apps/web

The Next.js application lives in `apps/web` and uses the App Router (introduced
in Next.js 13 and refined in 14).  It renders server components by default
and provides a simple landing page with a 2D scientist avatar at the top.  The
avatar serves as a placeholder for a future 3D speaking avatar.  Menu links
lead to pages for **Views**, **Papers**, and **Interviews**.  These pages
currently display placeholder text; you can replace them with data from the
API client in `packages/api` once your endpoints are ready.

### apps/app

The mobile application lives in `apps/app` and is built with Expo and
Expo Router.  It shares UI primitives with the web via the `packages/ui`
package.  The home screen mirrors the web landing page: it shows the same
avatar, the project title, a tagline, and a horizontal menu for **Views**,
**Papers**, and **Interviews**.  Each link navigates to a placeholder
screen.  Because the app uses React Native Web internally, you can even
render it on the web via `expo`’s web support.

### services

Two FastAPI services, **ingestion** and **nlp**, are defined under the
`services/` directory.  These services are extremely minimal right now—each
exposes a single root endpoint that returns a greeting.  In a real system,
the ingestion service would accept a DOI or URL, parse and chunk the
document, embed its contents, and store metadata in Postgres and Meilisearch
via Celery workers.  The NLP service would handle embedding lookups, RAG
responses, and classification.  Adding those features is a matter of
expanding the FastAPI routers and hooking them up to your database and queue.

### packages

* **@manyworlds/ui** holds shared UI components.  For now it contains a
  simple `Avatar` component that displays an image with rounded corners.
  As the project grows you can move other universal components here (e.g.
  buttons, cards, list items).
* **@manyworlds/theme** exposes design tokens like colors and spacing.  These
  can be imported by both web and mobile apps to ensure consistent styling.
* **@manyworlds/api** contains a placeholder API client.  Replace the
  implementation with a generated OpenAPI client or tRPC hooks once your
  back‑end endpoints are defined.

### infra

The `infra/docker-compose.yml` file defines the infrastructure needed to run
the prototype locally: Postgres 16 with `pgvector`, Redis, Meilisearch,
MinIO for object storage, and the two FastAPI services.  An environment file
`.env.local` at the root contains the connection strings and secrets used by
these services.  To spin up everything at once, run:

```sh
docker compose -f infra/docker-compose.yml up -d
```

## Getting started

1. **Install dependencies**.  This repo uses **pnpm** and **Turborepo**
   workspaces for JavaScript/TypeScript packages and `uv` for Python.  Start
   by installing the JS dependencies:

   ```sh
   pnpm install
   ```

2. **Start the infrastructure**.  Make sure Docker is running on your
   machine, then launch Postgres, Redis, Meilisearch, MinIO, and the FastAPI
   services in the background:

   ```sh
   docker compose -f infra/docker-compose.yml up -d
   ```

3. **Run the web app**.  From the repository root, run:

   ```sh
   pnpm --filter web dev
   ```

   The Next.js application should start at http://localhost:3000.  Navigate to
   see the landing page with the 2D scientist avatar and menu.  As you
   implement API routes, update the pages under `apps/web/app` to fetch data.

4. **Run the mobile app**.  In another terminal, run:

   ```sh
   pnpm --filter app start
   ```

   This command opens Expo Dev Tools.  You can run the app on an iOS
   simulator, Android emulator, or a real device.  The screens mirror the
   web experience and will later connect to the same API.

## Roadmap to a demoable V1

The skeleton is intentionally light, but it provides a clear path toward a
demoable V1:

1. **Implement the data model**.  Use the starter tables described in the
   monorepo overview to create SQL migrations under `infra/migrations`.  Add
   SQLModel or SQLAlchemy models in your Python services and connect to
   Postgres using the `DATABASE_URL` in `.env.local`.

2. **Build ingestion workflows**.  Expand the ingestion service to accept
   URLs/DOIs via a POST endpoint.  Use Celery workers to fetch and parse
   documents, compute embeddings (via OpenAI or another provider), and store
   chunks, sources, and statements.  Index metadata in Meilisearch to enable
   full‑text search.

3. **Expose API endpoints**.  In the Next.js application, create Route
   Handlers (`app/api/.../route.ts`) that call into your FastAPI services or
   directly into Postgres and Meilisearch.  Start with endpoints to list
   people, topics, views, and sources.  Update the pages in
   `apps/web/app` and `apps/app/app` to consume these endpoints via the
   shared API client in `packages/api`.

4. **Add authentication**.  Integrate Auth.js (NextAuth) on the web side
   using session cookies.  For the mobile app, implement the OAuth code
   exchange pattern described in the system overview and expose an
   `/api/auth/exchange` endpoint that mints a JWT for the app.  Store tokens
   securely using Expo Secure Store or MMKV.

5. **Upgrade the avatar**.  The current avatar is a simple 2D illustration
   stored in `apps/web/public/avatar.png` and `apps/app/assets/avatar.png`.
   To add a 3D speaking avatar, consider integrating a WebGL or Three.js
   component on the web and a corresponding React Native module on mobile.
   Load and animate a 3D model, then connect it to speech synthesis and
   recognition services so that users can interact with it.

6. **Enhance the UI/UX**.  Replace the inline styles in the current pages
   with components from your UI library (`packages/ui`) and design tokens
   from `packages/theme`.  Use animations via Framer Motion on the web and
   Reanimated/Moti on mobile to create a polished experience.

7. **Testing and CI/CD**.  Add unit and integration tests for your React
   components (using Jest and React Testing Library), API routes, and Python
   services.  Update the GitHub Actions workflow under `.github/workflows` to
   run these tests and build artifacts on every pull request.  Deploy the
   web app to Vercel and the services to Fly.io or Render.

This skeleton should give you a firm foundation on which to build the
ManyWorlds project.  Feel free to adjust the stack or structure to suit your
team’s preferences, but keep the monorepo layout in mind to maximize code
sharing and maintainability.