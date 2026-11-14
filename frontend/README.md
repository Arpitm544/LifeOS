# LifeOS frontend

Next.js App Router, React, TypeScript, plain CSS design tokens, and a locally hosted Manrope font. Implements the [Personal Orbit Figma design](https://www.figma.com/design/3B9mgEaRObGFSzdU91UIig).

## Run

```sh
cd frontend
npm ci
npm run dev
```

Open http://127.0.0.1:3000. Node 22 or newer is recommended; tests use Node's TypeScript stripping support.

```sh
npm run typecheck
npm test
npm run build
```

## Structure

```text
src/
  app/                    # Routes: today, chat, tasks, insights, profile
    globals.css           # Shared tokens, component styling, responsive layouts
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
- Browser-local persistence for tasks and preferences, with validation and visible storage errors.
- Name, timezone, work/focus/quiet hours, protected evenings and reduced-motion settings.
- Browser speech recognition with a 30-second limit, editable transcript, permission/error states, and optional spoken preview. Audio is not recorded by LifeOS; the browser speech provider may process it remotely.
- Sample AI conversation and explicit save-as-task/Undo actions. Chat is **not connected to an LLM** and does not infer dates or execute scheduling. Messages remain in memory for the current visit to Chat.

## Integration boundaries

No authentication, API, database, reminder worker, AI provider, or calendar integration is implemented. Sign-in belongs to the authentication teammate. Do not add provider secrets to this frontend.

`WorkspaceProvider` currently owns browser-local mutations. Replace these actions with authenticated backend calls when endpoints are available. The planned chat endpoint is `POST /api/chat` with `{ text, source: "text" | "voice", client_tz }` and a Clerk session bearer token; follow `docs/PRD.md` for the full backend response contract. Keep token acquisition at that integration boundary.

All scheduling, capacity and historical analytics shown are labeled sample data. Applying estimate padding saves a preference; it does not claim to recalculate a real plan. P1–P3 badges in this frontend preview use the selected importance; the backend priority engine will supply actual scores.

Voice needs browser support and microphone permission; use localhost or HTTPS. System reduced-motion preferences and the Profile toggle disable animation. The three Figma SVGs retain their source geometry and render in their original Today, voice and Profile slots; animation is applied to their wrapper.
