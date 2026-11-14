# LifeOS frontend

Next.js App Router, React, TypeScript, plain CSS design tokens, and a locally hosted Manrope font. Implements the [Personal Orbit Figma design](https://www.figma.com/design/3B9mgEaRObGFSzdU91UIig).

## Run

```sh
cd frontend
npm ci
npm run dev
```

Open http://localhost:3000. Use this hostname consistently for Clerk development sessions. Node 22.6 or newer is required; tests use Node's TypeScript stripping support.

```sh
npm run typecheck
npm test
npm run build
```

## Structure

```text
src/
  app/
    (workspace)/        # Protected routes: today, chat, tasks, insights, profile
    sign-in/             # Public Clerk sign-in
    sign-up/             # Public Clerk sign-up
    globals.css          # Shared tokens, component styling, responsive layouts
  components/
    layout/               # App shell, desktop/mobile navigation, page heading
    tasks/                # Task cards and create/edit form
    chat/                 # Conversation, composer, voice panel
    profile/              # Editable planning preferences
    providers/            # Browser-local workspace state and persistence
    ui/                   # Original Figma orbital illustrations
  hooks/                  # Browser speech recognition lifecycle
  lib/                    # Types, sample data, validation and formatting
public/images/            # Original SVG assets downloaded from Figma
tests/                    # Validation, timezone filters and storage checks
```

## What works

- Responsive desktop and mobile navigation across all five screens.
- Create, edit, complete, reopen and delete tasks; title search and time-aware filters.
- Clerk sign-in/sign-up, protected workspace pages, and account/sign-out controls.
- Browser-local persistence for tasks and preferences, isolated by Clerk user ID, with validation and visible storage errors.
- Name, timezone, work/focus/quiet hours, protected evenings and reduced-motion settings.
- Browser speech recognition with a 30-second limit, editable transcript, permission/error states, and optional spoken preview. Audio is not recorded by LifeOS; the browser speech provider may process it remotely.
- Sample AI conversation and explicit save-as-task/Undo actions. Chat is **not connected to an LLM** and does not infer dates or execute scheduling. Messages remain in memory for the current visit to Chat.

## Integration boundaries

Clerk authentication uses application `app_3M5laGFEp747pBJvQVYMWptOQwT`. The API, database, reminder worker, AI provider, and calendar integrations remain for later. The auth branch is based on the frontend branch.

The Clerk CLI writes development keys to the ignored `frontend/.env.local`; never commit it or print its contents. On another machine, sign into Clerk in your own terminal, then pull this application's development keys:

```sh
cd frontend
npx -y clerk@latest auth login
npx -y clerk@latest link --app app_3M5laGFEp747pBJvQVYMWptOQwT
npx -y clerk@latest env pull
npx -y clerk@latest doctor
```

`src/proxy.ts` initializes Clerk. The server layout for `(workspace)` requires authentication with `auth.protect()`. Sign-in and sign-up remain public and return users to `/today` by default. `UserButton` provides account management and sign-out on desktop and mobile.

Tasks and preferences remain browser-local, not cloud-synced. Each signed-in user gets a separate storage key. The previous anonymous demo storage is preserved but is not automatically imported into an account. This avoids assigning one person's demo workspace to another person. Local browser storage is not a substitute for backend authorization or protection on shared browser profiles.

Development authentication is configured; production Clerk configuration and domains are not set up. No users are created automatically.

`WorkspaceProvider` currently owns browser-local mutations. Replace these actions with authenticated backend calls when endpoints are available. The planned chat endpoint is `POST /api/chat` with `{ text, source: "text" | "voice", client_tz }` and a Clerk session bearer token; follow `docs/PRD.md` for the full backend response contract. Keep token acquisition at that integration boundary.

All scheduling, capacity and historical analytics shown are labeled sample data. Applying estimate padding saves a preference; it does not claim to recalculate a real plan. P1–P3 badges in this frontend preview use the selected importance; the backend priority engine will supply actual scores.

Task creation and chat require localhost or HTTPS for browser-generated IDs. Working and focus windows currently must stay within one day; quiet hours may span midnight. Sample task deadlines are fixed in November 2026 and remain overdue after those dates.

Voice needs browser support and microphone permission; use localhost or HTTPS. System reduced-motion preferences and the Profile toggle disable animation. The three Figma SVGs retain their source geometry and render in their original Today, voice and Profile slots; animation is applied to their wrapper.
