# ReTrace Community Edition — Autonomous Brain Platform Architecture

## Product Vision

Each Brain is an **autonomous AI employee** that fully executes work on behalf of the user.
Users don't chat with Brains — they **hire** them. The Brain asks a few setup questions,
connects to the user's accounts, and then works 24/7 autonomously.

---

## Part 1: The Brains

### Brain: Job Searcher

**What it does autonomously:**

| Task | Detail |
|------|--------|
| Find jobs | Searches LinkedIn, Indeed, Glassdoor, company career pages daily |
| Filter & rank | Matches against user's resume, preferences, salary range |
| Tailor resume | Creates customized resume per job posting |
| Write cover letters | Personalized per company and role |
| Apply | Submits applications on job boards |
| LinkedIn outreach | Sends connection requests to recruiters/hiring managers with personalized notes |
| Cold email | Finds hiring manager emails, sends intros |
| Respond to emails | Replies to recruiter outreach, schedules calls |
| Follow up | If no response in N days, sends polite follow-up |
| Interview prep | When interview booked, researches company, prepares Q&A |
| Track pipeline | Applied → Response → Interview → Offer → Rejected |

**Setup interview (Brain asks user):**
1. What role are you looking for?
2. What locations? Remote OK?
3. Salary range?
4. What industries/companies?
5. Upload your resume
6. Connect LinkedIn account
7. Connect email (Gmail/Outlook)
8. How aggressive? (5 apps/day vs 30 apps/day)
9. Auto-send or approve before sending?

---

### Brain: Trader

**What it does autonomously:**

| Task | Detail |
|------|--------|
| Monitor portfolio | Tracks all holdings, P&L, daily changes |
| Watch market | Scans news, earnings, SEC filings for user's watchlist |
| Price alerts | Notifies on threshold crossings |
| Execute trades | Buys/sells based on user-defined rules (with limits) |
| Rebalance | Adjusts portfolio to target allocation |
| Daily digest | Morning summary of overnight moves, upcoming events |
| Research | Deep dives on stocks/crypto user is interested in |
| Tax tracking | Tracks gains/losses for tax reporting |

**Setup interview:**
1. What do you trade? (Stocks, Crypto, Forex, Options)
2. Connect brokerage (Robinhood, TD Ameritrade, Coinbase, etc.)
3. Upload portfolio or enter tickers manually
4. Risk tolerance? (Conservative / Moderate / Aggressive)
5. Trading rules? (e.g., "Never invest more than 5% in one stock")
6. Auto-trade or approve before executing?
7. Daily budget limit?

---

### Brain: Social Media Manager

**What it does autonomously:**

| Task | Detail |
|------|--------|
| Create content | Generates posts matching brand voice and platform |
| Schedule posts | Publishes across Twitter/X, LinkedIn, Instagram, TikTok |
| Engage | Responds to comments, DMs, mentions |
| Monitor trends | Watches trending topics in user's niche |
| Repurpose | Turns one piece of content into multi-platform posts |
| Analytics | Tracks engagement, follower growth, best performing content |
| Competitor watch | Monitors what competitors are posting |

**Setup interview:**
1. What platforms? (Twitter, LinkedIn, Instagram, TikTok)
2. Connect accounts (OAuth)
3. Upload brand guidelines / past content / tone examples
4. Content topics and niche?
5. Posting frequency? (1/day, 3/day, etc.)
6. Auto-post or approve before publishing?
7. Engage with comments automatically?

---

### Brain: Coder

**What it does autonomously:**

| Task | Detail |
|------|--------|
| Monitor repos | Watches GitHub issues/PRs assigned to user |
| Write code | Drafts PR code for assigned issues |
| Code review | Reviews incoming PRs, leaves comments |
| Fix CI | When builds break, diagnoses and pushes fixes |
| Update docs | Keeps README and docs in sync with code changes |
| Dependency watch | Monitors for security vulnerabilities in dependencies |
| Daily standup | Summarizes what happened in repos overnight |

**Setup interview:**
1. Connect GitHub/GitLab account
2. Which repos to watch?
3. What's your role? (Owner, contributor, reviewer)
4. Auto-push code or create draft PRs for review?
5. Which issues to pick up automatically?
6. Coding style preferences?

---

### Brain: Personal Finance

**What it does autonomously:**

| Task | Detail |
|------|--------|
| Track spending | Categorizes transactions from connected bank accounts |
| Budget alerts | Notifies when nearing budget limits |
| Bill reminders | Reminds before due dates |
| Find savings | Spots subscriptions user might cancel, better rates |
| Tax prep | Organizes deductions, tracks receipts |
| Rate monitoring | Watches mortgage rates, savings rates, CD rates |

**Setup interview:**
1. Connect bank accounts (Plaid integration)
2. Monthly budget targets?
3. Bill due dates?
4. Financial goals? (Save $X, pay off debt, etc.)

---

### Brain: Custom

Users create their own Brain for any use case:
1. Name it
2. Describe what it should do (plain English)
3. Connect relevant accounts
4. Set rules and preferences
5. Define what needs approval vs. auto-execute

---

## Part 2: System Architecture

### High-Level Architecture

```
                         ┌──────────────────┐
                         │   Web / Mobile    │
                         │   (React PWA)     │
                         └────────┬─────────┘
                                  │ HTTPS
                         ┌────────┴─────────┐
                         │    API Gateway    │
                         │    (FastAPI)      │
                         └────────┬─────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
   ┌──────┴──────┐       ┌───────┴───────┐      ┌───────┴───────┐
   │  Brain      │       │  Execution    │      │  Monitor      │
   │  Manager    │       │  Engine       │      │  Service      │
   │             │       │               │      │               │
   │ - Setup     │       │ - Task Queue  │      │ - Watchers    │
   │ - Config    │       │ - Browser     │      │ - Data Feeds  │
   │ - Templates │       │   Sessions    │      │ - Alert Rules │
   │             │       │ - Action      │      │               │
   │             │       │   Execution   │      │               │
   └──────┬──────┘       └───────┬───────┘      └───────┬───────┘
          │                       │                       │
          │               ┌───────┴───────┐               │
          │               │   Browser     │               │
          │               │   Pool        │               │
          │               │  (Playwright) │               │
          │               │               │               │
          │               │ - LinkedIn    │               │
          │               │ - Gmail       │               │
          │               │ - Indeed      │               │
          │               │ - Robinhood   │               │
          │               └───────────────┘               │
          │                                               │
   ┌──────┴───────────────────────────────────────────────┴──────┐
   │                        Data Layer                            │
   │  ┌────────────┐  ┌───────────┐  ┌─────────┐  ┌──────────┐ │
   │  │ PostgreSQL  │  │  Redis    │  │   S3    │  │ ChromaDB │ │
   │  │ (state,    │  │ (queue,   │  │ (files, │  │ (vectors)│ │
   │  │  users,    │  │  cache,   │  │  resume,│  │          │ │
   │  │  brains)   │  │  sessions)│  │  docs)  │  │          │ │
   │  └────────────┘  └───────────┘  └─────────┘  └──────────┘ │
   └─────────────────────────────────────────────────────────────┘
          │
   ┌──────┴──────┐
   │ Notification │
   │ Service      │
   │              │
   │ - Push       │
   │ - Email      │
   │ - SMS        │
   │ - In-app     │
   └──────────────┘
```

