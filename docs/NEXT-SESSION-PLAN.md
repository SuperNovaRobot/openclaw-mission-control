# Mission Control: Agent Editor + Task Pipeline Feature Plan

## Context for Next Session

This is the openclaw-mission-control project at `/home/clawdbot/clawd/openclaw-mission-control`. It's a Docker-based stack (FastAPI backend, Next.js frontend, PostgreSQL, Redis) that manages AI agents running on an OpenClaw gateway (`ws://127.0.0.1:18789`).

### Current Architecture
- **Backend**: FastAPI at `backend/app/` — models in `models/`, API routes in `api/`, services in `services/`
- **Frontend**: Next.js at `frontend/src/` — pages in `app/`, components in `components/`
- **Gateway config**: `/home/clawdbot/.openclaw/openclaw.json` — agent list with workspace paths, heartbeat config, model config
- **Agent workspaces**: `/home/clawdbot/.openclaw/workspace-<agent-id>/` containing `HEARTBEAT.md`, `IDENTITY.md`, `SOUL.md`, `TOOLS.md`, `BOOTSTRAP.md`, `AGENTS.md`, `USER.md`, `memory/`
- **Agent auth**: `/home/clawdbot/.openclaw/agents/<agent-id>/agent/auth-profiles.json`
- **Compose**: `compose.yml` — backend uses `network_mode: host`, webhook-worker also uses `network_mode: host`
- **Webhook worker**: Uses custom queue worker (`from app.services.queue_worker import run_worker; run_worker()`) NOT `rq worker`

### Key Files to Reference
- `backend/app/api/board_webhooks.py` — webhook ingestion, currently only notifies lead agent (does NOT create tasks)
- `backend/app/api/tasks.py` — task CRUD and status transitions
- `backend/app/models/agents.py` — Agent model with `openclaw_session_id`, `status`, `heartbeat_config`
- `backend/app/services/openclaw/gateway_rpc.py` — WebSocket RPC to gateway
- `backend/app/services/openclaw/admin_service.py` — agent sync from gateway
- `backend/app/services/webhooks/dispatch.py` — webhook delivery worker
- `frontend/src/app/agents/page.tsx` — agents list page
- `frontend/src/app/boards/[boardId]/edit/page.tsx` — board edit page

---

## Feature 1: Agent Workspace File Editor

### Goal
When viewing an agent in Mission Control, the user should be able to see and edit all the agent's workspace files (HEARTBEAT.md, IDENTITY.md, SOUL.md, TOOLS.md, BOOTSTRAP.md, AGENTS.md, USER.md) and browse the memory directory.

### Requirements
- NO hardcoded file paths — resolve workspace path from gateway config via the agent's `openclaw_session_id` (which contains the agent ID like `agent:mc-<uuid>:main`)
- Read-only view by default, edit mode on click
- Save writes the file back to disk on the host
- Show file list in a sidebar/tab view on the agent detail page
- Memory files (`memory/*.md`) should also be browsable and editable

### Implementation Approach

#### Backend
1. **New API endpoints** under `/api/v1/agents/{agent_id}/files`:
   - `GET /api/v1/agents/{agent_id}/files` — list files in the agent's workspace (reads from disk using workspace path from gateway config)
   - `GET /api/v1/agents/{agent_id}/files/{file_path}` — read a specific file
   - `PUT /api/v1/agents/{agent_id}/files/{file_path}` — write/update a file
   - Must resolve the agent's workspace path by:
     1. Get agent from DB to get `openclaw_session_id`
     2. Extract the openclaw agent ID (e.g., `mc-<uuid>` from `agent:mc-<uuid>:main`)
     3. Look up workspace path from gateway config OR use convention: `/home/clawdbot/.openclaw/workspace-<openclaw-agent-id>/`
   - Path traversal protection — validate file_path stays within workspace directory
   - Also support reading from `agentDir` path for auth-profiles.json (but mask sensitive values like tokens/keys in read responses)

