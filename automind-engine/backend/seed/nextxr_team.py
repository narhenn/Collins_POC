"""Seed NextXR team demo data - 8 agents across Finance, Marketing, CEO, Strategy, and Sales."""
import asyncio
import random
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from app.core.database import async_session
from app.core.security import hash_password
from app.models.user import User
from app.models.agent import Agent
from app.models.workflow import Workflow
from app.models.execution import Execution, ExecutionNodeLog


DEMO_EMAIL = "prem@nextxr.io"
DEMO_PASSWORD = "nextxr2026"
DEMO_NAME = "Prem"


# ---------------------------------------------------------------------------
# Agent 1: Finance - Budget Tracker
# ---------------------------------------------------------------------------
AGENT_FINANCE_BUDGET = {
    "name": "Finance - Budget Tracker",
    "type": "custom",
    "description": "Daily budget status report across all three NextXR product launches. Tracks cloud infra, API costs, dev team spend, and flags overruns.",
    "status": "active",
    "schedule_cron": "0 9 * * 1-5",
    "workflow": {
        "nodes": [
            {
                "id": "t1",
                "type": "trigger",
                "position": {"x": 250, "y": 0},
                "data": {
                    "label": "Weekdays 9am",
                    "config": {
                        "frequency": "daily",
                        "cron": "0 9 * * 1-5",
                        "timezone": "Asia/Singapore",
                    },
                },
            },
            {
                "id": "ai1",
                "type": "ai_action",
                "position": {"x": 250, "y": 160},
                "data": {
                    "label": "Generate Budget Report",
                    "config": {
                        "prompt": (
                            "You are the Finance Manager at NextXR. Generate today's budget status report for our three product launches.\n\n"
                            "Products:\n"
                            "1) GoalCert AutoMind - $50K budget, launched June 2026, tracking cloud infra costs (AWS/Railway ~$500/mo), "
                            "API costs (OpenAI ~$200/mo), dev team costs.\n"
                            "2) GoalCert Scenario Generator - $30K budget, VM infrastructure costs, LLM API for scenario generation.\n"
                            "3) NextXR Digital Twin - $80K budget, 3D rendering infrastructure, Unity licenses, hosting.\n\n"
                            "For each product, estimate current month spend, remaining budget, and flag any overruns. "
                            "Include a summary table and highlight any items requiring immediate attention. Return as a structured report."
                        ),
                        "model": "gpt-4o-mini",
                        "max_tokens": 1500,
                        "temperature": 0.4,
                        "output_variable": "budget_report",
                    },
                },
            },
            {
                "id": "i1",
                "type": "integration",
                "position": {"x": 250, "y": 340},
                "data": {
                    "label": "Email Budget Report",
                    "config": {
                        "service": "email",
                        "action": "send",
                        "recipients": "prem@nextxr.io",
                        "subject": "Daily Budget Status Report - {date}",
                        "body": "{budget_report}",
                    },
                },
            },
        ],
        "edges": [
            {"id": "e1", "source": "t1", "target": "ai1"},
            {"id": "e2", "source": "ai1", "target": "i1"},
        ],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    },
}


# ---------------------------------------------------------------------------
# Agent 2: Finance - ROI Analyst
# ---------------------------------------------------------------------------
AGENT_FINANCE_ROI = {
    "name": "Finance - ROI Analyst",
    "type": "custom",
    "description": "Weekly ROI projections with market data for all three products. Calculates revenue forecasts, break-even timelines, and CAC estimates.",
    "status": "active",
    "schedule_cron": "0 8 * * 1",
    "workflow": {
        "nodes": [
            {
                "id": "t1",
                "type": "trigger",
                "position": {"x": 250, "y": 0},
                "data": {
                    "label": "Monday 8am",
                    "config": {
                        "frequency": "weekly",
                        "cron": "0 8 * * 1",
                        "timezone": "Asia/Singapore",
                    },
                },
            },
            {
                "id": "ws1",
                "type": "web_search",
                "position": {"x": 250, "y": 150},
                "data": {
                    "label": "Market Research",
                    "config": {
                        "query": "GoalCert cybersecurity training market size 2026 digital twin platform pricing enterprise",
                        "max_results": 8,
                        "output_variable": "search_results",
                    },
                },
            },
            {
                "id": "ai1",
                "type": "ai_action",
                "position": {"x": 250, "y": 310},
                "data": {
                    "label": "Calculate ROI Projections",
                    "config": {
                        "prompt": (
                            "You are the ROI Analyst at NextXR. Based on market data: {search_results}.\n\n"
                            "Calculate the ROI projections for our three products:\n"
                            "1) GoalCert AutoMind - $99/mo SaaS, target 200 customers Y1.\n"
                            "2) Scenario Generator - $5K/enterprise deal, target 20 enterprise clients.\n"
                            "3) Digital Twin - $2K/mo enterprise, target 50 clients.\n\n"
                            "Calculate:\n"
                            "- Revenue projections (monthly and annual)\n"
                            "- Break-even timeline for each product\n"
                            "- Customer acquisition cost estimates\n"
                            "- Gross margin analysis\n"
                            "- Sensitivity analysis (pessimistic / base / optimistic)\n\n"
                            "Provide a weekly ROI brief with clear recommendations."
                        ),
                        "model": "gpt-4o-mini",
                        "max_tokens": 2048,
                        "temperature": 0.4,
                        "output_variable": "roi_brief",
                    },
                },
            },
            {
                "id": "i1",
                "type": "integration",
                "position": {"x": 250, "y": 480},
                "data": {
                    "label": "Email ROI Brief",
                    "config": {
                        "service": "email",
                        "action": "send",
                        "recipients": "prem@nextxr.io",
                        "subject": "Weekly ROI Brief - {date}",
                        "body": "{roi_brief}",
                    },
                },
            },
        ],
        "edges": [
            {"id": "e1", "source": "t1", "target": "ws1"},
            {"id": "e2", "source": "ws1", "target": "ai1"},
            {"id": "e3", "source": "ai1", "target": "i1"},
        ],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    },
}