---

### Component Breakdown

#### 1. Brain Manager

Handles Brain lifecycle: creation from templates, setup interviews,
configuration storage, activation/deactivation.

```
Brain Manager
├── Template Registry      — Pre-built Brain definitions
├── Setup Interview Engine  — Guided Q&A to configure a Brain
├── Account Connector      — OAuth flows for external services
├── Config Store           — Brain preferences and rules
└── Brain Lifecycle        — Activate, pause, deactivate, delete
```

#### 2. Execution Engine

The core autonomous worker. Takes tasks from Brain configs and executes them.

```
Execution Engine
├── Task Scheduler         — Generates tasks from Brain rules (cron + event-driven)
├── Task Queue (Redis)     — Prioritized task queue per Brain
├── Task Executor          — Picks tasks, runs them via LangGraph agent
├── Browser Pool           — Persistent Playwright sessions per connected account
├── Action Library         — Pre-built actions (apply_to_job, send_linkedin_request, etc.)
├── Approval Gate          — Holds tasks needing user approval
└── Retry & Error Handler  — Retries failed tasks, escalates to user
```

#### 3. Monitor Service

Watches external data sources and triggers actions or notifications.

```
Monitor Service
├── Watcher Registry       — User-defined watches (price, keyword, job match, etc.)
├── Data Feed Connectors   — Stock APIs, news APIs, job board scrapers
├── Evaluation Engine      — Checks conditions against incoming data
├── Trigger Dispatcher     — Fires notifications or creates tasks in Execution Engine
└── History Store          — What was checked, what triggered, when
```

#### 4. Browser Pool

Persistent browser sessions that stay logged into user's accounts.

```
Browser Pool
├── Session Manager        — Create, maintain, recycle browser contexts
├── Cookie/Auth Store      — Encrypted session cookies per account
├── Anti-Detection         — Human-like delays, mouse movements, rate limiting
├── Page Interaction       — Click, type, scroll, extract data, fill forms
└── Screenshot Capture     — Proof of actions taken (stored for user review)
```

#### 5. Notification Service

Multi-channel delivery of alerts and reports.

```
Notification Service
├── Push (Web + Mobile)    — Firebase Cloud Messaging / Web Push API
├── Email                  — SendGrid / SES for digests and alerts
├── SMS                    — Twilio for critical alerts (pro feature)
├── In-App                 — WebSocket real-time + notification inbox
└── Digest Builder         — Daily/weekly summary emails per Brain
```

---

## Part 3: Data Model

### New Tables

