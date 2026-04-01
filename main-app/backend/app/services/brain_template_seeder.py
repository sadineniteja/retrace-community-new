"""
Brain template seeder — idempotently inserts built-in brain templates at startup.

Called from main.py lifespan, following the same pattern as default admin/tenant seeding.
"""

from sqlalchemy import select
from app.db.database import async_session_maker
from app.models.brain_template import BrainTemplate


BUILTIN_TEMPLATES = [
    {
        "slug": "job_searcher",
        "name": "Job Searcher",
        "description": "Finds and applies to jobs, networks on LinkedIn, sends follow-up emails, preps you for interviews, and manages your entire job pipeline.",
        "icon": "briefcase",
        "color": "#3b82f6",
        "category": "career",
        "interview_questions": [
            {"key": "target_role", "question": "What role are you looking for?", "type": "text", "required": True, "placeholder": "e.g., Senior Product Manager"},
            {"key": "locations", "question": "What locations work for you?", "type": "multi_text", "required": True, "placeholder": "e.g., Austin, Remote, NYC"},
            {"key": "remote_ok", "question": "Are you open to remote work?", "type": "boolean", "required": True},
            {"key": "salary_min", "question": "What's the minimum salary you'd accept?", "type": "number", "required": False, "placeholder": "e.g., 150000"},
            {"key": "salary_max", "question": "What's your target salary?", "type": "number", "required": False, "placeholder": "e.g., 200000"},
            {"key": "industries", "question": "What industries interest you?", "type": "multi_select", "required": False,
             "options": ["Tech", "Finance", "Healthcare", "Education", "Retail", "Media", "Government", "Other"]},
            {"key": "resume", "question": "Upload your resume so I can tailor applications for you.", "type": "file_upload", "required": True, "accept": ".pdf,.doc,.docx"},
            {"key": "linkedin", "question": "Connect your LinkedIn account so I can network for you.", "type": "connect_account", "provider": "linkedin", "required": True},
            {"key": "email", "question": "Connect your email for sending applications and follow-ups.", "type": "connect_account", "provider": "google", "required": True},
            {"key": "daily_applications", "question": "How many applications per day?", "type": "select", "required": True,
             "options": [{"label": "5 (careful)", "value": 5}, {"label": "15 (moderate)", "value": 15}, {"label": "30 (aggressive)", "value": 30}]},
            {"key": "auto_apply", "question": "Should I apply automatically, or show you each one first?", "type": "select", "required": True,
             "options": [{"label": "Show me every application first", "value": "supervised"}, {"label": "Auto-apply, just notify me", "value": "full_auto"}, {"label": "Auto for good matches, ask for borderline", "value": "semi_auto"}]},
        ],
        "system_prompt_template": "You are an autonomous Job Searcher agent. Your goal is to find and secure job opportunities for the user.\n\nTarget role: {target_role}\nLocations: {locations}\nRemote OK: {remote_ok}\nSalary range: {salary_min} - {salary_max}\nIndustries: {industries}\n\nYou have access to the user's resume and connected accounts (LinkedIn, Email). Use them to:\n1. Search for matching job postings daily\n2. Tailor the resume for each application\n3. Write personalized cover letters\n4. Submit applications\n5. Send LinkedIn connection requests to recruiters\n6. Follow up on applications after 5 days\n7. Prepare interview materials when interviews are scheduled\n\nAlways be professional. Never misrepresent the user's qualifications. Track every application in the pipeline.",
        "required_accounts": ["linkedin", "google"],
        "optional_accounts": ["indeed", "glassdoor"],
        "available_tools": ["linkedin_search", "linkedin_apply", "linkedin_connect", "indeed_search", "email_send", "email_read", "tailor_resume", "write_cover_letter", "web_search", "web_fetch"],
        "default_schedules": [
            {"name": "Daily Job Search", "task_type": "search", "schedule_type": "daily", "schedule_config": {"time": "08:00"}, "task_instructions": "Search for new job postings matching the user's criteria. For good matches, create application tasks."},
            {"name": "Follow-up Check", "task_type": "message", "schedule_type": "daily", "schedule_config": {"time": "14:00"}, "task_instructions": "Check for applications that are 5+ days old with no response. Send polite follow-up emails."},
        ],
        "default_monitors": [
            {"name": "New Job Matches", "monitor_type": "job_match", "check_interval_minutes": 360, "trigger_action": "create_task"},
        ],
    },
    {
        "slug": "trader",
        "name": "Trader",
        "description": "Monitors markets, tracks your portfolio, executes trades based on your rules, sends price alerts, and generates daily P&L summaries.",
        "icon": "trending-up",
        "color": "#10b981",
        "category": "finance",
        "interview_questions": [
            {"key": "markets", "question": "What do you trade?", "type": "multi_select", "required": True,
             "options": ["Stocks", "Crypto", "Forex", "Options", "Commodities"]},
            {"key": "tickers", "question": "What tickers do you want to watch?", "type": "multi_text", "required": True, "placeholder": "e.g., TSLA, AAPL, BTC, ETH"},
            {"key": "brokerage", "question": "Connect your brokerage account.", "type": "connect_account", "provider": "robinhood", "required": False},
            {"key": "risk_tolerance", "question": "What's your risk tolerance?", "type": "select", "required": True,
             "options": [{"label": "Conservative — preserve capital", "value": "conservative"}, {"label": "Moderate — balanced growth", "value": "moderate"}, {"label": "Aggressive — maximize returns", "value": "aggressive"}]},
            {"key": "daily_budget", "question": "Maximum daily trade amount (USD)?", "type": "number", "required": False, "placeholder": "e.g., 1000"},
            {"key": "trading_rules", "question": "Any specific trading rules?", "type": "text", "required": False, "placeholder": "e.g., Never more than 5% in one stock"},
            {"key": "auto_trade", "question": "Should I execute trades automatically?", "type": "select", "required": True,
             "options": [{"label": "Always ask before trading", "value": "supervised"}, {"label": "Auto for small trades, ask for large", "value": "semi_auto"}, {"label": "Full auto within my rules", "value": "full_auto"}]},
        ],
        "system_prompt_template": "You are an autonomous Trader agent. Your goal is to monitor markets and manage the user's trading activity.\n\nMarkets: {markets}\nWatchlist: {tickers}\nRisk tolerance: {risk_tolerance}\nDaily budget: ${daily_budget}\nRules: {trading_rules}\n\nYou should:\n1. Monitor prices of watched tickers\n2. Analyze market news and sentiment\n3. Generate buy/sell signals based on user's risk tolerance\n4. Execute trades within the daily budget (if authorized)\n5. Track portfolio performance and P&L\n6. Send daily market summaries\n7. Alert immediately on significant price movements\n\nNever exceed the daily budget. Always explain your reasoning for trades.",
        "required_accounts": [],
        "optional_accounts": ["robinhood", "coinbase", "binance"],
        "available_tools": ["get_stock_price", "get_crypto_price", "get_market_news", "place_order", "get_portfolio", "analyze_chart", "web_search"],
        "default_schedules": [
            {"name": "Market Open Check", "task_type": "monitor", "schedule_type": "daily", "schedule_config": {"time": "09:30"}, "task_instructions": "Check pre-market movers and overnight news for watchlist tickers. Alert on significant developments."},
            {"name": "Daily P&L Summary", "task_type": "general", "schedule_type": "daily", "schedule_config": {"time": "16:30"}, "task_instructions": "Generate end-of-day P&L summary with portfolio performance and notable market events."},
        ],
        "default_monitors": [
            {"name": "Price Alerts", "monitor_type": "stock_price", "check_interval_minutes": 5, "trigger_action": "notify"},
        ],
    },
    {
        "slug": "social_media",
        "name": "Social Media Manager",
        "description": "Creates and schedules posts, engages with your audience, monitors trends in your niche, tracks analytics, and grows your presence.",
        "icon": "share-2",
        "color": "#8b5cf6",
        "category": "marketing",
        "interview_questions": [
            {"key": "platforms", "question": "What platforms do you use?", "type": "multi_select", "required": True,
             "options": ["Twitter/X", "LinkedIn", "Instagram", "TikTok", "YouTube", "Facebook"]},
            {"key": "niche", "question": "What's your niche or industry?", "type": "text", "required": True, "placeholder": "e.g., AI/Tech, Fitness, Finance"},
            {"key": "tone", "question": "What's your brand voice?", "type": "select", "required": True,
             "options": [{"label": "Professional", "value": "professional"}, {"label": "Casual & friendly", "value": "casual"}, {"label": "Humorous", "value": "humorous"}, {"label": "Educational", "value": "educational"}, {"label": "Inspirational", "value": "inspirational"}]},
            {"key": "posting_frequency", "question": "How often should I post?", "type": "select", "required": True,
             "options": [{"label": "1 post/day", "value": 1}, {"label": "3 posts/day", "value": 3}, {"label": "5 posts/day", "value": 5}, {"label": "1 post/week", "value": 0.14}]},
            {"key": "twitter", "question": "Connect your Twitter/X account.", "type": "connect_account", "provider": "twitter", "required": False},
            {"key": "linkedin_social", "question": "Connect your LinkedIn for posting.", "type": "connect_account", "provider": "linkedin", "required": False},
            {"key": "auto_post", "question": "Should I post automatically?", "type": "select", "required": True,
             "options": [{"label": "Show me every post before publishing", "value": "supervised"}, {"label": "Auto-post, I'll review later", "value": "full_auto"}, {"label": "Auto for scheduled, ask for reactive", "value": "semi_auto"}]},
        ],
        "system_prompt_template": "You are an autonomous Social Media Manager agent. Your goal is to grow the user's social media presence.\n\nPlatforms: {platforms}\nNiche: {niche}\nBrand voice: {tone}\nPosting frequency: {posting_frequency} posts/day\n\nYou should:\n1. Create original content matching the brand voice\n2. Schedule posts at optimal times\n3. Engage with comments and mentions\n4. Monitor trending topics in the niche\n5. Repurpose content across platforms\n6. Track engagement metrics\n7. Suggest content improvements based on performance\n\nAlways maintain the brand voice. Never post controversial or offensive content.",
        "required_accounts": [],
        "optional_accounts": ["twitter", "linkedin", "instagram"],
        "available_tools": ["create_post", "schedule_post", "reply_comment", "get_trending", "get_analytics", "web_search", "web_fetch"],
        "default_schedules": [
            {"name": "Daily Content Creation", "task_type": "post", "schedule_type": "daily", "schedule_config": {"time": "07:00"}, "task_instructions": "Create and schedule today's posts based on trending topics and content calendar."},
            {"name": "Engagement Check", "task_type": "message", "schedule_type": "interval", "schedule_config": {"every": 4, "unit": "hours"}, "task_instructions": "Check for new comments, mentions, and DMs. Respond to engage with the audience."},
        ],
        "default_monitors": [
            {"name": "Trending in Niche", "monitor_type": "social_mention", "check_interval_minutes": 120, "trigger_action": "create_task"},
        ],
    },
    {
        "slug": "coder",
        "name": "Coder",
        "description": "Monitors your GitHub repos, picks up issues, writes pull requests, reviews code, fixes CI, and keeps your docs updated.",
        "icon": "code-2",
        "color": "#f59e0b",
        "category": "development",
        "interview_questions": [
            {"key": "github", "question": "Connect your GitHub account.", "type": "connect_account", "provider": "github", "required": True},
            {"key": "repos", "question": "Which repos should I watch?", "type": "multi_text", "required": True, "placeholder": "e.g., myorg/frontend, myorg/api"},
            {"key": "role", "question": "What's your role on these repos?", "type": "select", "required": True,
             "options": [{"label": "Owner — I can merge PRs", "value": "owner"}, {"label": "Contributor — I submit PRs", "value": "contributor"}, {"label": "Reviewer — I review others' PRs", "value": "reviewer"}]},
            {"key": "languages", "question": "Primary languages?", "type": "multi_select", "required": True,
             "options": ["Python", "JavaScript", "TypeScript", "Go", "Rust", "Java", "C++", "Ruby", "Other"]},
            {"key": "auto_push", "question": "Should I push code automatically?", "type": "select", "required": True,
             "options": [{"label": "Create draft PRs for my review", "value": "supervised"}, {"label": "Push and open PRs directly", "value": "full_auto"}]},
        ],
        "system_prompt_template": "You are an autonomous Coder agent. Your goal is to help the user manage their software projects.\n\nRepos: {repos}\nRole: {role}\nLanguages: {languages}\n\nYou should:\n1. Monitor assigned GitHub issues\n2. Write code to resolve issues\n3. Create well-structured pull requests\n4. Review incoming PRs and leave helpful comments\n5. Fix broken CI/CD pipelines\n6. Keep documentation up to date\n7. Watch for security vulnerabilities in dependencies\n\nFollow the repo's existing code style. Write tests for new code. Never push directly to main.",
        "required_accounts": ["github"],
        "optional_accounts": ["gitlab"],
        "available_tools": ["github_search_issues", "github_create_pr", "github_review_pr", "read_file", "write_file", "terminal", "web_search"],
        "default_schedules": [
            {"name": "Issue Triage", "task_type": "review", "schedule_type": "daily", "schedule_config": {"time": "09:00"}, "task_instructions": "Check for new issues assigned to the user. Prioritize and start working on the most important ones."},
            {"name": "PR Review", "task_type": "review", "schedule_type": "daily", "schedule_config": {"time": "14:00"}, "task_instructions": "Review open PRs that need attention. Leave constructive comments."},
        ],
        "default_monitors": [
            {"name": "New Issues", "monitor_type": "github_repo", "check_interval_minutes": 60, "trigger_action": "create_task"},
        ],
    },
    {
        "slug": "personal_finance",
        "name": "Personal Finance",
        "description": "Tracks your spending, monitors bills, finds savings opportunities, watches interest rates, and helps with tax preparation.",
        "icon": "wallet",
        "color": "#ec4899",
        "category": "finance",
        "interview_questions": [
            {"key": "goals", "question": "What are your financial goals?", "type": "multi_select", "required": True,
             "options": ["Save more money", "Pay off debt", "Budget better", "Track spending", "Tax preparation", "Find better rates"]},
            {"key": "monthly_income", "question": "What's your monthly income (approximate)?", "type": "number", "required": False, "placeholder": "e.g., 8000"},
            {"key": "budget_categories", "question": "What spending categories do you want to track?", "type": "multi_select", "required": False,
             "options": ["Housing", "Food", "Transportation", "Entertainment", "Shopping", "Subscriptions", "Healthcare", "Education"]},
            {"key": "alert_threshold", "question": "Alert me when any category exceeds what % of my budget?", "type": "select", "required": True,
             "options": [{"label": "80%", "value": 80}, {"label": "90%", "value": 90}, {"label": "100%", "value": 100}]},
            {"key": "auto_categorize", "question": "Should I automatically categorize your transactions?", "type": "boolean", "required": True},
        ],
        "system_prompt_template": "You are an autonomous Personal Finance agent. Your goal is to help the user manage their money better.\n\nGoals: {goals}\nMonthly income: ${monthly_income}\nBudget categories: {budget_categories}\nAlert threshold: {alert_threshold}%\n\nYou should:\n1. Track and categorize spending\n2. Alert when approaching budget limits\n3. Find subscriptions that could be cancelled\n4. Monitor interest rates for savings and mortgages\n5. Identify recurring charges and unusual spending\n6. Prepare tax-related summaries\n7. Suggest ways to save money\n\nBe conservative with financial advice. Never make unauthorized transactions.",
        "required_accounts": [],
        "optional_accounts": ["plaid", "google"],
        "available_tools": ["categorize_transaction", "get_account_balance", "find_subscriptions", "compare_rates", "web_search"],
        "default_schedules": [
            {"name": "Weekly Spending Review", "task_type": "general", "schedule_type": "weekly", "schedule_config": {"day": "sunday", "time": "10:00"}, "task_instructions": "Generate a weekly spending summary. Highlight unusual expenses and budget status."},
        ],
        "default_monitors": [
            {"name": "Rate Changes", "monitor_type": "rate_change", "check_interval_minutes": 1440, "trigger_action": "notify"},
        ],
    },
    {
        "slug": "custom",
        "name": "Custom Brain",
        "description": "Create your own AI agent for any task. Define what it does, connect the accounts it needs, and set your own rules.",
        "icon": "sparkles",
        "color": "#6366f1",
        "category": "general",
        "interview_questions": [
            {"key": "brain_name", "question": "What should I call this Brain?", "type": "text", "required": True, "placeholder": "e.g., My Research Assistant"},
            {"key": "purpose", "question": "What do you want this Brain to do?", "type": "textarea", "required": True, "placeholder": "Describe the tasks in plain English..."},
            {"key": "accounts_needed", "question": "What accounts does it need access to?", "type": "multi_select", "required": False,
             "options": ["Google/Gmail", "LinkedIn", "Twitter/X", "GitHub", "Slack", "Custom API"]},
            {"key": "schedule", "question": "How often should it run?", "type": "select", "required": True,
             "options": [{"label": "Continuously", "value": "continuous"}, {"label": "Every hour", "value": "hourly"}, {"label": "Daily", "value": "daily"}, {"label": "Weekly", "value": "weekly"}, {"label": "Only when I ask", "value": "manual"}]},
            {"key": "autonomy", "question": "How much autonomy should it have?", "type": "select", "required": True,
             "options": [{"label": "Ask me before every action", "value": "supervised"}, {"label": "Auto for routine, ask for important", "value": "semi_auto"}, {"label": "Full autonomy", "value": "full_auto"}]},
        ],
        "system_prompt_template": "You are a custom autonomous AI agent created by the user.\n\nPurpose: {purpose}\n\nFollow the user's instructions carefully. Use the connected accounts and tools available to accomplish the defined purpose. Report progress regularly.",
        "required_accounts": [],
        "optional_accounts": ["google", "linkedin", "twitter", "github", "slack"],
        "available_tools": ["web_search", "web_fetch", "email_send", "email_read"],
        "default_schedules": [],
        "default_monitors": [],
    },
]


