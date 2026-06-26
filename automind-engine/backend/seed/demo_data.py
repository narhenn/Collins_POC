"""Seed demo data - agents, executions, and activity for impressive demo."""
import asyncio
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from app.core.database import async_session
from app.core.security import hash_password
from app.models.user import User
from app.models.agent import Agent
from app.models.workflow import Workflow
from app.models.execution import Execution, ExecutionNodeLog
from app.models.template import AgentTemplate


DEMO_EMAIL = "prem@goalcert.com"
DEMO_PASSWORD = "goalcert2026"
DEMO_NAME = "Prem"

DEMO_AGENTS = [
    {
        "name": "Sales Lead Hunter",
        "type": "sales",
        "description": "Finds and qualifies B2B leads from tech companies, drafts personalized outreach emails.",
        "status": "active",
        "schedule_cron": "0 9 * * 1-5",
        "workflow": {
            "nodes": [
                {"id": "t1", "type": "trigger", "position": {"x": 250, "y": 0}, "data": {"label": "Weekdays 9am", "config": {"frequency": "daily", "cron": "0 9 * * 1-5"}}},
                {"id": "ws1", "type": "web_search", "position": {"x": 250, "y": 140}, "data": {"label": "Search Tech Leads", "config": {"query": "Singapore tech startups hiring 2026", "max_results": 5, "output_variable": "leads_raw"}}},
                {"id": "ai1", "type": "ai_action", "position": {"x": 250, "y": 280}, "data": {"label": "Qualify & Draft Emails", "config": {"prompt": "From these search results: {leads_raw}\n\nIdentify the top 3 companies that match our ICP (B2B SaaS, 50-500 employees). For each, draft a short personalized outreach email.", "model": "gpt-4o-mini", "max_tokens": 1024, "temperature": 0.7, "output_variable": "qualified_leads"}}},
                {"id": "i1", "type": "integration", "position": {"x": 250, "y": 420}, "data": {"label": "Email Sales Team", "config": {"service": "email", "action": "send", "recipients": "sales@goalcert.com", "subject": "New Qualified Leads - {leads_raw}", "body": "{qualified_leads}"}}},
            ],
            "edges": [
                {"id": "e1", "source": "t1", "target": "ws1"},
                {"id": "e2", "source": "ws1", "target": "ai1"},
                {"id": "e3", "source": "ai1", "target": "i1"},
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1},
        },
    },
    {
        "name": "Content Engine",
        "type": "marketing",
        "description": "Generates weekly LinkedIn posts, Twitter threads, and newsletter content from industry trends.",
        "status": "active",
        "schedule_cron": "0 8 * * 1",
        "workflow": {
            "nodes": [
                {"id": "t1", "type": "trigger", "position": {"x": 250, "y": 0}, "data": {"label": "Monday 8am", "config": {"frequency": "weekly", "cron": "0 8 * * 1"}}},
                {"id": "ws1", "type": "web_search", "position": {"x": 250, "y": 140}, "data": {"label": "Trending AI Topics", "config": {"query": "AI automation trends this week 2026", "max_results": 5, "output_variable": "trends"}}},
                {"id": "ai1", "type": "ai_action", "position": {"x": 250, "y": 280}, "data": {"label": "Generate Content", "config": {"prompt": "Based on these trends: {trends}\n\nCreate:\n1. Three LinkedIn posts (professional tone)\n2. Two Twitter threads (concise, engaging)\n3. One newsletter intro paragraph\n\nMake them about AI automation in business.", "model": "gpt-4o-mini", "max_tokens": 2048, "temperature": 0.8, "output_variable": "content"}}},
                {"id": "i1", "type": "integration", "position": {"x": 250, "y": 420}, "data": {"label": "Send to Marketing", "config": {"service": "email", "action": "send", "recipients": "marketing@goalcert.com", "subject": "Weekly Content Ready", "body": "{content}"}}},
            ],
            "edges": [
                {"id": "e1", "source": "t1", "target": "ws1"},
                {"id": "e2", "source": "ws1", "target": "ai1"},
                {"id": "e3", "source": "ai1", "target": "i1"},
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1},
        },
    },
    {
        "name": "Competitor Monitor",
        "type": "custom",
        "description": "Tracks competitor announcements and product launches, generates intelligence briefs.",
        "status": "active",
        "schedule_cron": "0 10 * * *",
        "workflow": {
            "nodes": [
                {"id": "t1", "type": "trigger", "position": {"x": 250, "y": 0}, "data": {"label": "Daily 10am", "config": {"frequency": "daily", "cron": "0 10 * * *"}}},
                {"id": "ws1", "type": "web_search", "position": {"x": 250, "y": 140}, "data": {"label": "Scan Competitors", "config": {"query": "AI agent platform startup funding launch 2026", "max_results": 8, "output_variable": "competitor_news"}}},
                {"id": "ai1", "type": "ai_action", "position": {"x": 250, "y": 280}, "data": {"label": "Analyze Threats", "config": {"prompt": "Analyze these competitor signals: {competitor_news}\n\nIdentify:\n1. Key threats to our market position\n2. Opportunities we can exploit\n3. Action items for the team\n\nBe specific and actionable.", "model": "gpt-4o-mini", "max_tokens": 1024, "temperature": 0.5, "output_variable": "analysis"}}},
                {"id": "d1", "type": "decision", "position": {"x": 250, "y": 420}, "data": {"label": "High Priority?", "config": {"left_operand": "{analysis}", "operator": "contains", "right_operand": "threat"}}},
                {"id": "esc1", "type": "escalation", "position": {"x": 100, "y": 560}, "data": {"label": "Alert Leadership", "config": {"recipient_email": "prem@goalcert.com", "message_template": "URGENT: Competitor threat detected.\n\n{analysis}"}}},
                {"id": "i1", "type": "integration", "position": {"x": 400, "y": 560}, "data": {"label": "Log Report", "config": {"service": "email", "action": "send", "recipients": "intel@goalcert.com", "subject": "Daily Competitor Brief", "body": "{analysis}"}}},
            ],
            "edges": [
                {"id": "e1", "source": "t1", "target": "ws1"},
                {"id": "e2", "source": "ws1", "target": "ai1"},
                {"id": "e3", "source": "ai1", "target": "d1"},
                {"id": "e4", "source": "d1", "target": "esc1", "sourceHandle": "true", "label": "true"},
                {"id": "e5", "source": "d1", "target": "i1", "sourceHandle": "false", "label": "false"},
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1},
        },
    },
]

