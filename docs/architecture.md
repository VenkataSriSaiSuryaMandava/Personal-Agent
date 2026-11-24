# Aegis AI Architecture

## Private runtime

A local-first modular monolith for a single Owner.

- Next.js frontend bound to loopback.
- FastAPI backend on the internal Docker network.
- Docker Compose manages both services.
- SQLite schema v6 in a persistent volume.
- Runtime credentials stored outside the repository.
- Argon2id authentication and revocable sessions.
- HttpOnly, SameSite Strict session cookies.
- Trusted backend gateway authentication.

## Public runtime

An isolated Render deployment using shared Guest UI components.

- Runtime-based access restrictions.
- No private database or Owner credentials.
- No live AI inference or Owner authentication.
- Private API routes reject public access.
- No network connection to the private runtime.

## Conversation lifecycle

1. Authenticate the Owner.
2. Validate message and context limits.
3. Enforce cloud authorization and content policy.
4. Submit approved text through the model gateway.
5. Handle sanitized provider errors.
6. Save completed turns only when authorized.
7. Return the response and persistence status.

Conversation retention is disabled by default.
Database transactions enforce the current retention preference.

Saved conversations can be reopened, renamed and deleted.
Concurrent writes are checked using expected turn counts.

Tab-scoped session storage remembers only the active chat ID.
Conversation messages remain in authenticated SQLite storage.

## Security boundaries

- Deny cloud inference by default.
- Runtime configuration sets the authorization boundary.
- Owner settings can restrict runtime permissions.
- Emergency stop blocks new cloud activity.
- Personal and sensitive content is not authorized for cloud AI.
- Content filtering cannot guarantee complete detection.
- AI responses cannot execute external actions.
- No automatic paid-provider fallback.

## Storage

SQLite stores authentication, settings, usage tracking,
security audit events, conversation history and workspace records.

Schema v5 introduced Owner-scoped workspace records.
Schema v6 introduced transactional workspace audit events.

Workspace updates use optimistic revisions. Audit metadata is
written atomically through SQLite triggers. Audit records exclude
workspace content and are not tamper-proof logs.

Database backups are verified before schema upgrades.

Disabling retention stops new saves.
Existing history remains until explicitly deleted.

Restrictive filesystem permissions protect database files.
Application-level encryption is not implemented.

Deleted content may remain in backups or SQLite storage pages.
Secure physical deletion is not guaranteed.

## Current limitations

- No local language models yet.
- No remote Owner access.
- No autonomous background workflows.
- No external action execution.
- No operating-system-level tool sandbox.
- External account integrations are unavailable.
- Saved memories are not automatically included in AI requests.
- Approval records do not authorize external execution.
- Workspace filtering and calendar views operate on loaded records.
- Offset pagination is not a concurrent snapshot.
- No application-level encryption.

## Release workflow

Development branches merge through validated pull requests.
All five development branches synchronize with main.

The deployment branch is promoted only after explicit approval.
Render watches deployment, not main.

## Workspace architecture

Nine functional record workspaces share authenticated CRUD APIs
and a common persistence layer:

- Tasks: local task tracking and completion.
- Jobs: six-stage application pipeline.
- Email: local drafts and archived messages.
- Calendar: local month, week and day views.
- Research: research records and source references.
- Coding: project records and repository references.
- Browser: bookmarks and explicitly confirmed external searches.
- Memory: manually saved local records and storage diagnostics.
- Approvals: manual pending and decision history records.

Owner records persist in private SQLite storage. Guest records
are temporary and do not access private workspace APIs.

The client uses allowlisted same-origin endpoints, bounded
identifiers, pagination and revision values. The server gateway
validates access, request origins and payloads before forwarding
requests to the private backend.

Workspace summaries contain counts, status breakdowns and storage
measurements rather than private record content.

Allocated SQLite pages are not equivalent to memory payload size,
total filesystem usage or AI memory capacity.

## AI provider architecture

The provider registry authorizes Gemini only.
Groq is not implemented, and automatic fallback is disabled.
Provider configuration diagnostics do not prove live availability.

Future development focuses on job intelligence, advanced tasks,
permission-based memory retrieval, controlled approvals and
authorized external integrations.
