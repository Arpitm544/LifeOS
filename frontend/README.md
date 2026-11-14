# LifeOS frontend

Next.js App Router, React, TypeScript, plain CSS design tokens, and a locally hosted Manrope font. Implements the [Personal Orbit Figma design](https://www.figma.com/design/3B9mgEaRObGFSzdU91UIig).

## Run

```sh
cd frontend
npm ci
npm run dev
```

Open http://localhost:3000. Use this hostname consistently for Clerk development sessions. Node 22.13 or newer is required; tests use Node's TypeScript stripping support.

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
    chat/                 # Conversation, composer, action cards with Undo
    profile/              # Editable planning preferences
    providers/            # API-backed workspace state (tasks, preferences)
    ui/                   # Original Figma orbital illustrations
  hooks/                  # Clerk-authenticated API client, display name
  lib/                    # API client, backend types, validation and formatting
public/images/            # Original SVG assets downloaded from Figma
tests/                    # API client, validation, timezone filters and preference mapping
```

## What works

- Responsive desktop and mobile navigation across all five screens.
- Create, edit, complete, reopen and delete tasks; title search and time-aware filters.
- Clerk sign-in/sign-up, protected workspace pages, and account/sign-out controls.
- Tasks, preferences, routines, Today and Insights are loaded from and saved to the backend API. Chat requests go to the API, but the conversation on screen is kept only for the current visit.
- Timezone, work/focus/quiet hours, reminder lead, estimate padding and a per-device reduced-motion setting.
- Chat calls `POST /api/chat` and shows action cards with Undo, clarification and confirmation chips.
- Every chat reply includes `steps`, shown as "How LifeOS handled this": what it read from your workspace, how the model understood the message, each tool call with its result (done, asked you, waiting for your OK, failed validation or skipped), the deadline check after any change, and the quick-add fallback when the model is down. Steps are also stored with the assistant message.
- Today opens with a morning brief from `GET /api/brief` (what is due, planned focus time and any deadline at risk) that can be read aloud, plus "LifeOS suggests" nudges with one action each: see fixes for an at-risk deadline, move an overdue task to tomorrow and replan, or plan unscheduled work. The brief is built from fixed templates; a model only translates it when a Chat language is chosen, and a translation that changes any number is discarded. The worker's morning push uses the same brief, so a risk is pushed even on days with no focus blocks.
- Chat is multilingual: speak or type in English, Hindi (including Hinglish), Spanish, French, German, Portuguese, Italian, Dutch, Russian or Japanese and LifeOS replies in that language. The detected spoken language (or a per-device choice in Chat) is sent as `language`; replies are read aloud by a Deepgram voice when `DEEPGRAM_TTS_VOICES` has one for that language, otherwise by the device voice.
- Chat supports microphone transcription and spoken replies through authenticated Deepgram routes when `DEEPGRAM_API_KEY` is configured. Each route reserves a backend quota before contacting Deepgram: five requests per user per minute for transcription and five for speech. The backend and migration 006 must be available; quota errors fail closed.

## Backend

Set `NEXT_PUBLIC_API_URL` (default `http://127.0.0.1:8000`). Every request sends the Clerk session token as `Authorization: Bearer`. Tasks, preferences, routines, Today, Insights and chat all come from the API; only the per-device theme and reduced-motion settings are stored in the browser. Theme is available before sign-in and falls back to the system preference until a choice is saved.

## Integration boundaries

Clerk authentication uses application `app_3M5laGFEp747pBJvQVYMWptOQwT`. Calendar import remains for later. The auth branch is based on the frontend branch.

The Clerk CLI writes development keys to the ignored `frontend/.env.local`; never commit it or print its contents. On another machine, sign into Clerk in your own terminal, then pull this application's development keys:

```sh
cd frontend
npx -y clerk@latest auth login
npx -y clerk@latest link --app app_3M5laGFEp747pBJvQVYMWptOQwT
npx -y clerk@latest env pull
npx -y clerk@latest doctor
```

`src/proxy.ts` initializes Clerk. The server layout for `(workspace)` requires authentication with `auth.protect()`. Sign-in and sign-up remain public and return users to `/today` by default. `UserButton` provides account management and sign-out on desktop and mobile.

Development authentication is configured; production Clerk configuration and domains are not set up. No users are created automatically.

`WorkspaceProvider` loads tasks and preferences from the API and owns the task and preference mutations; screens such as Today, Insights and Chat call the API directly through `useApi()`.

Chat requires localhost or HTTPS for browser-generated idempotency keys. Working and focus windows must stay within one day; quiet hours may span midnight.

System reduced-motion preferences and the Profile toggle (saved on this device) disable animation.