2. **New service** `backend/app/services/openclaw/agent_files.py`:
   - `list_workspace_files(agent_id)` — returns file tree
   - `read_workspace_file(agent_id, relative_path)` — returns content
   - `write_workspace_file(agent_id, relative_path, content)` — writes content
   - Resolves paths from gateway config via RPC or from a cached/stored workspace path on the Agent model

3. **Consider adding `workspace_path` field to Agent model** — populated during provisioning/sync so we don't need to query gateway config every time

#### Frontend
1. **New component** `AgentFileEditor.tsx`:
   - Tab/sidebar listing all workspace files
   - Markdown editor for `.md` files (use a simple textarea or a lightweight markdown editor)
   - JSON editor for `.json` files (with syntax highlighting)
   - Save button that PUTs back to the API
   - Read-only toggle

2. **Add to agent detail page** — new "Files" tab alongside existing Overview/Activity tabs

---

## Feature 2: Task Completion Pipeline (Board-to-Board Automation)

### Goal
When a task completes (moves to `done`) on one board, automatically create a new task in the inbox of another board. This enables multi-board workflows like: ScriptWriting completes a script → automatically creates a "Make Video" task on the VideoMaking board.

### Requirements
- NO hardcoded board IDs, webhook URLs, or task templates
- Fully configurable via the UI: source board + target board + task template
- The pipeline config defines:
  - **Source board** and **trigger status** (e.g., `done`)
  - **Target board** where new task gets created
  - **Task template**: how to map the completed task's data into the new task (title template, description template, assigned agent)
  - **Optional**: which webhook on the target board to use
- The new task should appear in the target board's **inbox** (not just as a message to the lead)
- The pipeline should include data from the completed task (title, description, deliverables, file paths)

### Implementation Approach

#### Data Model
1. **New model** `BoardTaskPipeline` (table: `board_task_pipelines`):
   ```
   id: UUID
   source_board_id: UUID (FK → boards)
   target_board_id: UUID (FK → boards)
   trigger_status: str (default: "done")
   enabled: bool (default: true)
   task_title_template: str (e.g., "Video: {{source_task.title}}")
   task_description_template: text (e.g., "Create video from script. Source: {{source_task.description}}")
   target_agent_id: UUID | null (FK → agents, optional — assign to specific agent)
   target_webhook_id: UUID | null (FK → board_webhooks, optional — if using webhook delivery)
   created_at: datetime
   updated_at: datetime
   ```

2. **Template variables** available in title/description templates:
   - `{{source_task.title}}` — completed task title
   - `{{source_task.description}}` — completed task description
   - `{{source_task.id}}` — task ID for reference
   - `{{source_board.name}}` — source board name
   - `{{source_task.comments}}` — last N comments (agent output/deliverables)
   - `{{source_task.agent_name}}` — agent that completed the task

#### Backend
1. **New API endpoints** under `/api/v1/boards/{board_id}/pipelines`:
   - `GET` — list pipelines for a board (as source)
   - `POST` — create pipeline
   - `PATCH /{pipeline_id}` — update pipeline
   - `DELETE /{pipeline_id}` — delete pipeline