# ---------------------------------------------------------------------------
# Agent 3: Marketing - Content Creator
# ---------------------------------------------------------------------------
AGENT_MARKETING_CONTENT = {
    "name": "Marketing - Content Creator",
    "type": "marketing",
    "description": "Creates LinkedIn posts, Twitter threads, and blog content for all three NextXR products on Mon/Wed/Fri.",
    "status": "active",
    "schedule_cron": "0 8 * * 1,3,5",
    "workflow": {
        "nodes": [
            {
                "id": "t1",
                "type": "trigger",
                "position": {"x": 250, "y": 0},
                "data": {
                    "label": "MWF 8am",
                    "config": {
                        "frequency": "daily",
                        "cron": "0 8 * * 1,3,5",
                        "timezone": "Asia/Singapore",
                    },
                },
            },
            {
                "id": "ws1",
                "type": "web_search",
                "position": {"x": 250, "y": 150},
                "data": {
                    "label": "Trend Research",
                    "config": {
                        "query": "AI agent automation trends 2026 cybersecurity training platform enterprise",
                        "max_results": 6,
                        "output_variable": "trends",
                    },
                },
            },
            {
                "id": "ai1",
                "type": "ai_action",
                "position": {"x": 250, "y": 310},
                "data": {
                    "label": "Generate Content",
                    "config": {
                        "prompt": (
                            "You are the Content Marketing Lead at NextXR. Based on these trends: {trends}.\n\n"
                            "Create content for this week:\n"
                            "1) One LinkedIn post about GoalCert AutoMind (highlight the AI agent builder, no-code workflow, real execution - "
                            "not just chatbot, agents that actually DO things).\n"
                            "2) One LinkedIn post about our Scenario Generator (red team/blue team cybersec training, MITRE ATT&CK mapped "
                            "scenarios, LLM-driven dynamic simulations).\n"
                            "3) One Twitter thread (5 tweets) about the future of AI agents in enterprise - reference AutoMind as the solution.\n"
                            "4) One short blog intro paragraph about NextXR's product suite and our vision for autonomous enterprise agents.\n\n"
                            "Tone: professional but approachable, slightly edgy. We're a startup, not a boring enterprise vendor. "
                            "Include relevant hashtags. Each piece should have a clear CTA."
                        ),
                        "model": "gpt-4o-mini",
                        "max_tokens": 2500,
                        "temperature": 0.8,
                        "output_variable": "content",
                    },
                },
            },
            {
                "id": "d1",
                "type": "decision",
                "position": {"x": 250, "y": 490},
                "data": {
                    "label": "All 3 products covered?",
                    "config": {
                        "left_operand": "{content}",
                        "operator": "contains",
                        "right_operand": "Digital Twin",
                    },
                },
            },
            {
                "id": "i1",
                "type": "integration",
                "position": {"x": 250, "y": 650},
                "data": {
                    "label": "Email to Marketing",
                    "config": {
                        "service": "email",
                        "action": "send",
                        "recipients": "marketing@nextxr.io",
                        "subject": "Content Ready for Review - {date}",
                        "body": "{content}",
                    },
                },
            },
        ],
        "edges": [
            {"id": "e1", "source": "t1", "target": "ws1"},
            {"id": "e2", "source": "ws1", "target": "ai1"},
            {"id": "e3", "source": "ai1", "target": "d1"},
            {"id": "e4", "source": "d1", "target": "i1", "sourceHandle": "true", "label": "true"},
            {"id": "e5", "source": "d1", "target": "i1", "sourceHandle": "false", "label": "false"},
        ],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    },
}