```sql
-- ============================================
-- BRAINS (replaces products for community edition)
-- ============================================

CREATE TABLE brains (
    brain_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(user_id),
    tenant_id       UUID NOT NULL REFERENCES tenants(tenant_id),

    -- Brain identity
    brain_type      VARCHAR(50) NOT NULL,  -- job_searcher, trader, social_media, coder, finance, custom
    name            VARCHAR(200) NOT NULL, -- User-facing name: "My Job Search"
    description     TEXT,
    icon            VARCHAR(50),           -- Emoji or icon key
    status          VARCHAR(20) NOT NULL DEFAULT 'setup',
        -- setup: still doing interview
        -- active: running autonomously
        -- paused: user paused it
        -- inactive: deactivated

    -- Configuration (from setup interview)
    config_json     JSONB NOT NULL DEFAULT '{}',
        -- Job Searcher example:
        -- {
        --   "target_role": "Senior Product Manager",
        --   "locations": ["Austin", "Remote"],
        --   "salary_min": 150000,
        --   "salary_max": 200000,
        --   "industries": ["Tech", "Fintech"],
        --   "aggression": "moderate",        -- low/moderate/high
        --   "auto_apply": false,
        --   "auto_email": false,
        --   "auto_linkedin": false,
        --   "followup_days": 5,
        --   "max_daily_applications": 10
        -- }

    -- Approval settings
    approval_mode   VARCHAR(20) NOT NULL DEFAULT 'approve_all',
        -- approve_all: every action needs approval
        -- approve_important: only high-impact actions (e.g., sending email, applying)
        -- auto: fully autonomous, just notify

    -- Schedule
    run_schedule    VARCHAR(20) NOT NULL DEFAULT 'daily',
        -- continuous, hourly, daily, weekly
    last_run_at     TIMESTAMPTZ,
    next_run_at     TIMESTAMPTZ,

    -- Stats
    total_actions   INTEGER NOT NULL DEFAULT 0,
    total_successes INTEGER NOT NULL DEFAULT 0,
    total_failures  INTEGER NOT NULL DEFAULT 0,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_brains_user ON brains(user_id);
CREATE INDEX idx_brains_status ON brains(status);


-- ============================================
-- BRAIN SETUP INTERVIEW
-- ============================================

CREATE TABLE brain_interviews (
    interview_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brain_id        UUID NOT NULL REFERENCES brains(brain_id) ON DELETE CASCADE,

    -- Interview state
    current_step    INTEGER NOT NULL DEFAULT 0,
    total_steps     INTEGER NOT NULL,
    answers_json    JSONB NOT NULL DEFAULT '{}',
        -- { "step_0": { "question": "...", "answer": "..." }, ... }
    status          VARCHAR(20) NOT NULL DEFAULT 'in_progress',
        -- in_progress, completed, abandoned

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);


-- ============================================
-- CONNECTED ACCOUNTS (OAuth sessions for external services)
-- ============================================

CREATE TABLE connected_accounts (
    account_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(user_id),
    brain_id            UUID REFERENCES brains(brain_id) ON DELETE SET NULL,

    -- Service identity
    provider            VARCHAR(50) NOT NULL,
        -- linkedin, gmail, outlook, indeed, glassdoor, github, gitlab,
        -- robinhood, coinbase, td_ameritrade, twitter, instagram, tiktok,
        -- plaid (banking)
    account_label       VARCHAR(200),          -- "Work Gmail", "Personal LinkedIn"
    external_user_id    VARCHAR(500),          -- Provider's user ID

    -- Auth
    auth_method         VARCHAR(20) NOT NULL,  -- oauth, cookies, api_key, credentials
    access_token_enc    TEXT,                   -- Encrypted OAuth access token
    refresh_token_enc   TEXT,                   -- Encrypted OAuth refresh token
    cookies_enc         TEXT,                   -- Encrypted browser cookies (for cookie-based auth)
    api_key_enc         TEXT,                   -- Encrypted API key
    token_expires_at    TIMESTAMPTZ,

    -- Status
    status              VARCHAR(20) NOT NULL DEFAULT 'active',
        -- active, expired, revoked, needs_reauth
    last_used_at        TIMESTAMPTZ,
    error_message       TEXT,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_connected_accounts_user ON connected_accounts(user_id);
CREATE INDEX idx_connected_accounts_brain ON connected_accounts(brain_id);


-- ============================================
-- TASKS (work items the Brain executes)
-- ============================================

CREATE TABLE brain_tasks (
    task_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brain_id        UUID NOT NULL REFERENCES brains(brain_id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(user_id),

    -- Task identity
    task_type       VARCHAR(100) NOT NULL,
        -- Job Searcher: search_jobs, apply_job, send_linkedin_request,
        --   send_cold_email, reply_email, followup_email, prep_interview
        -- Trader: check_prices, execute_trade, rebalance, research_stock
        -- Social Media: create_post, schedule_post, reply_comment, analyze_metrics
        -- Coder: check_issues, write_pr, review_pr, fix_ci, update_docs
    title           VARCHAR(500) NOT NULL,     -- Human-readable: "Apply to Google PM role"
    description     TEXT,

    -- Task data (input for execution)
    input_json      JSONB NOT NULL DEFAULT '{}',
        -- Job apply example:
        -- {
        --   "job_url": "https://linkedin.com/jobs/123",
        --   "company": "Google",
        --   "role": "Senior PM",
        --   "tailored_resume_s3_key": "resumes/google-pm-v1.pdf",
        --   "cover_letter": "Dear hiring manager..."
        -- }

    -- Execution result
    output_json     JSONB,
        -- {
        --   "status": "applied",
        --   "confirmation_screenshot_s3": "screenshots/apply-google-123.png",
        --   "notes": "Application submitted successfully"
        -- }

    -- Status flow: pending → approved/auto → running → completed/failed/cancelled
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
        -- pending_approval: waiting for user to approve
        -- approved: user approved, queued for execution
        -- queued: auto-approved, in task queue
        -- running: currently executing
        -- completed: done successfully
        -- failed: execution failed
        -- cancelled: user cancelled

    priority        INTEGER NOT NULL DEFAULT 5,  -- 1 (highest) to 10 (lowest)

    -- Approval
    needs_approval  BOOLEAN NOT NULL DEFAULT TRUE,
    approved_at     TIMESTAMPTZ,
    approval_note   TEXT,                       -- User can add note when approving

    -- Execution tracking
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    retry_count     INTEGER NOT NULL DEFAULT 0,
    max_retries     INTEGER NOT NULL DEFAULT 3,
    error_message   TEXT,

    -- Proof of work
    screenshots     JSONB,  -- Array of S3 keys for action screenshots
    action_log      JSONB,  -- Step-by-step log of what the agent did

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_brain_tasks_brain ON brain_tasks(brain_id);
CREATE INDEX idx_brain_tasks_status ON brain_tasks(status);
CREATE INDEX idx_brain_tasks_pending ON brain_tasks(brain_id, status) WHERE status = 'pending_approval';


-- ============================================
-- MONITORS (watchers that track external data)
-- ============================================

CREATE TABLE monitors (
    monitor_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brain_id        UUID NOT NULL REFERENCES brains(brain_id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(user_id),

    -- Monitor definition
    name            VARCHAR(200) NOT NULL,     -- "Tesla below $200"
    monitor_type    VARCHAR(50) NOT NULL,
        -- price_threshold: stock/crypto price crosses a value
        -- keyword_news: news matching keywords
        -- job_match: new job matching criteria
        -- website_change: webpage content changes
        -- rate_change: interest/mortgage rate change
        -- custom: LLM-evaluated condition
    description     TEXT,                       -- Plain English description

    -- Configuration
    config_json     JSONB NOT NULL,
        -- price_threshold: { "ticker": "TSLA", "condition": "below", "value": 200, "market": "nasdaq" }
        -- keyword_news: { "keywords": ["Tesla", "Elon Musk"], "sources": ["reuters", "bloomberg"] }
        -- job_match: { "role": "PM", "location": "Austin", "salary_min": 150000 }
        -- website_change: { "url": "https://...", "selector": ".price", "condition": "changes" }

    -- Schedule
    check_interval  VARCHAR(20) NOT NULL DEFAULT 'hourly',
        -- realtime, every_5min, every_15min, hourly, daily, weekly
    last_checked_at TIMESTAMPTZ,
    next_check_at   TIMESTAMPTZ,

    -- Current state
    current_value   TEXT,                      -- Last observed value
    triggered       BOOLEAN NOT NULL DEFAULT FALSE,
    last_triggered  TIMESTAMPTZ,
    trigger_count   INTEGER NOT NULL DEFAULT 0,

    -- Notification preferences
    notify_push     BOOLEAN NOT NULL DEFAULT TRUE,
    notify_email    BOOLEAN NOT NULL DEFAULT FALSE,
    notify_sms      BOOLEAN NOT NULL DEFAULT FALSE,

    -- When triggered, optionally create a task
    auto_create_task    BOOLEAN NOT NULL DEFAULT FALSE,
    task_template_json  JSONB,  -- Task to create when triggered

    -- Status
    status          VARCHAR(20) NOT NULL DEFAULT 'active',
        -- active, paused, triggered_once (one-shot), expired

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_monitors_brain ON monitors(brain_id);
CREATE INDEX idx_monitors_next_check ON monitors(next_check_at) WHERE status = 'active';


-- ============================================
-- MONITOR HISTORY (log of checks and triggers)
-- ============================================

CREATE TABLE monitor_history (
    history_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    monitor_id      UUID NOT NULL REFERENCES monitors(monitor_id) ON DELETE CASCADE,

    checked_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    observed_value  TEXT,
    triggered       BOOLEAN NOT NULL DEFAULT FALSE,
    trigger_reason  TEXT,                      -- "TSLA dropped to $198.50, below threshold of $200"
    notification_sent BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX idx_monitor_history_monitor ON monitor_history(monitor_id);
CREATE INDEX idx_monitor_history_triggered ON monitor_history(monitor_id) WHERE triggered = TRUE;


-- ============================================
-- NOTIFICATIONS
-- ============================================

CREATE TABLE notifications (
    notification_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(user_id),
    brain_id        UUID REFERENCES brains(brain_id),

    -- Content
    title           VARCHAR(500) NOT NULL,
    body            TEXT NOT NULL,
    category        VARCHAR(50) NOT NULL,
        -- task_completed, task_failed, task_needs_approval,
        -- monitor_triggered, daily_digest, weekly_report,
        -- account_issue, system
    priority        VARCHAR(20) NOT NULL DEFAULT 'normal',
        -- low, normal, high, urgent
    action_url      TEXT,                      -- Deep link to relevant page
    metadata_json   JSONB,                     -- Extra context

    -- Delivery status
    read            BOOLEAN NOT NULL DEFAULT FALSE,
    read_at         TIMESTAMPTZ,
    push_sent       BOOLEAN NOT NULL DEFAULT FALSE,
    email_sent      BOOLEAN NOT NULL DEFAULT FALSE,
    sms_sent        BOOLEAN NOT NULL DEFAULT FALSE,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_notifications_user ON notifications(user_id);
CREATE INDEX idx_notifications_unread ON notifications(user_id) WHERE read = FALSE;


-- ============================================
-- BRAIN ACTIVITY LOG (everything a Brain does)
-- ============================================

CREATE TABLE brain_activity (
    activity_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brain_id        UUID NOT NULL REFERENCES brains(brain_id) ON DELETE CASCADE,
    task_id         UUID REFERENCES brain_tasks(task_id),

    -- Activity
    action          VARCHAR(100) NOT NULL,
        -- searched_jobs, found_match, applied, sent_request, sent_email,
        -- received_reply, scheduled_interview, checked_price, executed_trade,
        -- created_post, replied_comment, pushed_code, etc.
    summary         TEXT NOT NULL,             -- "Applied to Google Senior PM role"
    detail_json     JSONB,                     -- Full details of what happened
    screenshot_s3   TEXT,                      -- Proof screenshot

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_brain_activity_brain ON brain_activity(brain_id);
CREATE INDEX idx_brain_activity_time ON brain_activity(brain_id, created_at DESC);


-- ============================================
-- UPLOADED FILES (resumes, portfolios, brand docs)
-- ============================================

CREATE TABLE uploaded_files (
    file_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brain_id        UUID NOT NULL REFERENCES brains(brain_id) ON DELETE CASCADE,
    user_id         UUID NOT NULL REFERENCES users(user_id),

    -- File info
    filename        VARCHAR(500) NOT NULL,
    mime_type       VARCHAR(100) NOT NULL,
    size_bytes      BIGINT NOT NULL,
    s3_key          TEXT NOT NULL,
    file_type       VARCHAR(50),
        -- resume, cover_letter, portfolio, brand_guide, transcript,
        -- statement, contract, screenshot, other

    -- Processing
    processing_status VARCHAR(20) NOT NULL DEFAULT 'pending',
        -- pending, processing, indexed, failed
    extracted_text  TEXT,
    metadata_json   JSONB,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_uploaded_files_brain ON uploaded_files(brain_id);


-- ============================================
-- BROWSER SESSIONS (persistent logged-in sessions)
-- ============================================

CREATE TABLE browser_sessions (
    session_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    connected_account_id UUID NOT NULL REFERENCES connected_accounts(account_id) ON DELETE CASCADE,
    user_id             UUID NOT NULL REFERENCES users(user_id),

    -- Session state
    status              VARCHAR(20) NOT NULL DEFAULT 'active',
        -- active, idle, expired, error
    cookies_enc         TEXT,                  -- Encrypted current cookies
    local_storage_enc   TEXT,                  -- Encrypted localStorage snapshot
    last_active_at      TIMESTAMPTZ,
    error_message       TEXT,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ============================================
-- PIPELINES (job search funnel, trade history, content calendar)
-- ============================================

CREATE TABLE pipeline_items (
    item_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brain_id        UUID NOT NULL REFERENCES brains(brain_id) ON DELETE CASCADE,

    -- Item identity
    item_type       VARCHAR(50) NOT NULL,
        -- Job: job_application
        -- Trader: trade, watchlist_item
        -- Social: content_piece
        -- Coder: issue, pull_request
    title           VARCHAR(500) NOT NULL,
    external_url    TEXT,
    external_id     VARCHAR(500),

    -- Pipeline stage
    stage           VARCHAR(50) NOT NULL,
        -- Job: found → applied → response → interview → offer → accepted → rejected
        -- Trader: watching → buy_signal → bought → holding → sell_signal → sold
        -- Social: idea → drafted → scheduled → published → analyzing
        -- Coder: assigned → in_progress → pr_created → reviewed → merged
    stage_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Data
    data_json       JSONB NOT NULL DEFAULT '{}',
        -- Job example:
        -- {
        --   "company": "Google", "role": "Senior PM", "salary": "$180k",
        --   "applied_date": "2026-03-28", "resume_version": "google-pm-v1",
        --   "cover_letter_sent": true, "recruiter_name": "Jane Smith",
        --   "interview_date": "2026-04-05", "notes": "Phone screen"
        -- }

    -- Outcome
    outcome         VARCHAR(50),   -- won, lost, neutral, pending
    outcome_note    TEXT,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_pipeline_brain ON pipeline_items(brain_id);
CREATE INDEX idx_pipeline_stage ON pipeline_items(brain_id, stage);


-- ============================================
-- USER NOTIFICATION PREFERENCES
-- ============================================

CREATE TABLE notification_preferences (
    pref_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(user_id),

    -- Global preferences
    push_enabled    BOOLEAN NOT NULL DEFAULT TRUE,
    email_enabled   BOOLEAN NOT NULL DEFAULT TRUE,
    sms_enabled     BOOLEAN NOT NULL DEFAULT FALSE,
    sms_phone       VARCHAR(20),

    -- Digest preferences
    daily_digest    BOOLEAN NOT NULL DEFAULT TRUE,
    digest_time     TIME NOT NULL DEFAULT '08:00',
    digest_timezone VARCHAR(50) NOT NULL DEFAULT 'UTC',
    weekly_report   BOOLEAN NOT NULL DEFAULT TRUE,

    -- Quiet hours
    quiet_start     TIME,
    quiet_end       TIME,

    -- Push subscription
    push_subscription_json JSONB,  -- Web Push subscription object

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(user_id)
);
```

