# Aegis AI Architecture

## Private runtime

A local-first modular monolith for a single Owner.

- Next.js frontend bound to loopback.
- FastAPI backend on the internal Docker network.
- Docker Compose manages both services.
- SQLite schema v4 in a persistent volume.
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
security audit events and conversation history.

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
- Non-assistant workspaces remain incomplete integrations.

## Release workflow

Development branches merge through validated pull requests.
All five development branches synchronize with main.

The deployment branch is promoted only after explicit approval.
Render watches deployment, not main.

Future work includes local model support, persistent tasks,
memory, scoped approvals and controlled external integrations.