async def seed_brain_templates() -> None:
    """Idempotently insert or update built-in brain templates."""
    async with async_session_maker() as session:
        for tmpl_data in BUILTIN_TEMPLATES:
            slug = tmpl_data["slug"]
            result = await session.execute(
                select(BrainTemplate).where(BrainTemplate.slug == slug)
            )
            existing = result.scalar_one_or_none()

            if existing is None:
                template = BrainTemplate(
                    slug=slug,
                    name=tmpl_data["name"],
                    description=tmpl_data["description"],
                    icon=tmpl_data["icon"],
                    color=tmpl_data["color"],
                    category=tmpl_data["category"],
                    interview_questions=tmpl_data["interview_questions"],
                    system_prompt_template=tmpl_data["system_prompt_template"],
                    default_config={},
                    required_accounts=tmpl_data["required_accounts"],
                    optional_accounts=tmpl_data["optional_accounts"],
                    available_tools=tmpl_data["available_tools"],
                    default_schedules=tmpl_data.get("default_schedules", []),
                    default_monitors=tmpl_data.get("default_monitors", []),
                    is_builtin=True,
                    is_published=True,
                )
                session.add(template)
                print(f"[STARTUP] Seeded brain template: {slug}", flush=True)
            else:
                # Update existing built-in templates to latest definitions
                existing.name = tmpl_data["name"]
                existing.description = tmpl_data["description"]
                existing.icon = tmpl_data["icon"]
                existing.color = tmpl_data["color"]
                existing.category = tmpl_data["category"]
                existing.interview_questions = tmpl_data["interview_questions"]
                existing.system_prompt_template = tmpl_data["system_prompt_template"]
                existing.required_accounts = tmpl_data["required_accounts"]
                existing.optional_accounts = tmpl_data["optional_accounts"]
                existing.available_tools = tmpl_data["available_tools"]
                existing.default_schedules = tmpl_data.get("default_schedules", [])
                existing.default_monitors = tmpl_data.get("default_monitors", [])

        await session.commit()
        print(f"[STARTUP] Brain templates seeded ({len(BUILTIN_TEMPLATES)} templates)", flush=True)