2. **Hook into task status transitions** in `backend/app/api/tasks.py`:
   - When a task moves to the trigger status (e.g., `done`), check for active pipelines on that board
   - For each matching pipeline:
     - Render the title/description templates with task data
     - Create a new task on the target board with status `inbox`
     - If `target_webhook_id` is set, also fire the webhook (which notifies the lead agent)
     - If `target_agent_id` is set, assign the new task to that agent
   - Enqueue this work via the existing Redis queue (don't block the status update)

3. **New service** `backend/app/services/task_pipeline.py`:
   - `evaluate_pipelines(task, new_status)` — find and execute matching pipelines
   - `render_template(template, context)` — simple Jinja2 or string.Template rendering
   - `create_downstream_task(pipeline, source_task)` — creates the task on target board

4. **Update webhook ingestion** (`board_webhooks.py`):
   - Add a new mode/option on webhooks: `auto_create_task: bool`
   - When enabled, the webhook creates an inbox task from the payload instead of just messaging the lead
   - This way the pipeline can use the existing webhook system but with task creation built in

#### Frontend
1. **Pipeline config UI** on the board settings/edit page:
   - List existing pipelines
   - "Add Pipeline" form: select target board, write title/description templates, optionally select target agent
   - Enable/disable toggle
   - Template preview showing available variables

2. **Visual indicator** on tasks that were created by a pipeline (e.g., "From: ScriptWriting board")

---

## Implementation Order

1. **Feature 2 first** (Task Pipeline) — this unblocks the multi-board workflow immediately
   - Start with the data model + API
   - Then the task status hook + pipeline execution
   - Then the frontend config UI

2. **Feature 1 second** (Agent File Editor) — quality of life improvement
   - Start with backend file read/write API
   - Then frontend editor component

## Testing
- Test pipeline: Create a task on ScriptWriting board → move to done → verify new task appears in VideoMaking board inbox
- Test file editor: View agent → open Files tab → edit HEARTBEAT.md → save → verify file on disk changed
- Ensure no hardcoded paths, board IDs, or webhook URLs anywhere

## Git & Version Control

- **Remotes**:
  - `origin` → `git@github.com:BusinessBuilders/openclaw-mission-control.git` (upstream, no push access)
  - `fork` → `git@github.com:SuperNovaRobot/openclaw-mission-control.git` (push here)
- **SSH auth**: SuperNovaRobot SSH key (already configured)
- **Current branch**: `mobile-ui-changes` (pushed to `fork`)
- **IMPORTANT: Before starting work, run `git checkout mobile-ui-changes` to make sure you're on the right branch**
- **Workflow**: Create a new feature branch off `mobile-ui-changes` for these features. Push to `fork` remote, NOT `origin`.
  ```
  git checkout mobile-ui-changes
  git pull fork mobile-ui-changes
  git checkout -b feature/task-pipeline-and-agent-editor
  # ... work ...
  git push fork feature/task-pipeline-and-agent-editor
  ```
- Make clean, focused commits — one per logical change (e.g., separate commits for model, API, frontend, tests)
- **PR target**: `master` branch on `origin` (BusinessBuilders), created from `fork`

### CRITICAL: Never Commit Secrets
- **NEVER** commit API keys, auth tokens, passwords, or credentials to git
- `.env` files contain secrets — they must NEVER be committed
- `backend/.env` is not in `.gitignore` yet — **add it** before doing anything else
- `compose.yml` must use `${ENV_VAR}` references, never inline token values
- `auth-profiles.json` files contain API keys — these live outside the repo in `~/.openclaw/`
- If you see a hardcoded token/key in any file, replace it with an env var reference before committing
- Before every commit, run `git diff --cached` and scan for anything that looks like a key, token, or password
- Files to add to `.gitignore` if not already there: `backend/.env`, `frontend/.env`, `.env.local`, `*.pem`, `*.key`

### Uncommitted Changes to Commit
The compose.yml fix from the previous session needs to be committed:
- Webhook worker: changed from `rq worker` to custom `queue_worker.run_worker()` (the old command used a different queue protocol and never processed webhooks)
- Webhook worker: added `network_mode: host` so it can reach the gateway at localhost
- Webhook worker: updated Redis/DB URLs from Docker DNS (`redis://redis:6379`) to localhost (required for host networking)
- Backend: restored `env_file` reference, kept env var references for AUTH_MODE/LOCAL_AUTH_TOKEN (no hardcoding)

## Notes
- The webhook-worker uses a custom queue worker, NOT `rq worker` — see compose.yml
- Backend and webhook-worker both use `network_mode: host`
- Auth token for local mode is in `backend/.env` (`LOCAL_AUTH_TOKEN`) — NEVER commit this file
- Gateway auth token: stored in `.env` as `OPENCLAW_AUTH_TOKEN` — NEVER commit actual token values