---

## Part 4: Services Architecture

### Service 1: Brain Manager Service

**Location:** `backend/app/services/brain_manager.py`

**Responsibilities:**
- Create Brain from template
- Run setup interview (stateful Q&A)
- Store and update Brain config
- Activate/pause/deactivate Brain
- Generate initial task batch when Brain activates

```python
# Pseudocode — Brain Manager

class BrainManager:

    async def create_brain(user_id, brain_type) -> Brain:
        """Create brain from template, start setup interview."""
        template = BRAIN_TEMPLATES[brain_type]
        brain = Brain(user_id=user_id, brain_type=brain_type, status='setup')
        interview = BrainInterview(
            brain_id=brain.brain_id,
            total_steps=len(template.setup_questions)
        )
        return brain

    async def answer_interview_step(brain_id, answer) -> NextQuestion | Complete:
        """Process user's answer, return next question or complete."""
        # Some questions are conditional:
        # If user says "auto-apply: yes" → skip approval config questions
        # If user says "Stocks" → ask stock-specific questions
        # If user says "Crypto" → ask crypto-specific questions

    async def activate_brain(brain_id):
        """Interview complete → activate Brain → schedule first run."""
        brain.status = 'active'
        brain.next_run_at = calculate_next_run(brain.run_schedule)
        # Generate initial tasks:
        # Job Searcher → create 'search_jobs' task immediately
        # Trader → create 'check_prices' task immediately
        # Social Media → create 'analyze_existing_content' task

    async def pause_brain(brain_id):
        """Pause all tasks and monitors for this Brain."""

    async def get_brain_dashboard(brain_id) -> BrainDashboard:
        """Return stats, recent activity, pending approvals, pipeline."""
```

**Brain Templates:**

