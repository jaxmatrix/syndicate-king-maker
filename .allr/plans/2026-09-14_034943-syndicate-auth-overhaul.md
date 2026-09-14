# Syndicate Auth Overhaul: Google Sign-In + Registration Funnel

> **For Allr:** Execute task-by-task with verification after each task. Keep tasks sequential — Tasks 1–4 all touch `frontend/index.html` in order.

**Goal:** Make Google Sign-In the only real auth method, turn first sign-in into a proper registration (Google profile + company/use case captured to Firestore), demote guest mode to a session-only escape hatch, and gate every product action (simulation + chat) behind an auth decision.

**Architecture:** Single-file SPA (`frontend/index.html`) on Firebase Auth compat 10.8.0, deployed to Helix as a static zip. Add the Firestore compat SDK. Rework the auth modal into a two-step flow (identity → profile), replace password handlers with `signInWithPopup(GoogleAuthProvider)`, add a chat gate mirroring the existing simulation gate, and propagate `user_id` into simulation payloads (worker already accepts it). Backend untouched.

**Tech Stack:** Firebase compat 10.8.0 (Auth + Firestore), project `intelligence-8c622`, Helix deploy via `/opt/allr/skills/helix/scripts/helix_client.py`.

---

## Decisions (locked with user, 2026-09-14)

1. **Guest mode stays** — explicit escape hatch, session-only (in-memory, resets on reload). First-run modal forces a choice: Google sign-in or guest.
2. **Registration = Google sign-in + lightweight profile** — after first Google sign-in, capture company name + use case into a Firestore `users` collection. No multi-step wizard.

## Prerequisite (external, one-time — flag to Jai)