# ---------------------------------------------------------------------------
# Agent 4: Marketing - Campaign Manager
# ---------------------------------------------------------------------------
AGENT_MARKETING_CAMPAIGN = {
    "name": "Marketing - Campaign Manager",
    "type": "marketing",
    "description": "Weekly campaign planning with go-to-market strategy, cold outreach templates, and channel-specific activity schedules.",
    "status": "active",
    "schedule_cron": "0 9 * * 1",
    "workflow": {
        "nodes": [
            {
                "id": "t1",
                "type": "trigger",
                "position": {"x": 250, "y": 0},
                "data": {
                    "label": "Monday 9am",
                    "config": {
                        "frequency": "weekly",
                        "cron": "0 9 * * 1",
                        "timezone": "Asia/Singapore",
                    },
                },
            },
            {
                "id": "ws1",
                "type": "web_search",
                "position": {"x": 250, "y": 150},
                "data": {
                    "label": "GTM Research",
                    "config": {
                        "query": "product hunt launch strategy 2026 SaaS B2B go-to-market AI platform",
                        "max_results": 6,
                        "output_variable": "gtm_research",
                    },
                },
            },
            {
                "id": "ai1",
                "type": "ai_action",
                "position": {"x": 250, "y": 310},
                "data": {
                    "label": "Plan Weekly Campaign",
                    "config": {
                        "prompt": (
                            "You are the Campaign Manager at NextXR. Based on GTM research: {gtm_research}.\n\n"
                            "Plan this week's marketing campaign. Current status:\n"
                            "- GoalCert AutoMind is in beta (June 2026 launch)\n"
                            "- Scenario Generator has 4 scenarios built (8 Red Team, 4 Blue Team, 4 SOC planned)\n"
                            "- Digital Twin has demo ready for GoalCert\n\n"
                            "Create a detailed weekly campaign plan:\n"
                            "1) Target audience for each product (job titles, company types, pain points)\n"
                            "2) Channels: LinkedIn, ProductHunt, IndieHackers, HackerNews, email outreach, Twitter/X\n"
                            "3) Key messages per product with value propositions\n"
                            "4) Daily schedule of activities (Mon-Fri)\n"
                            "5) KPIs to track (impressions, clicks, signups, demos booked)\n\n"
                            "Focus on pre-launch buzz for AutoMind. We need 20 demos booked this month."
                        ),
                        "model": "gpt-4o-mini",
                        "max_tokens": 2048,
                        "temperature": 0.7,
                        "output_variable": "campaign_plan",
                    },
                },
            },
            {
                "id": "ai2",
                "type": "ai_action",
                "position": {"x": 250, "y": 490},
                "data": {
                    "label": "Draft Cold Outreach",
                    "config": {
                        "prompt": (
                            "Based on the campaign plan: {campaign_plan}.\n\n"
                            "Draft 3 cold outreach email templates for potential enterprise customers:\n\n"
                            "a) AI AUTOMATION (AutoMind target):\n"
                            "   - For VP Engineering / CTO who wastes time on repetitive workflows\n"
                            "   - Highlight: no-code agent builder, real execution (not just chat), scheduled automation\n\n"
                            "b) CYBERSECURITY TRAINING (Scenario Generator target):\n"
                            "   - For CISO / Security Director who needs to train SOC analysts\n"
                            "   - Highlight: MITRE ATT&CK mapped, red/blue team simulations, LLM-driven dynamic scenarios\n\n"
                            "c) DIGITAL TWIN (Digital Twin target):\n"
                            "   - For CTO / VP Engineering in manufacturing/logistics/smart buildings\n"
                            "   - Highlight: 3D simulation, real-time monitoring, predictive analytics\n\n"
                            "Each email: compelling subject line, under 150 words, reference their specific pain point, "
                            "clear CTA for a 15-min demo call. Make them feel personal, not template-y."
                        ),
                        "model": "gpt-4o-mini",
                        "max_tokens": 2048,
                        "temperature": 0.7,
                        "output_variable": "outreach_templates",
                    },
                },
            },
            {
                "id": "i1",
                "type": "integration",
                "position": {"x": 250, "y": 670},
                "data": {
                    "label": "Email Campaign Plan",
                    "config": {
                        "service": "email",
                        "action": "send",
                        "recipients": "marketing@nextxr.io",
                        "subject": "Weekly Campaign Plan + Outreach Templates - {date}",
                        "body": "CAMPAIGN PLAN:\n\n{campaign_plan}\n\n---\n\nOUTREACH TEMPLATES:\n\n{outreach_templates}",
                    },
                },
            },
        ],
        "edges": [
            {"id": "e1", "source": "t1", "target": "ws1"},
            {"id": "e2", "source": "ws1", "target": "ai1"},
            {"id": "e3", "source": "ai1", "target": "ai2"},
            {"id": "e4", "source": "ai2", "target": "i1"},
        ],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    },
}