```python
BRAIN_TEMPLATES = {
    "job_searcher": BrainTemplate(
        name="Job Searcher",
        description="Finds and applies to jobs, networks on LinkedIn, manages your pipeline",
        icon="briefcase",
        setup_questions=[
            {"key": "target_role", "question": "What role are you looking for?", "type": "text"},
            {"key": "locations", "question": "What locations work for you?", "type": "multi_text"},
            {"key": "remote_ok", "question": "Are you open to remote work?", "type": "boolean"},
            {"key": "salary_range", "question": "What's your salary range?", "type": "range", "unit": "USD"},
            {"key": "industries", "question": "What industries interest you?", "type": "multi_select",
             "options": ["Tech", "Finance", "Healthcare", "Education", "Retail", "Other"]},
            {"key": "resume", "question": "Upload your resume", "type": "file_upload"},
            {"key": "linkedin", "question": "Connect your LinkedIn account", "type": "connect_account",
             "provider": "linkedin"},
            {"key": "email", "question": "Connect your email for outreach", "type": "connect_account",
             "provider": "gmail"},
            {"key": "aggression", "question": "How many applications per day?",
             "type": "select", "options": ["5 (careful)", "15 (moderate)", "30 (aggressive)"]},
            {"key": "approval_mode", "question": "Should I ask before applying, or go ahead?",
             "type": "select", "options": ["Ask me every time", "Ask for emails only", "Full auto"]}
        ],
        default_monitors=[
            {"type": "job_match", "check_interval": "daily"},
        ],
        task_types=["search_jobs", "apply_job", "send_linkedin_request",
                     "send_cold_email", "reply_email", "followup_email", "prep_interview"]
    ),

    "trader": BrainTemplate(
        name="Trader",
        description="Monitors markets, executes trades, manages your portfolio",
        icon="chart",
        setup_questions=[
            {"key": "markets", "question": "What do you trade?",
             "type": "multi_select", "options": ["Stocks", "Crypto", "Forex", "Options"]},
            {"key": "tickers", "question": "What tickers do you want to watch?", "type": "multi_text"},
            {"key": "brokerage", "question": "Connect your brokerage", "type": "connect_account",
             "provider": "robinhood"},
            {"key": "risk_tolerance", "question": "Risk tolerance?",
             "type": "select", "options": ["Conservative", "Moderate", "Aggressive"]},
            {"key": "daily_limit", "question": "Maximum daily trade amount?", "type": "number", "unit": "USD"},
            {"key": "rules", "question": "Any trading rules? (e.g., 'never more than 5% in one stock')",
             "type": "text"},
            {"key": "approval_mode", "question": "Auto-trade or approve each trade?",
             "type": "select", "options": ["Approve each trade", "Auto under $100", "Full auto"]}
        ],
        default_monitors=[
            {"type": "price_threshold", "check_interval": "every_5min"},
        ],
        task_types=["check_prices", "execute_trade", "rebalance", "research_stock", "daily_digest"]
    ),

    # ... social_media, coder, finance, custom templates
}
```

---

### Service 2: Task Execution Engine

**Location:** `backend/app/services/task_engine.py`

**Responsibilities:**
- Pull tasks from queue
- Execute via LangGraph agent + browser automation
- Capture screenshots as proof
- Log all actions
- Handle retries and failures

```
Task Lifecycle:

  Brain Schedule Fires
         │
         ▼
  Task Generator creates tasks
  (e.g., "search for jobs matching criteria")
         │
         ▼
  ┌──────────────┐     needs_approval?
  │ pending_approval│◄── YES ──┐
  └───────┬──────┘            │
          │ user approves      │
          ▼                    │
  ┌──────────────┐     NO ────┘
  │   queued     │
  └───────┬──────┘
          │ worker picks up
          ▼
  ┌──────────────┐
  │   running    │
  └───────┬──────┘
          │
     ┌────┴────┐
     ▼         ▼
 completed   failed
     │         │
     ▼         ▼
  log activity  retry? → back to queued
                  │
                  ▼ max retries
              notify user
```

**How tasks execute (Job Searcher example):**

```
Task: apply_job
Input: { job_url, company, role }

Agent Steps:
  1. Get browser session for user's LinkedIn account
  2. Navigate to job_url
  3. Screenshot the job posting (proof)
  4. Click "Apply" button
  5. Fill in application form fields using user's profile
  6. Upload tailored resume (generated earlier)
  7. Paste cover letter (generated earlier)
  8. Submit application
  9. Screenshot confirmation page (proof)
  10. Log: "Applied to {company} {role} — confirmation #{id}"
  11. Update pipeline_item stage: found → applied
  12. Create follow-up task for 5 days later
```

---

### Service 3: Browser Pool Service

**Location:** `backend/app/services/browser_pool.py`

**Responsibilities:**
- Maintain persistent Playwright browser contexts per connected account
- Store and restore cookies/sessions so user stays logged in
- Rate limit actions to avoid platform bans
- Simulate human-like behavior

```
Browser Pool Architecture:

  ┌─────────────────────────────────────────────┐
  │              Browser Pool                    │
  │                                              │
  │  ┌─────────────┐  ┌─────────────┐          │
  │  │ LinkedIn     │  │ Gmail       │          │
  │  │ Context #1   │  │ Context #1  │          │
  │  │ (user: john) │  │ (user: john)│          │
  │  │ cookies: *** │  │ cookies: ***│          │
  │  └─────────────┘  └─────────────┘          │
  │                                              │
  │  ┌─────────────┐  ┌─────────────┐          │
  │  │ Indeed       │  │ Robinhood   │          │
  │  │ Context #2   │  │ Context #3  │          │
  │  │ (user: jane) │  │ (user: jane)│          │
  │  └─────────────┘  └─────────────┘          │
  │                                              │
  │  Rate Limiter:                               │
  │    LinkedIn: max 25 actions/day              │
  │    Gmail: max 50 emails/day                  │
  │    Indeed: max 20 applications/day           │
  │                                              │
  │  Anti-Detection:                             │
  │    Random delays: 2-8 seconds between actions│
  │    Mouse movement: human-like curves         │
  │    Viewport randomization                    │
  │    Fingerprint rotation                      │
  └─────────────────────────────────────────────┘
```

