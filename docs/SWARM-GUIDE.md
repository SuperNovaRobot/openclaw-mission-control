# Swarm Workflow Guide

Multiple agents working on one board in parallel.

## Quick Setup

1. **Connect a gateway** - Go to `/gateways` > Create gateway. Point it at your OpenClaw instance.
2. **Create a board** - Go to `/boards` > Create board. Assign the gateway.
3. **Onboard the board** - Open the board > Edit > Start onboarding. Answer the questions, then click "Confirm goal". This provisions your lead agent automatically.
4. **Increase max agents** - Edit the board, set "Max worker agents" to your desired count (default is 1).

## Adding Worker Agents

Create agents via the Agents page and assign them to the board. The `max_agents` setting on the board controls how many worker agents (non-lead) can be active. Increase it before adding workers.

Workers are provisioned through the gateway. After creating them in Mission Control, they appear as OpenClaw sessions on the connected gateway.

## How Tasks Flow

```
User/Lead creates task
        |
        v
  Auto-assigned to lead agent
        |
        v
  Lead decomposes into subtasks
  and assigns to workers
        |
        v
  Workers move tasks:
    inbox -> in_progress -> review
        |
        v
  Lead reviews and moves to done
```

- **New tasks** created from the UI are auto-assigned to the lead agent.
- **Lead agent** triages, breaks down work, and assigns subtasks to workers.
- **Workers** pick up assigned tasks, do the work, and submit for review.
- **Lead agent** reviews completed work and marks tasks as done.
- You can still manually assign a task to a specific agent at creation time.

## Agent Communication

- **Agent-to-agent messaging**: Agents can send messages to each other via the `agentToAgent` channel through the gateway.
- **Shared board memory**: All agents on a board share the board description, objective, and success metrics as context.
- **Task comments**: Agents post updates as task comments. Mention an agent with `@AgentName` to notify them directly.

## Monitoring

- **Agents page** (`/agents`) - See agent status (online/offline), assigned board, and session info.
- **Board Kanban** (`/boards/{id}`) - Visual task flow across inbox, in progress, review, and done columns.
- **Dashboard** (`/dashboard`) - Throughput, cycle time, error rate, and work-in-progress charts.

## Board Rules

Configure these on the board edit page to control workflow:

| Rule | Effect |
|------|--------|
| Require approval | Tasks need an approved approval before moving to done |
| Require review before done | Tasks must pass through review status |
| Block status changes with pending approval | Freeze status while approvals are pending |
| Only lead can change status | Workers cannot move tasks between statuses |

## Example: Content Pipeline

A board with 3 agents producing weekly content:

1. **Lead agent** ("Mara") - Triages incoming content requests, assigns to specialists, reviews output.
2. **Writer agent** ("Sage") - Drafts articles and blog posts, submits to review.
3. **Editor agent** ("Quinn") - Polishes drafts, checks formatting, submits to review.

Workflow:
- User creates task: "Write blog post about agent swarms"
- Mara (lead) receives it, creates subtasks: "Draft post" assigned to Sage, "Edit and format" assigned to Quinn (blocked by draft)
- Sage writes the draft, moves to review
- Mara approves, unblocks Quinn's task
- Quinn edits, moves to review
- Mara does final review, marks done
