"""Seed agent templates into the database."""
import asyncio
import uuid

from sqlalchemy import select

from app.core.database import async_session, engine
from app.models.template import AgentTemplate


TEMPLATES = [
    {
        "name": "Sales Prospector",
        "description": "Automate lead research, personalized outreach, and meeting scheduling. Finds prospects matching your ICP, drafts personalized emails, and follows up automatically.",
        "type": "sales",
        "icon": "users",
        "color": "blue",
        "features": [
            "Lead research & qualification",
            "Personalized email outreach",
            "Response tracking",
            "Meeting scheduling escalation",
        ],
        "workflow_definition": {
            "nodes": [
                {
                    "id": "trigger-1",
                    "type": "trigger",
                    "position": {"x": 250, "y": 0},
                    "data": {
                        "label": "Daily 9am",
                        "config": {
                            "frequency": "daily",
                            "cron": "0 9 * * *",
                            "timezone": "UTC",
                        },
                    },
                },
                {
                    "id": "ai-1",
                    "type": "ai_action",
                    "position": {"x": 250, "y": 120},
                    "data": {
                        "label": "Research Leads",
                        "config": {
                            "prompt": "You are a B2B sales researcher. Find 5 potential leads matching this Ideal Customer Profile:\n- Industry: SaaS / Technology\n- Company size: 50-500 employees\n- Role: VP Sales, Head of Growth, CEO\n\nFor each lead, provide:\n- Full name\n- Job title\n- Company name\n- A personalized outreach angle based on their company's recent news or product launches\n\nReturn as JSON array with keys: name, title, company, outreach_angle",
                            "model": "gpt-4o-mini",
                            "max_tokens": 1024,
                            "temperature": 0.7,
                            "output_variable": "leads",
                        },
                    },
                },
                {
                    "id": "integration-1",
                    "type": "integration",
                    "position": {"x": 250, "y": 260},
                    "data": {
                        "label": "Send Outreach Emails",
                        "config": {
                            "service": "email",
                            "action": "send",
                            "recipients": "{leads}",
                            "subject": "Quick question about {company}",
                            "body": "Hi {name},\n\nI noticed {outreach_angle}. We help companies like {company} automate their sales outreach and save 20+ hours per week.\n\nWould you be open to a 15-minute chat this week?\n\nBest regards",
                        },
                    },
                },
                {
                    "id": "decision-1",
                    "type": "decision",
                    "position": {"x": 250, "y": 400},
                    "data": {
                        "label": "Emails sent > 0?",
                        "config": {
                            "left_operand": "{emails_sent}",
                            "operator": ">",
                            "right_operand": "0",
                        },
                    },
                },
                {
                    "id": "escalation-1",
                    "type": "escalation",
                    "position": {"x": 100, "y": 540},
                    "data": {
                        "label": "Notify Sales Rep",
                        "config": {
                            "recipient_email": "sales@company.com",
                            "message_template": "Sales Prospector sent {emails_sent} outreach emails to {leads_count} leads. Review responses and schedule meetings for interested prospects.",
                        },
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "trigger-1", "target": "ai-1"},
                {"id": "e2", "source": "ai-1", "target": "integration-1"},
                {"id": "e3", "source": "integration-1", "target": "decision-1"},
                {
                    "id": "e4",
                    "source": "decision-1",
                    "target": "escalation-1",
                    "label": "true",
                    "sourceHandle": "true",
                },
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1},
        },
    },
    {
        "name": "Marketing Campaign Designer",
        "description": "Generate full marketing campaigns including briefs, social media posts, and email content. Runs weekly to keep your content pipeline full.",
        "type": "marketing",
        "icon": "pen-tool",
        "color": "pink",
        "features": [
            "Campaign brief generation",
            "Social media post creation",
            "Multi-platform content",
            "Campaign report delivery",
        ],
        "workflow_definition": {
            "nodes": [
                {
                    "id": "trigger-1",
                    "type": "trigger",
                    "position": {"x": 250, "y": 0},
                    "data": {
                        "label": "Weekly Monday 8am",
                        "config": {
                            "frequency": "weekly",
                            "cron": "0 8 * * 1",
                            "timezone": "UTC",
                        },
                    },
                },
                {
                    "id": "ai-1",
                    "type": "ai_action",
                    "position": {"x": 250, "y": 120},
                    "data": {
                        "label": "Generate Campaign Brief",
                        "config": {
                            "prompt": "Create a weekly marketing campaign brief for a B2B SaaS product.\n\nInclude:\n1. Campaign theme for the week\n2. Key messaging pillars (3 max)\n3. Target audience description\n4. Recommended content types\n5. Call-to-action\n\nFormat as a structured brief that a content team can execute on. Return as JSON with keys: theme, messaging_pillars, audience, content_types, cta",
                            "model": "gpt-4o-mini",
                            "max_tokens": 1024,
                            "temperature": 0.8,
                            "output_variable": "campaign_brief",
                        },
                    },
                },
                {
                    "id": "ai-2",
                    "type": "ai_action",
                    "position": {"x": 250, "y": 260},
                    "data": {
                        "label": "Create Social Posts",
                        "config": {
                            "prompt": "Based on this campaign brief:\n{campaign_brief}\n\nGenerate 5 social media posts:\n- 3 LinkedIn posts (professional, thought-leadership)\n- 2 Twitter/X posts (concise, engaging)\n\nFor each post include: platform, content, hashtags (3 max), and suggested posting time.\n\nReturn as JSON array with keys: platform, content, hashtags, post_time",
                            "model": "gpt-4o-mini",
                            "max_tokens": 1500,
                            "temperature": 0.8,
                            "output_variable": "social_posts",
                        },
                    },
                },
                {
                    "id": "integration-1",
                    "type": "integration",
                    "position": {"x": 250, "y": 400},
                    "data": {
                        "label": "Email Campaign Summary",
                        "config": {
                            "service": "email",
                            "action": "send",
                            "recipients": "marketing@company.com",
                            "subject": "Weekly Campaign Brief & Content Ready",
                            "body": "Hi team,\n\nThis week's campaign brief and content are ready:\n\nTheme: {campaign_brief.theme}\n\nPosts generated: {posts_count}\n\nPlease review and schedule the posts.\n\nBest,\nAUTOMIND Marketing Agent",
                        },
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "trigger-1", "target": "ai-1"},
                {"id": "e2", "source": "ai-1", "target": "ai-2"},
                {"id": "e3", "source": "ai-2", "target": "integration-1"},
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1},
        },
    },
    {
        "name": "Support Receptionist",
        "description": "Classify incoming support emails, draft appropriate responses, and escalate complex issues. Handles FAQs automatically and routes edge cases to humans.",
        "type": "support",
        "icon": "mail",
        "color": "amber",
        "features": [
            "Email classification",
            "Automated FAQ responses",
            "Spam detection",
            "Smart escalation",
        ],
        "workflow_definition": {
            "nodes": [
                {
                    "id": "trigger-1",
                    "type": "trigger",
                    "position": {"x": 250, "y": 0},
                    "data": {
                        "label": "Manual Trigger",
                        "config": {"frequency": "manual"},
                    },
                },
                {
                    "id": "ai-1",
                    "type": "ai_action",
                    "position": {"x": 250, "y": 120},
                    "data": {
                        "label": "Classify Email",
                        "config": {
                            "prompt": "Classify this support email into one of these categories:\n- bug_report: User is reporting a software bug\n- feature_request: User is requesting a new feature\n- question: User has a general question\n- billing: Related to billing or payments\n- spam: Unsolicited or irrelevant message\n\nEmail content: {email_content}\n\nReturn JSON with keys: category, confidence (0-1), summary, suggested_priority (low/medium/high)",
                            "model": "gpt-4o-mini",
                            "max_tokens": 512,
                            "temperature": 0.3,
                            "output_variable": "classification",
                        },
                    },
                },
                {
                    "id": "decision-1",
                    "type": "decision",
                    "position": {"x": 250, "y": 260},
                    "data": {
                        "label": "Is it spam?",
                        "config": {
                            "left_operand": "{classification.category}",
                            "operator": "==",
                            "right_operand": "spam",
                        },
                    },
                },
                {
                    "id": "ai-2",
                    "type": "ai_action",
                    "position": {"x": 400, "y": 400},
                    "data": {
                        "label": "Draft Response",
                        "config": {
                            "prompt": "Draft a helpful, professional support response for this email.\n\nCategory: {classification.category}\nPriority: {classification.suggested_priority}\nSummary: {classification.summary}\nOriginal email: {email_content}\n\nWrite a warm, concise response that addresses the user's concern. If it's a bug report, acknowledge the issue and ask for reproduction steps. If it's a question, provide a helpful answer.",
                            "model": "gpt-4o-mini",
                            "max_tokens": 800,
                            "temperature": 0.5,
                            "output_variable": "draft_response",
                        },
                    },
                },
                {
                    "id": "integration-1",
                    "type": "integration",
                    "position": {"x": 400, "y": 540},
                    "data": {
                        "label": "Send Response",
                        "config": {
                            "service": "email",
                            "action": "send",
                            "recipients": "{sender_email}",
                            "subject": "Re: {email_subject}",
                            "body": "{draft_response}",
                        },
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "trigger-1", "target": "ai-1"},
                {"id": "e2", "source": "ai-1", "target": "decision-1"},
                {
                    "id": "e3",
                    "source": "decision-1",
                    "target": "ai-2",
                    "label": "false",
                    "sourceHandle": "false",
                },
                {"id": "e4", "source": "ai-2", "target": "integration-1"},
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1},
        },
    },
    {
        "name": "Research Analyst",
        "description": "Automated competitive intelligence and market research. Searches the web for industry trends, analyzes competitors, and delivers a structured weekly briefing.",
        "type": "custom",
        "icon": "search",
        "color": "teal",
        "features": [
            "Web research & data gathering",
            "Competitive analysis",
            "Trend identification",
            "Executive briefing delivery",
        ],
        "workflow_definition": {
            "nodes": [
                {
                    "id": "trigger-1",
                    "type": "trigger",
                    "position": {"x": 250, "y": 0},
                    "data": {
                        "label": "Daily 10am",
                        "config": {
                            "frequency": "daily",
                            "cron": "0 10 * * *",
                            "timezone": "UTC",
                        },
                    },
                },
                {
                    "id": "web-1",
                    "type": "web_search",
                    "position": {"x": 250, "y": 120},
                    "data": {
                        "label": "Search Industry News",
                        "config": {
                            "query": "AI enterprise software market trends competitors 2026",
                            "max_results": 10,
                            "output_variable": "search_results",
                        },
                    },
                },
                {
                    "id": "ai-1",
                    "type": "ai_action",
                    "position": {"x": 250, "y": 260},
                    "data": {
                        "label": "Analyze & Summarize",
                        "config": {
                            "prompt": "You are a senior market research analyst. Based on these search results:\n\n{search_results}\n\nProduce a structured competitive intelligence briefing:\n\n1. **Key Market Developments** (top 3 news items with implications)\n2. **Competitor Moves** (any notable launches, funding, partnerships)\n3. **Emerging Trends** (patterns you see forming)\n4. **Risk Alerts** (anything that could impact our business)\n5. **Recommended Actions** (2-3 specific next steps)\n\nBe concise and actionable. Focus on what matters for strategic decision-making.",
                            "model": "gpt-4o-mini",
                            "max_tokens": 1500,
                            "temperature": 0.4,
                            "output_variable": "analysis",
                        },
                    },
                },
                {
                    "id": "decision-1",
                    "type": "decision",
                    "position": {"x": 250, "y": 420},
                    "data": {
                        "label": "Urgent findings?",
                        "config": {
                            "left_operand": "{analysis}",
                            "operator": "contains",
                            "right_operand": "urgent",
                        },
                    },
                },
                {
                    "id": "integration-1",
                    "type": "integration",
                    "position": {"x": 100, "y": 560},
                    "data": {
                        "label": "Email Briefing",
                        "config": {
                            "service": "email",
                            "action": "send",
                            "recipients": "team@company.com",
                            "subject": "Daily Market Intelligence Briefing",
                            "body": "{analysis}",
                        },
                    },
                },
                {
                    "id": "escalation-1",
                    "type": "escalation",
                    "position": {"x": 400, "y": 560},
                    "data": {
                        "label": "Escalate to Leadership",
                        "config": {
                            "recipient_email": "ceo@company.com",
                            "message_template": "URGENT: The Research Analyst agent flagged critical market findings that require immediate attention. Please review the daily briefing.",
                        },
                    },
                },
            ],
            "edges": [
                {"id": "e1", "source": "trigger-1", "target": "web-1"},
                {"id": "e2", "source": "web-1", "target": "ai-1"},
                {"id": "e3", "source": "ai-1", "target": "decision-1"},
                {
                    "id": "e4",
                    "source": "decision-1",
                    "target": "integration-1",
                    "label": "false",
                    "sourceHandle": "false",
                },
                {
                    "id": "e5",
                    "source": "decision-1",
                    "target": "escalation-1",
                    "label": "true",
                    "sourceHandle": "true",
                },
            ],
            "viewport": {"x": 0, "y": 0, "zoom": 1},
        },
    },
]


async def seed_templates():
    """Insert template data if not already present."""
    async with async_session() as session:
        result = await session.execute(select(AgentTemplate))
        existing = result.scalars().all()

        if existing:
            print(f"Templates already seeded ({len(existing)} found). Skipping.")
            return

        for tmpl in TEMPLATES:
            template = AgentTemplate(
                id=uuid.uuid4(),
                name=tmpl["name"],
                description=tmpl["description"],
                type=tmpl["type"],
                workflow_definition=tmpl["workflow_definition"],
                icon=tmpl["icon"],
                color=tmpl["color"],
                features=tmpl["features"],
            )
            session.add(template)

        await session.commit()
        print(f"Seeded {len(TEMPLATES)} agent templates.")


if __name__ == "__main__":
    asyncio.run(seed_templates())