**Key behaviors:**
- User logs in ONCE through the app (Playwright shows the login page in an iframe or popup)
- App captures and encrypts cookies after login
- On next task, app restores cookies → user is already logged in
- If session expires → notify user to re-login (don't store passwords)

---

### Service 4: Monitor Service

**Location:** `backend/app/services/monitor_service.py`

**Responsibilities:**
- Check external data sources on schedule
- Evaluate conditions
- Trigger notifications or create tasks

```
Monitor Check Flow:

  Scheduler fires (every 5min/hourly/daily)
         │
         ▼
  Load active monitors due for check
         │
         ▼
  For each monitor:
    1. Fetch current data (API call, scrape, etc.)
    2. Compare against condition
    3. If triggered:
       a. Create notification
       b. If auto_create_task: create task in execution engine
       c. Update monitor state (current_value, last_triggered)
       d. Log to monitor_history
    4. If not triggered:
       a. Update current_value
       b. Log check to monitor_history
    5. Calculate next_check_at
```

**Data feed connectors:**

| Monitor Type | Data Source | Method |
|---|---|---|
| Stock price | Alpha Vantage / Polygon.io / Yahoo Finance | REST API |
| Crypto price | CoinGecko / Binance API | REST API |
| News keywords | NewsAPI / Google News RSS | REST API / RSS |
| Job match | LinkedIn / Indeed | Browser scrape (via browser pool) |
| Website change | Any URL | Fetch + diff |
| Rate change | Bankrate / FRED API | REST API |

---

### Service 5: Notification Service

**Location:** `backend/app/services/notification_service.py`

```
Notification Flow:

  Event occurs (task completed, monitor triggered, etc.)
         │
         ▼
  Create notification record in DB
         │
         ▼
  Check user notification preferences
         │
         ├─ Push enabled? → Send via Web Push / FCM
         ├─ Email enabled? → Send via SendGrid/SES
         ├─ SMS enabled? → Send via Twilio
         └─ Always → In-app notification (WebSocket + inbox)
         │
         ▼
  Update notification delivery status

  Daily Digest (runs at user's preferred time):
    1. Collect all brain activity from past 24h
    2. Group by brain
    3. Generate summary per brain
    4. Send single digest email
```

---

## Part 5: API Routes

### New API Endpoints

```
# ── Brain Management ──────────────────────────────

GET    /api/v1/brains                       # List user's brains
POST   /api/v1/brains                       # Create brain (pick type)
GET    /api/v1/brains/:id                   # Get brain details + stats
PATCH  /api/v1/brains/:id                   # Update brain config
DELETE /api/v1/brains/:id                   # Delete brain
POST   /api/v1/brains/:id/activate          # Activate (start working)
POST   /api/v1/brains/:id/pause             # Pause
POST   /api/v1/brains/:id/resume            # Resume

GET    /api/v1/brains/templates             # List available brain templates


# ── Setup Interview ───────────────────────────────

GET    /api/v1/brains/:id/interview         # Get current interview state
POST   /api/v1/brains/:id/interview/answer  # Submit answer to current step
POST   /api/v1/brains/:id/interview/skip    # Skip optional step
POST   /api/v1/brains/:id/interview/back    # Go back to previous step


# ── Connected Accounts ────────────────────────────

GET    /api/v1/accounts                     # List connected accounts
POST   /api/v1/accounts/connect             # Start OAuth flow or browser login
DELETE /api/v1/accounts/:id                 # Disconnect account
POST   /api/v1/accounts/:id/reauth         # Re-authenticate expired account
GET    /api/v1/accounts/:id/status          # Check connection health


# ── Tasks ─────────────────────────────────────────

GET    /api/v1/brains/:id/tasks             # List tasks for a brain (filterable by status)
GET    /api/v1/tasks/:id                    # Get task detail + action log + screenshots
POST   /api/v1/tasks/:id/approve            # Approve pending task
POST   /api/v1/tasks/:id/reject             # Reject pending task
POST   /api/v1/tasks/:id/cancel             # Cancel queued/running task
POST   /api/v1/tasks/:id/retry              # Retry failed task

GET    /api/v1/tasks/pending                # All pending approvals across all brains
POST   /api/v1/tasks/bulk-approve           # Approve multiple tasks at once


# ── Monitors ──────────────────────────────────────

GET    /api/v1/brains/:id/monitors          # List monitors for a brain
POST   /api/v1/brains/:id/monitors          # Create monitor
PATCH  /api/v1/monitors/:id                 # Update monitor
DELETE /api/v1/monitors/:id                 # Delete monitor
POST   /api/v1/monitors/:id/pause           # Pause monitor
POST   /api/v1/monitors/:id/resume          # Resume monitor
GET    /api/v1/monitors/:id/history         # Check history for a monitor


# ── Pipeline ──────────────────────────────────────

GET    /api/v1/brains/:id/pipeline          # Get pipeline items (kanban view)
PATCH  /api/v1/pipeline/:id                 # Manually move pipeline item
GET    /api/v1/pipeline/:id                 # Get pipeline item detail


# ── Activity & Notifications ──────────────────────

GET    /api/v1/brains/:id/activity          # Activity feed for a brain
GET    /api/v1/notifications                # User's notification inbox
PATCH  /api/v1/notifications/:id/read       # Mark notification as read
POST   /api/v1/notifications/read-all       # Mark all as read
GET    /api/v1/notifications/preferences    # Get notification preferences
PUT    /api/v1/notifications/preferences    # Update notification preferences


# ── Files ─────────────────────────────────────────

POST   /api/v1/brains/:id/files             # Upload file to brain
GET    /api/v1/brains/:id/files             # List files in brain
DELETE /api/v1/files/:id                    # Delete file


# ── Brain Chat (for manual interaction) ───────────

POST   /api/v1/brains/:id/chat             # Send message to brain (ask questions, give instructions)
GET    /api/v1/brains/:id/chat/history      # Chat history with brain


# ── Dashboard ─────────────────────────────────────

GET    /api/v1/dashboard                    # Global dashboard (all brains summary)
GET    /api/v1/dashboard/stats              # Aggregate stats
```

---

## Part 6: What We Reuse From Existing Codebase

### Direct Reuse (rename/extend)

| Existing Component | Reuse As | Changes Needed |
|---|---|---|
| `Product` model | `Brain` model | Rename, add brain_type, config_json, approval_mode, schedule fields |
| `Conversation` + `ConversationMessage` | Brain Chat | Add brain_id FK, keep as-is |
| `AgentSession` | Task execution sessions | Already tracks iterations, messages, token usage |
| `SOP` + `AutomationRun` | Brain schedule + task runs | SOP becomes Brain schedule config; AutomationRun becomes task execution log |
| `agent_service.py` (LangGraph) | Task Executor core | Same CodeAct agent, new tool set per Brain type |
| `browser_manager.py` (Playwright) | Browser Pool foundation | Extend: persistent sessions, cookie storage, multi-context |
| `scheduler_service.py` (APScheduler) | Brain + Monitor scheduler | Already handles cron/interval/one-shot triggers |
| `security.py` (JWT + RBAC) | Auth layer | Keep as-is, simplify roles for consumer |
| `encryption.py` (Fernet) | Token/cookie encryption | Same encryption for connected account tokens |
| `email_connection.py` | Connected accounts (email) | Generalize to multi-provider account model |
| `notifications/` (Slack, SMTP) | Notification service base | Add push + SMS channels |
| `kb_search.py` + `kb_store.py` | Brain knowledge search | Same RAG for uploaded resumes/docs per Brain |
| `file_processor.py` | File upload processing | Generalize: PDF extraction already exists |
| `audit_log.py` | Brain activity log | Same structure, more action types |

### Remove (not needed for consumer)

| Component | Why Remove |
|---|---|
| `Pod` model + `pod-agent/` (Go) | No local agents — all processing is cloud-hosted |
| `FolderGroup` + `FolderPath` | No local folders — files uploaded to S3 |
| `TerminalSession` + `pty_manager.py` | No terminal for consumers |
| `MCP` models + builder | Developer feature |
| `ScreenOps` tool | Replaced by browser pool (same Playwright, different abstraction) |
| `terminal_ws.py` | No terminal |
| `browser_ws.py` | Replace with managed browser pool (no user-facing browser control) |
| LDAP, Azure AD auth | Consumer doesn't need enterprise SSO |
| `Documentation` model | Replace with Brain knowledge |
| `ChunkRecord` model | ChromaDB-only, no SQLite chunks |

### Modify Significantly

| Component | What Changes |
|---|---|
| `main.py` | New lifespan: start task workers, monitor service, notification service |
| `database.py` | PostgreSQL driver, new tables, new migrations |
| `config.py` | Add S3, Redis, Stripe, Twilio, SendGrid, stock API configs |
| `agent_service.py` | Multiple agent profiles per Brain type (different system prompts, tools) |
| `auth.py` API | Simplified: email + Google/Apple sign-in only |
| Frontend (entire) | Complete rebuild: Brain dashboard, pipeline view, setup wizard, approval inbox |

---

## Part 7: Infrastructure

### Production Deployment

```
┌─────────────────────────────────────────────────────────┐
│                    Cloud Infrastructure                   │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  Web Server   │  │  API Server  │  │  Worker Pool │  │
│  │  (Nginx/CDN)  │  │  (FastAPI)   │  │  (N workers) │  │
│  │               │  │  x3 replicas │  │              │  │
│  │  React SPA    │  │              │  │  Task exec   │  │
│  │  static files │  │  REST + WS   │  │  Browser     │  │
│  │               │  │              │  │  automation   │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│                            │                  │          │
│         ┌──────────────────┼──────────────────┘          │
│         │                  │                             │
│  ┌──────┴──────┐  ┌───────┴───────┐  ┌──────────────┐  │
│  │ PostgreSQL   │  │    Redis      │  │     S3       │  │
│  │ (Supabase    │  │  (Upstash     │  │  (uploads,   │  │
│  │  or RDS)     │  │   or Redis    │  │  screenshots,│  │
│  │              │  │   Cloud)      │  │  resumes)    │  │
│  │  - users     │  │              │  │              │  │
│  │  - brains    │  │  - task queue│  │              │  │
│  │  - tasks     │  │  - sessions  │  │              │  │
│  │  - monitors  │  │  - cache     │  │              │  │
│  │  - activity  │  │  - pub/sub   │  │              │  │
│  └─────────────┘  └──────────────┘  └──────────────┘  │
│                                                          │
│  ┌──────────────┐  ┌──────────────┐                     │
│  │  ChromaDB    │  │ External APIs│                     │
│  │  (vectors    │  │              │                     │
│  │   for RAG)   │  │  - Stock APIs│                     │
│  │              │  │  - News APIs │                     │
│  └──────────────┘  │  - Job boards│                     │
│                     │  - Twilio    │                     │
│                     │  - SendGrid  │                     │
│                     └──────────────┘                     │
└─────────────────────────────────────────────────────────┘
```

### Worker Architecture

```
Worker Process (each worker runs independently):

  while True:
    1. Pop next task from Redis queue (BRPOP, blocking)
    2. Load task details from PostgreSQL
    3. Load brain config
    4. Load connected account for this task's provider
    5. Get or create browser context (restore cookies)
    6. Build LangGraph agent with brain-specific tools
    7. Execute task:
       a. Navigate, interact, capture screenshots
       b. Log each step to brain_activity
       c. Update task status in real-time (WebSocket → frontend)
    8. On success:
       a. Mark task completed
       b. Update pipeline item
       c. Create follow-up tasks if needed
       d. Send notification
    9. On failure:
       a. If retries left → re-queue with backoff
       b. If max retries → mark failed, notify user
    10. Save updated cookies back to connected_accounts
```

---

## Part 8: Security Considerations

### Account Safety

| Concern | Mitigation |
|---|---|
| Stored credentials | Never store passwords. OAuth tokens + browser cookies only, encrypted at rest (AES-256) |
| Platform bans | Rate limiting per platform, human-like delays, fingerprint rotation |
| User reputation | Every outgoing message/application shown to user. Approval mode for first-time users |
| Data breach | All tokens encrypted with per-user key derived from master secret. DB encryption at rest |
| Rogue agent | Max action limits per day per Brain. Kill switch: user can pause instantly |

### Rate Limits (Per Platform)

| Platform | Daily Limit | Delay Between Actions |
|---|---|---|
| LinkedIn connection requests | 20-25/day | 30-120 seconds |
| LinkedIn messages | 50/day | 15-60 seconds |
| Indeed applications | 20/day | 60-180 seconds |
| Gmail sends | 100/day | 5-30 seconds |
| Twitter posts | 25/day | 300+ seconds |

### User Control Hierarchy

```
Level 1: Approve Everything (default for new users)
  → User sees every action before it happens
  → Must tap "Approve" or "Reject"

Level 2: Approve Important Only (after trust is built)
  → Auto: search, research, draft content
  → Approve: send email, apply, connect, post, trade

Level 3: Full Auto (power users)
  → Everything auto-executes within daily limits
  → User gets digest notification
  → Can pause instantly from any notification
```

---

## Part 9: User Experience Flow

### First-Time User Journey

```
1. SIGN UP
   → Email + password, or Google/Apple sign-in
   → "Welcome to ReTrace! Let's set up your first Brain."

2. CHOOSE A BRAIN
   → Grid of Brain cards: Job Searcher, Trader, Social Media, Coder, Finance
   → User taps "Job Searcher"

3. SETUP INTERVIEW (conversational UI, not a form)
   Brain: "Hi! I'll help you find your next job. What role are you looking for?"
   User: "Senior Product Manager"
   Brain: "Great! What locations work for you?"
   User: "Austin, Remote"
   Brain: "Salary range?"
   User: "$150k - $200k"
   ...
   Brain: "Now let's connect your LinkedIn so I can start networking for you."
   → OAuth popup → user logs in → connected
   Brain: "Last thing — should I apply automatically, or show you each one first?"
   User: "Show me first"
   Brain: "All set! I'm starting to search now. I'll notify you when I find matches."

4. BRAIN GOES TO WORK
   → User sees dashboard update in real-time
   → First notification in minutes: "Found 8 matching jobs!"
   → User reviews, approves applications
   → Brain applies, follows up, tracks everything

5. DAILY LIFE
   → Morning notification: "Your Job Searcher found 5 new matches overnight"
   → Tap notification → see matches → approve/reject
   → Check pipeline: 34 applied, 8 responses, 2 interviews
   → Brain: "You have an interview with Stripe tomorrow. Here's your prep guide."
```

---

## Part 10: File Structure (New)

```
main-app/
├── backend/
│   ├── app/
│   │   ├── main.py                         # FastAPI app + lifespan
│   │   ├── core/
│   │   │   ├── config.py                   # Settings (Postgres, Redis, S3, APIs)
│   │   │   ├── security.py                 # JWT auth (simplified for consumer)
│   │   │   └── encryption.py               # Fernet encryption for tokens
│   │   ├── db/
│   │   │   └── database.py                 # PostgreSQL + async sessions
│   │   ├── models/
│   │   │   ├── user.py                     # User (simplified)
│   │   │   ├── tenant.py                   # Account/org
│   │   │   ├── brain.py                    # NEW: Brain + BrainInterview
│   │   │   ├── connected_account.py        # NEW: OAuth/cookie accounts
│   │   │   ├── task.py                     # NEW: BrainTask
│   │   │   ├── monitor.py                  # NEW: Monitor + MonitorHistory
│   │   │   ├── pipeline.py                 # NEW: PipelineItem
│   │   │   ├── notification.py             # NEW: Notification + Preferences
│   │   │   ├── uploaded_file.py            # NEW: S3-backed uploads
│   │   │   ├── browser_session.py          # NEW: Persistent browser state
│   │   │   ├── brain_activity.py           # NEW: Activity log
│   │   │   ├── conversation.py             # KEEP: Chat with brain
│   │   │   ├── audit_log.py               # KEEP: Compliance
│   │   │   └── user_session.py            # KEEP: Login tracking
│   │   ├── api/
│   │   │   ├── auth.py                     # SIMPLIFY: email + Google/Apple
│   │   │   ├── brains.py                   # NEW: Brain CRUD + interview
│   │   │   ├── tasks.py                    # NEW: Task approval + management
│   │   │   ├── monitors.py                 # NEW: Monitor CRUD
│   │   │   ├── pipeline.py                 # NEW: Pipeline view
│   │   │   ├── accounts.py                 # NEW: Connected accounts
│   │   │   ├── notifications.py            # NEW: Notification inbox
│   │   │   ├── files.py                    # MODIFY: S3 upload
│   │   │   ├── dashboard.py               # NEW: Global dashboard
│   │   │   ├── chat.py                     # KEEP: Chat with brain
│   │   │   └── health.py                  # KEEP
│   │   ├── services/
│   │   │   ├── brain_manager.py            # NEW: Brain lifecycle
│   │   │   ├── task_engine.py              # NEW: Task execution (wraps agent_service)
│   │   │   ├── browser_pool.py             # NEW: Persistent Playwright sessions
│   │   │   ├── monitor_service.py          # NEW: Watch + check + trigger
│   │   │   ├── notification_service.py     # NEW: Multi-channel delivery
│   │   │   ├── agent_service.py            # MODIFY: Brain-specific agent profiles
│   │   │   ├── scheduler_service.py        # KEEP: APScheduler
│   │   │   └── data_feeds/                 # NEW: External data connectors
│   │   │       ├── stock_feed.py           # Alpha Vantage / Polygon
│   │   │       ├── news_feed.py            # NewsAPI / RSS
│   │   │       ├── job_feed.py             # LinkedIn/Indeed scraper
│   │   │       └── rate_feed.py            # Interest rates / FRED
│   │   ├── tools/                          # Agent tools per brain type
│   │   │   ├── job_tools.py               # NEW: apply_job, send_request, etc.
│   │   │   ├── trading_tools.py           # NEW: execute_trade, check_price, etc.
│   │   │   ├── social_tools.py            # NEW: create_post, reply_comment, etc.
│   │   │   ├── coding_tools.py            # MODIFY: from existing tools
│   │   │   ├── web_search.py              # KEEP
│   │   │   ├── web_fetch.py               # KEEP
│   │   │   └── file_ops.py               # KEEP
│   │   ├── rag/                            # KEEP: for uploaded file Q&A
│   │   │   ├── kb_search.py
│   │   │   ├── kb_store.py
│   │   │   ├── file_processor.py
│   │   │   └── models.py
│   │   └── brain_templates/               # NEW: Template definitions
│   │       ├── job_searcher.py
│   │       ├── trader.py
│   │       ├── social_media.py
│   │       ├── coder.py
│   │       ├── personal_finance.py
│   │       └── custom.py
│   └── requirements.txt
├── frontend/                               # REBUILD: Consumer mobile-first PWA
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Home.tsx                   # Brain grid / dashboard
│   │   │   ├── BrainSetup.tsx             # Setup interview UI
│   │   │   ├── BrainDashboard.tsx         # Single brain view
│   │   │   ├── Tasks.tsx                  # Approval inbox
│   │   │   ├── Pipeline.tsx               # Kanban pipeline view
│   │   │   ├── Monitors.tsx               # Monitor list + create
│   │   │   ├── Activity.tsx               # Activity feed
│   │   │   ├── Notifications.tsx          # Notification inbox
│   │   │   ├── Chat.tsx                   # Chat with brain
│   │   │   ├── Settings.tsx               # Account + notification preferences
│   │   │   └── Login.tsx                  # Sign in / sign up
│   │   ├── components/
│   │   │   ├── BrainCard.tsx
│   │   │   ├── TaskApprovalCard.tsx
│   │   │   ├── PipelineBoard.tsx
│   │   │   ├── MonitorWidget.tsx
│   │   │   ├── ActivityItem.tsx
│   │   │   ├── InterviewChat.tsx
│   │   │   ├── AccountConnector.tsx
│   │   │   └── NotificationBell.tsx
│   │   └── ...
│   └── package.json
├── docker-compose.yml                      # Postgres + Redis + API + Workers
├── Dockerfile.api                          # FastAPI container
├── Dockerfile.worker                       # Task worker container
└── ARCHITECTURE_BRAINS.md                  # This document
```

---

## Part 11: Implementation Priority

### Phase 1: Foundation (Weeks 1-4)
- PostgreSQL migration
- Brain model + templates (Job Searcher first)
- Setup interview API + basic UI
- Connected accounts (LinkedIn OAuth, Gmail OAuth)
- File upload to S3

### Phase 2: Execution Engine (Weeks 5-8)
- Browser pool (Playwright persistent sessions)
- Task model + queue (Redis)
- Job Searcher tools: search, apply, LinkedIn request
- Approval flow (pending → approve → execute)
- Activity logging + screenshots

### Phase 3: Monitoring + Notifications (Weeks 9-11)
- Monitor model + scheduler
- Stock price feed (Alpha Vantage)
- Job match monitoring
- Push notifications (Web Push)
- Email notifications (SendGrid)
- Daily digest

### Phase 4: Pipeline + Dashboard (Weeks 12-13)
- Pipeline view (kanban)
- Brain dashboard with stats
- Global dashboard (all brains)
- Notification inbox

### Phase 5: Second Brain (Weeks 14-16)
- Trader Brain (brokerage connection, price tools, trade execution)
- Social Media Brain (platform connections, content tools)

### Phase 6: Polish + Launch (Weeks 17-18)
- Mobile-responsive PWA
- Onboarding polish
- Rate limiting + anti-detection hardening
- Billing (Stripe)