# Fake execution data to make dashboard look alive
FAKE_EXECUTIONS = [
    {"status": "success", "duration_ms": 4200, "cost": "0.000312", "hours_ago": 2},
    {"status": "success", "duration_ms": 6800, "cost": "0.000456", "hours_ago": 5},
    {"status": "success", "duration_ms": 3100, "cost": "0.000198", "hours_ago": 8},
    {"status": "success", "duration_ms": 7500, "cost": "0.000521", "hours_ago": 26},
    {"status": "failed", "duration_ms": 1200, "cost": "0.000050", "hours_ago": 30},
    {"status": "success", "duration_ms": 5400, "cost": "0.000389", "hours_ago": 50},
    {"status": "success", "duration_ms": 4900, "cost": "0.000278", "hours_ago": 74},
    {"status": "success", "duration_ms": 8200, "cost": "0.000612", "hours_ago": 98},
]


async def seed_demo():
    async with async_session() as session:
        # Check if demo user exists
        result = await session.execute(select(User).where(User.email == DEMO_EMAIL))
        user = result.scalar_one_or_none()

        if user:
            print(f"Demo user {DEMO_EMAIL} already exists, cleaning up old data...")
            # Delete old agents (cascade deletes workflows + executions)
            old_agents = await session.execute(select(Agent).where(Agent.user_id == user.id))
            for agent in old_agents.scalars().all():
                await session.delete(agent)
            await session.flush()
        else:
            user = User(
                id=uuid.uuid4(),
                email=DEMO_EMAIL,
                password_hash=hash_password(DEMO_PASSWORD),
                name=DEMO_NAME,
            )
            session.add(user)
            await session.flush()
            print(f"Created demo user: {DEMO_EMAIL}")

        now = datetime.now(timezone.utc)

        for i, agent_data in enumerate(DEMO_AGENTS):
            agent = Agent(
                id=uuid.uuid4(),
                user_id=user.id,
                name=agent_data["name"],
                type=agent_data["type"],
                description=agent_data["description"],
                status=agent_data["status"],
                schedule_cron=agent_data.get("schedule_cron"),
                schedule_timezone="Asia/Singapore",
                last_execution_at=now - timedelta(hours=2),
            )
            session.add(agent)
            await session.flush()

            workflow = Workflow(
                id=uuid.uuid4(),
                agent_id=agent.id,
                status="active",
                definition=agent_data["workflow"],
                deployed_at=now - timedelta(days=3),
            )
            session.add(workflow)
            await session.flush()

            # Add fake execution history
            for j, exec_data in enumerate(FAKE_EXECUTIONS[:6 if i == 0 else 4 if i == 1 else 3]):
                started = now - timedelta(hours=exec_data["hours_ago"])
                ended = started + timedelta(milliseconds=exec_data["duration_ms"])
                execution = Execution(
                    id=uuid.uuid4(),
                    agent_id=agent.id,
                    workflow_id=workflow.id,
                    status=exec_data["status"],
                    triggered_by="schedule" if j > 0 else "manual",
                    started_at=started,
                    ended_at=ended,
                    duration_ms=exec_data["duration_ms"],
                    variables={},
                    total_cost=float(exec_data["cost"]),
                )
                session.add(execution)

            await session.flush()
            print(f"  Created agent: {agent_data['name']} with {len(FAKE_EXECUTIONS[:6 if i == 0 else 4])} executions")

        await session.commit()
        print(f"\nDemo ready!")
        print(f"  Login: {DEMO_EMAIL} / {DEMO_PASSWORD}")
        print(f"  URL: http://localhost:3000")


if __name__ == "__main__":
    asyncio.run(seed_demo())