# ---------------------------------------------------------------------------
# Agent 5: CEO - Executive Dashboard
# ---------------------------------------------------------------------------
AGENT_CEO_DASHBOARD = {
    "name": "CEO - Executive Dashboard",
    "type": "custom",
    "description": "Morning and evening executive briefing with market news, competitive landscape, KPI tracking, and risk flags.",
    "status": "active",
    "schedule_cron": "0 8,17 * * 1-5",
    "workflow": {
        "nodes": [
            {
                "id": "t1",
                "type": "trigger",
                "position": {"x": 250, "y": 0},
                "data": {
                    "label": "8am & 5pm Weekdays",
                    "config": {
                        "frequency": "daily",
                        "cron": "0 8,17 * * 1-5",
                        "timezone": "Asia/Singapore",
                    },
                },
            },
            {
                "id": "ws1",
                "type": "web_search",
                "position": {"x": 250, "y": 150},
                "data": {
                    "label": "Scan Market News",
                    "config": {
                        "query": "NextXR GoalCert AI agent platform startup news funding 2026",
                        "max_results": 8,
                        "output_variable": "market_news",
                    },
                },
            },
            {
                "id": "ai1",
                "type": "ai_action",
                "position": {"x": 250, "y": 310},
                "data": {
                    "label": "Generate Executive Briefing",
                    "config": {
                        "prompt": (
                            "You are the CEO's AI assistant at NextXR (CEO: Prem). Generate the executive daily briefing.\n\n"
                            "Market news context: {market_news}\n\n"
                            "Products in market:\n"
                            "1) GoalCert AutoMind - agentic AI platform, just launched beta. Competitors: Zapier, Make, LangGraph, CrewAI, "
                            "Relevance AI, OpenAI Agents SDK.\n"
                            "2) Scenario Generator - cybersec training with red/blue team simulations. Competitors: Immersive Labs, "
                            "HackTheBox, TryHackMe, RangeForce.\n"
                            "3) Digital Twin - 3D simulation platform. Competitors: NVIDIA Omniverse, AWS IoT TwinMaker, Azure Digital Twins.\n\n"
                            "Include:\n"
                            "a) MARKET NEWS: Relevant news to our products from search results\n"
                            "b) COMPETITIVE LANDSCAPE: Updates on competitor activity, new features, funding rounds\n"
                            "c) KPI SUMMARY: Target 20 demos this month, current pipeline estimate, website traffic trends\n"
                            "d) ACTION ITEMS: Top 3 things CEO should focus on today\n"
                            "e) RISK FLAGS: Anything requiring immediate attention\n\n"
                            "Keep it concise, scannable, and actionable. Use bullet points."
                        ),
                        "model": "gpt-4o-mini",
                        "max_tokens": 2048,
                        "temperature": 0.5,
                        "output_variable": "briefing",
                    },
                },
            },
            {
                "id": "d1",
                "type": "decision",
                "position": {"x": 250, "y": 490},
                "data": {
                    "label": "Urgent items?",
                    "config": {
                        "left_operand": "{briefing}",
                        "operator": "contains",
                        "right_operand": "URGENT",
                    },
                },
            },
            {
                "id": "esc1",
                "type": "escalation",
                "position": {"x": 80, "y": 650},
                "data": {
                    "label": "Alert CEO - Urgent",
                    "config": {
                        "recipient_email": "prem@nextxr.io",
                        "message_template": "URGENT ALERT: Competitive threat or critical issue detected.\n\n{briefing}",
                    },
                },
            },
            {
                "id": "i1",
                "type": "integration",
                "position": {"x": 420, "y": 650},
                "data": {
                    "label": "Email Daily Briefing",
                    "config": {
                        "service": "email",
                        "action": "send",
                        "recipients": "prem@nextxr.io",
                        "subject": "Executive Daily Briefing - {date}",
                        "body": "{briefing}",
                    },
                },
            },
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
}


# ---------------------------------------------------------------------------
# Agent 6: Strategy - Market Intelligence
# ---------------------------------------------------------------------------
AGENT_STRATEGY_INTEL = {
    "name": "Strategy - Market Intelligence",
    "type": "custom",
    "description": "Daily strategic analysis of competitive moves, market signals, opportunities, and threats across the AI agent, cybersec, and digital twin markets.",
    "status": "active",
    "schedule_cron": "0 10 * * 1-5",
    "workflow": {
        "nodes": [
            {
                "id": "t1",
                "type": "trigger",
                "position": {"x": 250, "y": 0},
                "data": {
                    "label": "Weekdays 10am",
                    "config": {
                        "frequency": "daily",
                        "cron": "0 10 * * 1-5",
                        "timezone": "Asia/Singapore",
                    },
                },
            },
            {
                "id": "ws1",
                "type": "web_search",
                "position": {"x": 250, "y": 150},
                "data": {
                    "label": "Market Intelligence Scan",
                    "config": {
                        "query": "AI agent platform funding 2026 cybersecurity simulation market digital twin enterprise growth",
                        "max_results": 10,
                        "output_variable": "market_data",
                    },
                },
            },
            {
                "id": "ai1",
                "type": "ai_action",
                "position": {"x": 250, "y": 310},
                "data": {
                    "label": "Strategic Analysis",
                    "config": {
                        "prompt": (
                            "You are the Chief Strategy Officer at NextXR. Analyze today's market intelligence: {market_data}.\n\n"
                            "Produce a strategic analysis covering:\n\n"
                            "1) COMPETITIVE MOVES:\n"
                            "   - What are Zapier, Make, LangGraph, CrewAI, OpenAI doing in the AI agent space?\n"
                            "   - Any new agent platforms launched?\n"
                            "   - Cybersec training moves: Immersive Labs, HackTheBox, TryHackMe\n"
                            "   - Digital twin: NVIDIA Omniverse, AWS, Azure updates\n\n"
                            "2) MARKET SIGNALS:\n"
                            "   - Enterprise AI adoption trends and spending\n"
                            "   - Cybersecurity spending trends and compliance drivers\n"
                            "   - Digital twin market growth and industry verticals\n\n"
                            "3) STRATEGIC OPPORTUNITIES:\n"
                            "   - Gaps in the market we can exploit with AutoMind\n"
                            "   - Underserved segments for Scenario Generator\n"
                            "   - Digital Twin partnerships or vertical plays\n\n"
                            "4) THREATS:\n"
                            "   - Big tech encroachment, pricing pressure, talent competition\n"
                            "   - Anything that could undermine our position\n\n"
                            "5) RECOMMENDATIONS:\n"
                            "   - Top 3 strategic actions for this week\n"
                            "   - Resource allocation suggestions\n"
                            "   - Partnership opportunities to pursue"
                        ),
                        "model": "gpt-4o-mini",
                        "max_tokens": 2500,
                        "temperature": 0.5,
                        "output_variable": "strategic_brief",
                    },
                },
            },
            {
                "id": "i1",
                "type": "integration",
                "position": {"x": 250, "y": 490},
                "data": {
                    "label": "Email Strategic Brief",
                    "config": {
                        "service": "email",
                        "action": "send",
                        "recipients": "prem@nextxr.io",
                        "subject": "Daily Strategic Brief - {date}",
                        "body": "{strategic_brief}",
                    },
                },
            },
        ],
        "edges": [
            {"id": "e1", "source": "t1", "target": "ws1"},
            {"id": "e2", "source": "ws1", "target": "ai1"},
            {"id": "e3", "source": "ai1", "target": "i1"},
        ],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    },
}


# ---------------------------------------------------------------------------
# Agent 7: Sales - Lead Hunter
# ---------------------------------------------------------------------------
AGENT_SALES_HUNTER = {
    "name": "Sales - Lead Hunter",
    "type": "sales",
    "description": "Daily enterprise lead discovery, qualification, and personalized outreach drafting. Focused on Singapore/SEA companies.",
    "status": "active",
    "schedule_cron": "0 9 * * 1-5",
    "workflow": {
        "nodes": [
            {
                "id": "t1",
                "type": "trigger",
                "position": {"x": 250, "y": 0},
                "data": {
                    "label": "Weekdays 9am",
                    "config": {
                        "frequency": "daily",
                        "cron": "0 9 * * 1-5",
                        "timezone": "Asia/Singapore",
                    },
                },
            },
            {
                "id": "ws1",
                "type": "web_search",
                "position": {"x": 250, "y": 150},
                "data": {
                    "label": "Find Enterprise Leads",
                    "config": {
                        "query": "Singapore enterprise AI automation cybersecurity training companies hiring digital twin customers manufacturing 2026",
                        "max_results": 10,
                        "output_variable": "leads_raw",
                    },
                },
            },
            {
                "id": "ai1",
                "type": "ai_action",
                "position": {"x": 250, "y": 310},
                "data": {
                    "label": "Qualify Leads",
                    "config": {
                        "prompt": (
                            "You are the Sales Lead Hunter at NextXR. From these search results: {leads_raw}.\n\n"
                            "Identify 5 potential enterprise leads for our products. For each lead:\n"
                            "1) Company name and what they do\n"
                            "2) Which NextXR product fits them:\n"
                            "   - AutoMind: companies needing AI workflow automation, repetitive tasks, report generation\n"
                            "   - Scenario Generator: companies with cybersecurity teams, SOC analysts, compliance requirements\n"
                            "   - Digital Twin: manufacturing, logistics, smart buildings, infrastructure companies\n"
                            "3) Decision maker to target (VP Engineering, CISO, CTO, COO)\n"
                            "4) Personalized outreach angle based on their specific pain points\n"
                            "5) Estimated deal size (AutoMind: $1.2K-5K/yr, ScenGen: $5K-20K/deal, Digital Twin: $24K-100K/yr)\n\n"
                            "Prioritize Singapore/SEA companies. Include company website if found."
                        ),
                        "model": "gpt-4o-mini",
                        "max_tokens": 2048,
                        "temperature": 0.6,
                        "output_variable": "qualified_leads",
                    },
                },
            },
            {
                "id": "ai2",
                "type": "ai_action",
                "position": {"x": 250, "y": 490},
                "data": {
                    "label": "Draft Outreach Emails",
                    "config": {
                        "prompt": (
                            "Draft a personalized cold email for the top 3 leads: {qualified_leads}.\n\n"
                            "For each email:\n"
                            "- Subject line: compelling, specific to their company (not generic)\n"
                            "- Opening: reference something specific about their company or industry\n"
                            "- Pain point: describe the problem they likely face\n"
                            "- Solution: how our specific product solves it (be concrete, not vague)\n"
                            "- Social proof: mention we're backed by NTU ecosystem / Singapore startup scene\n"
                            "- CTA: 15-min demo call, suggest specific times this week\n\n"
                            "Keep each email under 150 words. Make it feel like a human wrote it, not a template. "
                            "No corporate jargon. Direct and respectful of their time."
                        ),
                        "model": "gpt-4o-mini",
                        "max_tokens": 1500,
                        "temperature": 0.7,
                        "output_variable": "outreach_emails",
                    },
                },
            },
            {
                "id": "i1",
                "type": "integration",
                "position": {"x": 250, "y": 670},
                "data": {
                    "label": "Email to Sales",
                    "config": {
                        "service": "email",
                        "action": "send",
                        "recipients": "sales@nextxr.io",
                        "subject": "Today's Qualified Leads + Outreach Drafts - {date}",
                        "body": "QUALIFIED LEADS:\n\n{qualified_leads}\n\n---\n\nDRAFT OUTREACH EMAILS:\n\n{outreach_emails}",
                    },
                },
            },
        ],
        "edges": [
            {"id": "e1", "source": "t1", "target": "ws1"},
            {"id": "e2", "source": "ws1", "target": "ai1"},
            {"id": "e3", "source": "ai1", "target": "ai2"},
            {"id": "e4", "source": "ai2", "target": "i1"},
        ],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    },
}


# ---------------------------------------------------------------------------
# Agent 8: Sales - Pipeline Manager
# ---------------------------------------------------------------------------
AGENT_SALES_PIPELINE = {
    "name": "Sales - Pipeline Manager",
    "type": "sales",
    "description": "End-of-day sales pipeline report with stage tracking, demo schedule, revenue forecast, and target recovery plans.",
    "status": "active",
    "schedule_cron": "0 17 * * 1-5",
    "workflow": {
        "nodes": [
            {
                "id": "t1",
                "type": "trigger",
                "position": {"x": 250, "y": 0},
                "data": {
                    "label": "Weekdays 5pm",
                    "config": {
                        "frequency": "daily",
                        "cron": "0 17 * * 1-5",
                        "timezone": "Asia/Singapore",
                    },
                },
            },
            {
                "id": "ai1",
                "type": "ai_action",
                "position": {"x": 250, "y": 160},
                "data": {
                    "label": "Generate Pipeline Report",
                    "config": {
                        "prompt": (
                            "You are the Sales Pipeline Manager at NextXR. Generate the end-of-day pipeline report.\n\n"
                            "CEO target: 20 demos per month. We are in month 1 of active sales.\n\n"
                            "Products and pricing:\n"
                            "- AutoMind: $99/mo SaaS (self-serve) or $499/mo Pro (managed)\n"
                            "- Scenario Generator: $5K/enterprise deal (one-time setup + $500/mo)\n"
                            "- Digital Twin: $2K/mo enterprise subscription\n\n"
                            "Create a realistic month-1 startup pipeline report:\n\n"
                            "1) PIPELINE SUMMARY: Leads at each stage\n"
                            "   - Prospect (cold leads identified)\n"
                            "   - Contacted (outreach sent)\n"
                            "   - Demo Scheduled (meeting booked)\n"
                            "   - Proposal Sent (pricing shared)\n"
                            "   - Closed Won / Closed Lost\n\n"
                            "2) THIS WEEK'S DEMO SCHEDULE: List upcoming demos with company names and products\n\n"
                            "3) FOLLOW-UP ACTIONS: Who needs follow-up and what type\n\n"
                            "4) REVENUE FORECAST: This month projected vs target, pipeline weighted value\n\n"
                            "5) DEALS AT RISK: Stalled deals, ghosted prospects, competitive losses\n\n"
                            "Use realistic numbers for a startup in month 1. Be honest about gaps."
                        ),
                        "model": "gpt-4o-mini",
                        "max_tokens": 2048,
                        "temperature": 0.5,
                        "output_variable": "pipeline_report",
                    },
                },
            },
            {
                "id": "d1",
                "type": "decision",
                "position": {"x": 250, "y": 360},
                "data": {
                    "label": "On track for 20 demos?",
                    "config": {
                        "left_operand": "{pipeline_report}",
                        "operator": "contains",
                        "right_operand": "behind",
                    },
                },
            },
            {
                "id": "esc1",
                "type": "escalation",
                "position": {"x": 80, "y": 520},
                "data": {
                    "label": "Alert CEO - Behind Target",
                    "config": {
                        "recipient_email": "prem@nextxr.io",
                        "message_template": (
                            "SALES ALERT: We are behind on demo targets for this month.\n\n"
                            "Recovery plan needed. See full pipeline report below.\n\n{pipeline_report}"
                        ),
                    },
                },
            },
            {
                "id": "i1",
                "type": "integration",
                "position": {"x": 420, "y": 520},
                "data": {
                    "label": "Email Pipeline Report",
                    "config": {
                        "service": "email",
                        "action": "send",
                        "recipients": "sales@nextxr.io",
                        "subject": "EOD Pipeline Report - {date}",
                        "body": "{pipeline_report}",
                    },
                },
            },
        ],
        "edges": [
            {"id": "e1", "source": "t1", "target": "ai1"},
            {"id": "e2", "source": "ai1", "target": "d1"},
            {"id": "e3", "source": "d1", "target": "esc1", "sourceHandle": "true", "label": "true"},
            {"id": "e4", "source": "d1", "target": "i1", "sourceHandle": "false", "label": "false"},
        ],
        "viewport": {"x": 0, "y": 0, "zoom": 1},
    },
}


# ---------------------------------------------------------------------------
# All agents list
# ---------------------------------------------------------------------------
ALL_AGENTS = [
    AGENT_FINANCE_BUDGET,
    AGENT_FINANCE_ROI,
    AGENT_MARKETING_CONTENT,
    AGENT_MARKETING_CAMPAIGN,
    AGENT_CEO_DASHBOARD,
    AGENT_STRATEGY_INTEL,
    AGENT_SALES_HUNTER,
    AGENT_SALES_PIPELINE,
]


# ---------------------------------------------------------------------------
# Fake execution history per agent (varied to look realistic)
# ---------------------------------------------------------------------------
EXEC_PROFILES = [
    # Agent 0: Finance Budget - daily, 5 runs
    [
        {"status": "success", "duration_ms": 3800, "cost": "0.000245", "hours_ago": 3, "triggered_by": "schedule"},
        {"status": "success", "duration_ms": 4100, "cost": "0.000261", "hours_ago": 27, "triggered_by": "schedule"},
        {"status": "success", "duration_ms": 3600, "cost": "0.000232", "hours_ago": 51, "triggered_by": "schedule"},
        {"status": "success", "duration_ms": 4500, "cost": "0.000289", "hours_ago": 75, "triggered_by": "schedule"},
        {"status": "success", "duration_ms": 3900, "cost": "0.000251", "hours_ago": 99, "triggered_by": "manual"},
    ],
    # Agent 1: Finance ROI - weekly, 3 runs
    [
        {"status": "success", "duration_ms": 7200, "cost": "0.000478", "hours_ago": 4, "triggered_by": "schedule"},
        {"status": "success", "duration_ms": 6800, "cost": "0.000445", "hours_ago": 172, "triggered_by": "schedule"},
        {"status": "failed", "duration_ms": 2100, "cost": "0.000089", "hours_ago": 340, "triggered_by": "schedule"},
    ],
    # Agent 2: Marketing Content - MWF, 6 runs
    [
        {"status": "success", "duration_ms": 8400, "cost": "0.000612", "hours_ago": 2, "triggered_by": "schedule"},
        {"status": "success", "duration_ms": 7900, "cost": "0.000578", "hours_ago": 50, "triggered_by": "schedule"},
        {"status": "success", "duration_ms": 9100, "cost": "0.000689", "hours_ago": 98, "triggered_by": "schedule"},
        {"status": "success", "duration_ms": 8200, "cost": "0.000601", "hours_ago": 146, "triggered_by": "schedule"},
        {"status": "failed", "duration_ms": 3400, "cost": "0.000145", "hours_ago": 194, "triggered_by": "schedule"},
        {"status": "success", "duration_ms": 8700, "cost": "0.000634", "hours_ago": 242, "triggered_by": "manual"},
    ],
    # Agent 3: Marketing Campaign - weekly, 3 runs
    [
        {"status": "success", "duration_ms": 11200, "cost": "0.000834", "hours_ago": 5, "triggered_by": "schedule"},
        {"status": "success", "duration_ms": 10800, "cost": "0.000801", "hours_ago": 173, "triggered_by": "schedule"},
        {"status": "success", "duration_ms": 12100, "cost": "0.000912", "hours_ago": 341, "triggered_by": "manual"},
    ],
    # Agent 4: CEO Dashboard - twice daily, 6 runs
    [
        {"status": "success", "duration_ms": 9600, "cost": "0.000712", "hours_ago": 2, "triggered_by": "schedule"},
        {"status": "success", "duration_ms": 8900, "cost": "0.000667", "hours_ago": 11, "triggered_by": "schedule"},
        {"status": "success", "duration_ms": 9200, "cost": "0.000689", "hours_ago": 26, "triggered_by": "schedule"},
        {"status": "success", "duration_ms": 10100, "cost": "0.000745", "hours_ago": 35, "triggered_by": "schedule"},
        {"status": "success", "duration_ms": 8800, "cost": "0.000656", "hours_ago": 50, "triggered_by": "schedule"},
        {"status": "success", "duration_ms": 9500, "cost": "0.000701", "hours_ago": 59, "triggered_by": "manual"},
    ],
    # Agent 5: Strategy Intel - daily, 4 runs
    [
        {"status": "success", "duration_ms": 10500, "cost": "0.000789", "hours_ago": 3, "triggered_by": "schedule"},
        {"status": "success", "duration_ms": 9800, "cost": "0.000734", "hours_ago": 27, "triggered_by": "schedule"},
        {"status": "success", "duration_ms": 11200, "cost": "0.000845", "hours_ago": 51, "triggered_by": "schedule"},
        {"status": "failed", "duration_ms": 4200, "cost": "0.000178", "hours_ago": 75, "triggered_by": "schedule"},
    ],
    # Agent 6: Sales Lead Hunter - daily, 5 runs
    [
        {"status": "success", "duration_ms": 12800, "cost": "0.000956", "hours_ago": 4, "triggered_by": "schedule"},
        {"status": "success", "duration_ms": 11500, "cost": "0.000867", "hours_ago": 28, "triggered_by": "schedule"},
        {"status": "success", "duration_ms": 13200, "cost": "0.000989", "hours_ago": 52, "triggered_by": "schedule"},
        {"status": "success", "duration_ms": 12100, "cost": "0.000912", "hours_ago": 76, "triggered_by": "schedule"},
        {"status": "success", "duration_ms": 11800, "cost": "0.000878", "hours_ago": 100, "triggered_by": "manual"},
    ],
    # Agent 7: Sales Pipeline - daily, 4 runs
    [
        {"status": "success", "duration_ms": 8200, "cost": "0.000612", "hours_ago": 2, "triggered_by": "schedule"},
        {"status": "success", "duration_ms": 7800, "cost": "0.000578", "hours_ago": 26, "triggered_by": "schedule"},
        {"status": "success", "duration_ms": 8600, "cost": "0.000645", "hours_ago": 50, "triggered_by": "schedule"},
        {"status": "success", "duration_ms": 9100, "cost": "0.000689", "hours_ago": 74, "triggered_by": "manual"},
    ],
]


async def seed_nextxr_team():
    """Create NextXR team demo: user + 8 agents + execution history."""
    async with async_session() as session:
        # ---------------------------------------------------------------
        # 1. User setup (idempotent)
        # ---------------------------------------------------------------
        result = await session.execute(select(User).where(User.email == DEMO_EMAIL))
        user = result.scalar_one_or_none()

        if user:
            print(f"User {DEMO_EMAIL} already exists, cleaning up old agents...")
            old_agents = await session.execute(select(Agent).where(Agent.user_id == user.id))
            for agent in old_agents.scalars().all():
                await session.delete(agent)
            await session.flush()
            # Update password in case it changed
            user.password_hash = hash_password(DEMO_PASSWORD)
            user.name = DEMO_NAME
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
            print(f"Created user: {DEMO_EMAIL}")

        now = datetime.now(timezone.utc)

        # ---------------------------------------------------------------
        # 2. Create all 8 agents with workflows and execution history
        # ---------------------------------------------------------------
        for i, agent_data in enumerate(ALL_AGENTS):
            exec_profile = EXEC_PROFILES[i]
            last_exec_hours = exec_profile[0]["hours_ago"]

            agent = Agent(
                id=uuid.uuid4(),
                user_id=user.id,
                name=agent_data["name"],
                type=agent_data["type"],
                description=agent_data["description"],
                status=agent_data["status"],
                schedule_cron=agent_data.get("schedule_cron"),
                schedule_timezone="Asia/Singapore",
                last_execution_at=now - timedelta(hours=last_exec_hours),
            )
            session.add(agent)
            await session.flush()

            workflow = Workflow(
                id=uuid.uuid4(),
                agent_id=agent.id,
                status="active",
                definition=agent_data["workflow"],
                deployed_at=now - timedelta(days=14),
            )
            session.add(workflow)
            await session.flush()

            # Add execution history
            for exec_data in exec_profile:
                started = now - timedelta(hours=exec_data["hours_ago"])
                ended = started + timedelta(milliseconds=exec_data["duration_ms"])
                execution = Execution(
                    id=uuid.uuid4(),
                    agent_id=agent.id,
                    workflow_id=workflow.id,
                    status=exec_data["status"],
                    triggered_by=exec_data["triggered_by"],
                    started_at=started,
                    ended_at=ended,
                    duration_ms=exec_data["duration_ms"],
                    variables={},
                    total_cost=float(exec_data["cost"]),
                )
                session.add(execution)

            await session.flush()
            print(f"  [{i+1}/8] {agent_data['name']} - {len(exec_profile)} executions")

        await session.commit()

        print(f"\nNextXR team seed complete!")
        print(f"  Login: {DEMO_EMAIL} / {DEMO_PASSWORD}")
        print(f"  Agents: {len(ALL_AGENTS)}")
        print(f"  URL: http://localhost:3000")


if __name__ == "__main__":
    asyncio.run(seed_nextxr_team())