- **Firebase Console → Authentication → Sign-in method → enable Google provider** for project `intelligence-8c622`. If not enabled, `signInWithPopup` fails with `auth/operation-not-allowed` (the modal's error surface will show it). Support email must be set on the project.
- Authorized domains must include `syndicate-app.jai.allr.work` (already required per CLAUDE.md).
- **Firestore must be created** for project `intelligence-8c622` (Native mode) with a `users` collection. Suggested security rule: `match /users/{uid} { allow read, write: if request.auth.uid == uid; }`.

## Current State (verified in code, 2026-09-14)

- `frontend/index.html` (1430 lines):
  - Lines 21–22: firebase-app-compat.js + firebase-auth-compat.js (no Firestore SDK yet).
  - Lines 661–695: auth modal — email + password inputs (`#auth-email`, `#auth-pass`), `Sign In` → `handleFirebaseLogin()`, `Register` → `handleFirebaseSignUp()`, `Continue in Guest Mode` → `continueAsGuest()`, `#auth-error` div.
  - Lines 699–727: firebaseConfig (project `intelligence-8c622`), `fbAuth`/`currentUser`/`guestModeAllowed` state, `onAuthStateChanged` handler.
  - Lines 732–741: `toggleAuthModal()`, `continueAsGuest()`.
  - Lines 743–759: `handleFirebaseLogin()` (signInWithEmailAndPassword), `handleFirebaseSignUp()` (createUserWithEmailAndPassword) — **both get deleted**.
  - Lines 459–467: session chip (`#user-email`, `#auth-btn` with "Sign In / Register").
  - Lines 1031–1035: `triggerSimulation()` gates on `!currentUser && !guestModeAllowed` → opens modal. **This gate stays.**
  - Line 1303: `sendChatMessage()` — **ungated today**.
  - Line 1056: simulation POST body — no `user_id` today.
- `backend/worker.py` line 82: already reads `t.get("user_id", "guest")` — no backend change needed.
- `test_suite.py`: 4 tests (`test_01_backend_health` … `test_04_live_helix_frontend`).

## Target State

- Modal offers exactly two paths: **Sign in with Google** (primary, gold) and **Continue in Guest Mode (limited, session-only)**.
- Password fields, password Sign In, and password Register are gone.
- After first Google sign-in: profile step (company + use case) → `users/{uid}` doc in Firestore. Returning users skip it (`lastSeenAt` bumped instead).
- `sendChatMessage()` gets the same gate as `triggerSimulation()`.
- Simulation payloads carry `user_id` (email, or `guest`).
- CLAUDE.md invariant #3 updated to match.

---

## Task 1 — Load Firestore SDK + rewrite modal HTML

**Files:**
- Modify: `frontend/index.html` line 22 (SDK), lines 661–695 (modal)

**Steps:**
1. After line 22, add: `<script src="https://www.gstatic.com/firebasejs/10.8.0/firebase-firestore-compat.js"></script>`
2. Initialize Firestore in the init block (Task 2): `fbDb = firebase.firestore();`
3. Replace modal body (lines 661–695) per this contract — keep `#auth-modal` / `.modal-overlay` / `.modal-box` / `.modal-close` wrappers and existing class names (`btn btn-gold`, `btn-tonal`, `input-label`, `input-field`, `input-group`) exactly:
   - Header unchanged: brand-logo "S", h3 "Sign in to Syndicate".
   - Subline: "Registration is instant with Google. Or explore in guest mode."
   - **Identity step** (`#auth-step-identity`): one full-width gold button, inline 4-color Google "G" SVG (18px) + "Sign in with Google", `onclick="handleGoogleSignIn()"`. Below it, full-width tonal button "Continue in Guest Mode (limited, session-only)", `onclick="continueAsGuest()"`.
   - **Profile step** (`#auth-step-profile`, hidden by default): heading "Complete your registration", subline "Tell us who's operating this workspace." Fields: company name text input (`#profile-company`, placeholder "Company / Fund / Studio"), use case select (`#profile-usecase`) with options: Site Selection, Market Research, Competitive Intelligence, Deal Sourcing, Other. Submit button (gold, "Enter Syndicate") → `saveProfile()`. Skip link ("Skip for now") → `saveProfile(true)`.
   - `#auth-error` div kept as-is.
   - **Removed entirely:** `#auth-email`, `#auth-pass`, both password buttons.
4. Add a small `#user-photo` `<img>` (24px, round) inside `#user-display` before `#user-email`; keep it `display:none` by default.

**Verify:** open the page locally in a browser or `python3 -m http.server`; modal shows Google + Guest only; no console errors from the new SDK tag.

## Task 2 — Replace auth JS: Google sign-in + Firestore profile + UI state

**Files:**
- Modify: `frontend/index.html` script section 1 (lines 698–759)

**Function contracts (replace `handleFirebaseLogin` / `handleFirebaseSignUp` entirely):**

- State: keep `fbAuth`, `currentUser`, `guestModeAllowed`; add `fbDb = null`, `guestSessionId = null`.
- `firebase.initializeApp(firebaseConfig)` try/catch stays. Inside the try, after `fbAuth = firebase.auth()`: `fbDb = firebase.firestore();`
- `onAuthStateChanged(user)`: set `currentUser = user`; call `updateAuthUI()`; if user → `ensureProfileDoc(user)`.
- `updateAuthUI()`:
  - Signed in: `#user-email` = email; `#user-photo` src = photoURL, shown (null-check both — element is new); `#auth-btn` = "Sign Out" → `fbAuth.signOut()`.
  - Signed out + guest: `#user-email` = "Guest Mode (Session Only)".
  - Signed out, no guest: "Not Signed In".
  - `#auth-btn` label when signed out: "Sign in with Google", bound to `handleGoogleSignIn()`. Use clean innerHTML with the `material-symbols-outlined` span — no malformed markup.
- `handleGoogleSignIn()`:
  - Guard: `if (!fbAuth) return continueAsGuest();`
  - `const provider = new firebase.auth.GoogleAuthProvider(); provider.setCustomParameters({ prompt: 'select_account' });`
  - `fbAuth.signInWithPopup(provider)` → on resolve: `closeAuthModal()` (catch silently).
  - Catch: if `err.code === 'auth/popup-closed-by-user'` or `'auth/cancelled-popup-request'` → silent. If `'auth/popup-blocked'` → retry with `fbAuth.signInWithRedirect(provider)`. Else → human-readable message in `#auth-error` (e.g. operation-not-allowed → "Google sign-in is not enabled yet for this Firebase project.").
  - Never leave the modal open with a stale error: clear `#auth-error` whenever the modal opens.
- `continueAsGuest()`: `guestModeAllowed = true; guestSessionId = 'guest:' + crypto.randomUUID().slice(0,8);` close modal; `updateAuthUI()`. Session-only — no persistence (document in Task 5).
- `showProfileStep()`: toggle modal steps — hide `#auth-step-identity`, show `#auth-step-profile`. Called from `ensureProfileDoc` when the doc is new.
- `ensureProfileDoc(user)`: `fbDb.collection('users').doc(user.uid).get()` → if not exists → `showProfileStep()` (re-open modal with profile step); if exists → `doc.ref.update({ lastSeenAt: serverTimestamp-ish })` (use `firebase.firestore.FieldValue.serverTimestamp()`), silent.
- `saveProfile(skipped)`:
  - Build `{ email: currentUser.email, displayName: currentUser.displayName, photoURL: currentUser.photoURL, company: skipped ? '' : #profile-company.value.trim(), useCase: skipped ? 'skipped' : #profile-usecase.value, createdAt: serverTimestamp, lastSeenAt: serverTimestamp, sessionId: guestSessionId || null }`.
  - `fbDb.collection('users').doc(currentUser.uid).set(data)` → close modal, chat bubble: "Welcome, {displayName || email}. Registration complete." On error → `#auth-error` message, stay on step.
- `toggleAuthModal()`: unchanged behavior + clear `#auth-error` + reset to identity step unless mid-profile (keep it simple: reset to identity step; `ensureProfileDoc` will re-route new users).

**Verify:** in-browser: Google popup opens; sign-in lands signed-in (chip shows email + photo); first sign-in shows profile step; Firestore `users/{uid}` doc appears with company/useCase; Sign Out works; reload → guest cleared.

## Task 3 — Gate the chat + propagate user_id

**Files:**
- Modify: `frontend/index.html` — `sendChatMessage()` (~line 1303), `triggerSimulation()` payload (~line 1039)

**Steps:**
1. Top of `sendChatMessage()`, before reading input: mirror the simulation gate —
   `if (!currentUser && !guestModeAllowed) { toggleAuthModal(); return; }`
2. In `triggerSimulation()` payload object, add: `user_id: currentUser ? currentUser.email : (guestSessionId || 'guest')`.
3. In `sendChatMessage()` fetch body, add the same `user_id` field (backend accepts extra keys in `{message, context}` body — verify with a quick POST to `127.0.0.1:8090/api/chat`; if FastAPI model rejects unknown keys, extend the pydantic model in `backend/server.py` with `user_id: str = "guest"`).

**Verify:** signed-out + no guest → chat input submit opens modal; guest can chat; signed-in chat POST body includes email.

## Task 4 — Remove dead code

**Files:**
- Modify: `frontend/index.html`

**Steps:**
1. Delete `handleFirebaseLogin()` and `handleFirebaseSignUp()` bodies (replaced in Task 2).
2. Search for any remaining `auth-email` / `auth-pass` / `signInWithEmail` / `createUserWithEmail` references → must be zero.
3. `grep -c "handleGoogleSignIn\|continueAsGuest\|saveProfile\|ensureProfileDoc" frontend/index.html` → each defined exactly once, referenced correctly.

## Task 5 — Update CLAUDE.md (project rules stay truthful)

**Files:**
- Modify: `/opt/data/syndicate/CLAUDE.md`

**Steps:**
1. Invariant #3 → "Auth gate: `triggerSimulation()` AND `sendChatMessage()` must check `currentUser || guestModeAllowed` and open the auth modal otherwise. Guest mode is session-only (in-memory flag, resets on reload) and explicitly limited."
2. Replace the "Firebase auth" mentions: Google Sign-In is the only real provider (password auth removed); registration captures company + use case into Firestore `users/{uid}`.
3. Add pitfall: "Google provider must stay enabled in Firebase Console (project `intelligence-8c622`); popup-blocked falls back to `signInWithRedirect`."

## Task 6 — Verification

**Steps:**
1. `npm --prefix /opt/data/syndicate/mastra run test` → all 4 tests pass (backend health, global sim, chat, live Helix frontend). Note: backend + worker must be running (`/opt/hermes/.venv/bin/python3 backend/server.py` in background, worker likewise) — the suite hits live endpoints.
2. Static sanity: `node -e` or `python3 - <<'EOF'` parse of index.html for balanced script tags and presence of new function names; zero references to removed identifiers.
3. Live smoke (after deploy, Task 7): open https://syndicate-app.jai.allr.work — modal appears with Google button; guest flow works; simulation runs as guest and as signed-in user; Firestore gets a `users` doc on first Google sign-in.

## Task 7 — Deploy to Helix

**Steps:**
1. `python3 /opt/allr/skills/helix/scripts/helix_client.py zip /opt/data/syndicate/frontend /tmp/syndicate_app.zip` (zip contents, not the directory).
2. `python3 /opt/allr/skills/helix/scripts/helix_client.py update cf126906-b884-47b3-a1d8-aec3b9d44dd3 /tmp/syndicate_app.zip "v2: Google-only auth + registration profile + chat gate"`.
3. Deploys are synchronous (~60s) — never retry while one is in flight. Confirm via `versions` / live URL.

---

## Risks & Tradeoffs

- **Firebase Console dependency:** Google provider + Firestore creation are manual, external steps. Until done, Google button errors with `auth/operation-not-allowed` — the modal surfaces it, and the error message should name the exact fix.
- **Existing password users:** anyone registered with email/password today can't log in with that credential anymore. Same-email Google accounts resolve to a different `uid` (new Firestore doc). At current pre-launch traffic this is acceptable; no migration code by design.
- **Popup blockers:** handled with redirect fallback (`signInWithRedirect`); the compat SDK processes redirect results automatically on load.
- **Firestore in open test mode:** ship the `users/{uid}` rule in the same sitting — default test-mode rules expire in 30 days.
- **Chat gate UX:** returning guests must re-accept guest mode after reload — intentional (registration pressure), confirmed with user.

## Open Items (none blocking)

- Email capture for guests: not in scope (guest was explicitly kept as no-friction escape hatch).
- Firestore security rules deployment via API vs Console: Console is fine for one collection; revisit at scale.
