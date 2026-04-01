"""
LinkedIn Job Search & Apply tools — browser automation via Playwright.

These tools operate on a BrowserSession managed by brain_browser_manager.
Every action is streamed live to the user's Brain detail page via WebSocket.
"""

from __future__ import annotations

import asyncio
import json
import random
import re
from typing import Optional
from pathlib import Path

import structlog

logger = structlog.get_logger()


# ── Blockage / Captcha Detection ───────────────────────────────────────

async def detect_blockage(page) -> dict | None:
    """
    Check if the current page shows a captcha, login wall, verification,
    rate limit, or other blockage that requires human intervention.

    Returns a dict with alert_type and message, or None if no blockage.
    """
    try:
        url = page.url.lower()
        page_text = ""
        try:
            page_text = (await page.inner_text("body"))[:3000].lower()
        except Exception:
            pass
        title = ""
        try:
            title = (await page.title()).lower()
        except Exception:
            pass

        # ── Captcha detection ──
        captcha_selectors = [
            'iframe[src*="captcha"]',
            'iframe[src*="recaptcha"]',
            'iframe[src*="hcaptcha"]',
            'iframe[src*="arkoselabs"]',
            '#captcha', '.captcha',
            '[data-captcha]',
            '#recaptcha', '.g-recaptcha',
            'iframe[title*="reCAPTCHA"]',
            '#arkose', 'iframe[data-e2e="enforcement-frame"]',
        ]
        for sel in captcha_selectors:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    return {
                        "alert_type": "captcha",
                        "message": "CAPTCHA detected — please solve it in the Live View, then click Resume.",
                    }
            except Exception:
                continue

        # Check page text for captcha keywords
        captcha_keywords = ["verify you're human", "security verification", "prove you're not a robot",
                           "complete the security check", "captcha", "challenge"]
        if any(kw in page_text for kw in captcha_keywords):
            return {
                "alert_type": "captcha",
                "message": "Security challenge detected — please solve it in the Live View, then click Resume.",
            }

        # ── Login wall detection ──
        if any(x in url for x in ["/login", "/signin", "/authwall", "/uas/login", "/session_redirect"]):
            return {
                "alert_type": "login_required",
                "message": "Session expired — please log in via the Live View, then click Resume.",
            }

        login_selectors = [
            'form[action*="login"]', 'form[action*="signin"]',
            '#login-form', '.login-form',
            'input[name="session_key"]',  # LinkedIn login
        ]
        for sel in login_selectors:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    # Only flag if we're not intentionally on a login page
                    if "/feed" not in url and "/jobs" not in url:
                        return {
                            "alert_type": "login_required",
                            "message": "Login page detected — please sign in via the Live View, then click Resume.",
                        }
            except Exception:
                continue

        # ── Verification / 2FA detection ──
        if "/checkpoint" in url or "/challenge" in url or "/two-step-verification" in url:
            return {
                "alert_type": "verification",
                "message": "Account verification required — please complete it in the Live View, then click Resume.",
            }

        verification_keywords = ["verify your identity", "two-step verification", "phone verification",
                                "enter the code", "security code", "confirm it's you", "confirm your identity"]
        if any(kw in page_text for kw in verification_keywords):
            return {
                "alert_type": "verification",
                "message": "Identity verification required — please complete it in the Live View, then click Resume.",
            }

        # ── Rate limit / Block detection ──
        if any(x in url for x in ["/error", "/restricted", "/unavailable"]):
            return {
                "alert_type": "blocked",
                "message": "Account may be rate-limited or restricted. Check the Live View for details.",
            }

        block_keywords = ["you've reached the", "rate limit", "temporarily restricted",
                         "unusual activity", "account restricted", "try again later",
                         "too many requests", "we've restricted your account"]
        if any(kw in page_text for kw in block_keywords):
            return {
                "alert_type": "blocked",
                "message": "Rate limit or restriction detected. Please review in the Live View and click Resume when ready.",
            }

        # ── Generic error page ──
        error_keywords = ["something went wrong", "page not found", "this page isn't available",
                         "access denied", "403 forbidden", "500 internal"]
        if any(kw in page_text for kw in error_keywords) or any(kw in title for kw in error_keywords):
            # Don't flag as blockage for normal 404s on job listings
            if "job" not in page_text[:200]:
                return {
                    "alert_type": "error",
                    "message": "Error page detected. Please check the Live View and click Resume to continue.",
                }

        return None

    except Exception as e:
        logger.warning("blockage_detection_error", error=str(e))
        return None


async def check_and_handle_blockage(page, browser_session, description: str = "action") -> bool:
    """
    Check for blockages and if found, request human intervention.
    Pauses execution until the user resolves it or timeout (5 min).

    Args:
        page: Playwright page
        browser_session: BrainBrowserSession instance
        description: What the brain was doing when blocked

    Returns:
        True if resolved (or no blockage), False if timed out
    """
    blockage = await detect_blockage(page)
    if not blockage:
        return True

    logger.warning("blockage_detected",
                   brain_id=browser_session.brain_id,
                   alert_type=blockage["alert_type"],
                   description=description)

    # Request human help — this pauses execution
    resolved = await browser_session.request_human_help(
        alert_type=blockage["alert_type"],
        message=blockage["message"],
        timeout_seconds=300,  # 5 minutes
    )

    if resolved:
        await browser_session.broadcast_status(f"Human resolved {blockage['alert_type']} — resuming {description}")
        # Small delay after human intervention
        await asyncio.sleep(2)
        return True
    else:
        await browser_session.broadcast_status(f"Timed out waiting for human — skipping {description}")
        return False


# ── Human-like delays ──────────────────────────────────────────────────

async def _human_delay(min_s: float = 0.5, max_s: float = 2.0):
    """Random delay to mimic human behavior."""
    await asyncio.sleep(random.uniform(min_s, max_s))


async def _human_type(page, text: str):
    """Type text with human-like delays between keystrokes."""
    for char in text:
        await page.keyboard.type(char)
        await asyncio.sleep(random.uniform(0.03, 0.12))


async def _human_scroll(page, distance: int = 300):
    """Smooth scroll like a human."""
    steps = random.randint(3, 6)
    per_step = distance // steps
    for _ in range(steps):
        await page.mouse.wheel(0, per_step)
        await asyncio.sleep(random.uniform(0.05, 0.15))


# ── LinkedIn Login via Cookies ─────────────────────────────────────────

async def inject_linkedin_cookies(context, cookies: list[dict]) -> bool:
    """
    Inject stored LinkedIn cookies into a browser context.
    Returns True if cookies were successfully injected.
    """
    try:
        # Ensure cookies have the right domain format
        linkedin_cookies = []
        for cookie in cookies:
            c = dict(cookie)
            if 'domain' not in c:
                c['domain'] = '.linkedin.com'
            if 'path' not in c:
                c['path'] = '/'
            linkedin_cookies.append(c)

        await context.add_cookies(linkedin_cookies)
        logger.info("linkedin_cookies_injected", count=len(linkedin_cookies))
        return True
    except Exception as e:
        logger.error("linkedin_cookie_inject_failed", error=str(e))
        return False


async def verify_linkedin_login(page, browser_session=None) -> dict:
    """
    Navigate to LinkedIn and verify the session is valid.
    If a browser_session is provided, will detect blockages and
    request human help for captchas/login walls.
    Returns login status info.
    """
    try:
        await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=20000)
        await _human_delay(2, 4)

        # Check for blockages (captcha, verification, etc.)
        if browser_session:
            resolved = await check_and_handle_blockage(page, browser_session, "LinkedIn login verification")
            if not resolved:
                return {"logged_in": False, "reason": "Blockage not resolved by user"}

        url = page.url
        if "/login" in url or "/authwall" in url or "/checkpoint" in url:
            if browser_session:
                # Give the user a chance to log in manually
                resolved = await browser_session.request_human_help(
                    alert_type="login_required",
                    message="LinkedIn session expired. Please log in via the Live View, then click Resume.",
                    timeout_seconds=300,
                )
                if resolved:
                    # Re-check after human login
                    await _human_delay(2, 3)
                    url = page.url
                    if "/login" not in url and "/authwall" not in url:
                        return {"logged_in": True, "url": url}
                return {"logged_in": False, "reason": "Session expired — user did not log in"}
            return {"logged_in": False, "reason": "Session expired — redirected to login"}

        # Check for feed indicators
        try:
            await page.wait_for_selector('[data-test-id="feed"], .feed-shared-update-v2, .scaffold-layout__main', timeout=8000)
            return {"logged_in": True, "url": url}
        except Exception:
            # Might still be logged in but on a different page
            if "linkedin.com" in url and "/login" not in url:
                return {"logged_in": True, "url": url}
            return {"logged_in": False, "reason": "Could not verify feed page"}

    except Exception as e:
        return {"logged_in": False, "reason": str(e)}


# ── Job Search ─────────────────────────────────────────────────────────

async def linkedin_search_jobs(
    page,
    keywords: str,
    location: str = "",
    filters: Optional[dict] = None,
    max_results: int = 20,
    browser_session=None,
) -> list[dict]:
    """
    Search LinkedIn Jobs and return structured results.

    Args:
        page: Playwright page with active LinkedIn session
        keywords: Job search keywords (e.g., "Python Developer")
        location: Location filter (e.g., "San Francisco, CA")
        filters: Optional filters dict (experience_level, job_type, remote, date_posted)
        max_results: Max number of results to return

    Returns:
        List of job dicts with title, company, location, url, posted_date
    """
    filters = filters or {}
    logger.info("linkedin_job_search", keywords=keywords, location=location)

    # Build search URL
    params = [f"keywords={keywords.replace(' ', '%20')}"]
    if location:
        params.append(f"location={location.replace(' ', '%20')}")

    # Experience level filters
    exp_map = {
        "internship": "1", "entry": "2", "associate": "3",
        "mid_senior": "4", "director": "5", "executive": "6",
    }
    if filters.get("experience_level"):
        levels = filters["experience_level"] if isinstance(filters["experience_level"], list) else [filters["experience_level"]]
        exp_vals = [exp_map.get(l, l) for l in levels]
        params.append(f"f_E={','.join(exp_vals)}")

    # Job type filters
    type_map = {
        "full_time": "F", "part_time": "P", "contract": "C",
        "temporary": "T", "internship": "I",
    }
    if filters.get("job_type"):
        types = filters["job_type"] if isinstance(filters["job_type"], list) else [filters["job_type"]]
        type_vals = [type_map.get(t, t) for t in types]
        params.append(f"f_JT={','.join(type_vals)}")

    # Remote filter
    remote_map = {"on_site": "1", "remote": "2", "hybrid": "3"}
    if filters.get("remote"):
        params.append(f"f_WT={remote_map.get(filters['remote'], '2')}")

    # Date posted
    date_map = {"past_24h": "r86400", "past_week": "r604800", "past_month": "r2592000"}
    if filters.get("date_posted"):
        params.append(f"f_TPR={date_map.get(filters['date_posted'], 'r604800')}")

    # Easy Apply only
    if filters.get("easy_apply"):
        params.append("f_AL=true")

    search_url = f"https://www.linkedin.com/jobs/search/?{'&'.join(params)}"

    await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
    await _human_delay(2, 4)

    # Check for blockages after navigation
    if browser_session:
        resolved = await check_and_handle_blockage(page, browser_session, "job search")
        if not resolved:
            return []

    # Wait for job listings to load
    try:
        await page.wait_for_selector('.jobs-search-results-list, .scaffold-layout__list', timeout=10000)
    except Exception:
        # Might be a blockage that wasn't caught above
        if browser_session:
            resolved = await check_and_handle_blockage(page, browser_session, "job search results")
            if resolved:
                try:
                    await page.wait_for_selector('.jobs-search-results-list, .scaffold-layout__list', timeout=10000)
                except Exception:
                    pass
        logger.warning("job_results_not_found", url=search_url)
        return []

    # Scroll to load more results
    for _ in range(3):
        await _human_scroll(page, 500)
        await _human_delay(1, 2)

    # Extract job listings
    jobs = await page.evaluate("""() => {
        const cards = document.querySelectorAll('.job-card-container, .jobs-search-results__list-item, [data-job-id]');
        const results = [];
        cards.forEach(card => {
            try {
                const titleEl = card.querySelector('.job-card-list__title, .job-card-container__link, a[data-control-name]');
                const companyEl = card.querySelector('.job-card-container__primary-description, .job-card-container__company-name, .artdeco-entity-lockup__subtitle');
                const locationEl = card.querySelector('.job-card-container__metadata-item, .artdeco-entity-lockup__caption');
                const linkEl = card.querySelector('a[href*="/jobs/view/"]');
                const dateEl = card.querySelector('time, .job-card-container__footer-item');

                if (titleEl) {
                    results.push({
                        title: titleEl.textContent.trim(),
                        company: companyEl ? companyEl.textContent.trim() : '',
                        location: locationEl ? locationEl.textContent.trim() : '',
                        url: linkEl ? linkEl.href.split('?')[0] : '',
                        posted_date: dateEl ? dateEl.textContent.trim() : '',
                        job_id: card.getAttribute('data-job-id') || '',
                    });
                }
            } catch(e) {}
        });
        return results;
    }""")

    results = jobs[:max_results]
    logger.info("linkedin_jobs_found", count=len(results), keywords=keywords)
    return results


# ── Job Application ────────────────────────────────────────────────────

async def linkedin_apply_easy(
    page,
    job_url: str,
    resume_path: Optional[str] = None,
    answers: Optional[dict] = None,
    browser_session=None,
) -> dict:
    """
    Apply to a LinkedIn Easy Apply job.

    Args:
        page: Playwright page with active LinkedIn session
        job_url: Full URL of the job posting
        resume_path: Local path to resume file (PDF)
        answers: Pre-filled answers for common application questions

    Returns:
        Dict with application status and details
    """
    answers = answers or {}
    logger.info("linkedin_easy_apply", job_url=job_url)

    # Navigate to job posting
    await page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
    await _human_delay(2, 4)

    # Check for blockages
    if browser_session:
        resolved = await check_and_handle_blockage(page, browser_session, "job application")
        if not resolved:
            return {"status": "blocked", "job": {}, "message": "Blockage not resolved"}

    # Get job details before applying
    job_info = await page.evaluate("""() => {
        const title = document.querySelector('.job-details-jobs-unified-top-card__job-title, .t-24.t-bold');
        const company = document.querySelector('.job-details-jobs-unified-top-card__company-name, .t-14 a');
        return {
            title: title ? title.textContent.trim() : 'Unknown',
            company: company ? company.textContent.trim() : 'Unknown',
        };
    }""")

    # Look for Easy Apply button
    easy_apply_btn = None
    selectors = [
        'button.jobs-apply-button',
        'button[data-control-name="jobdetails_topcard_inapply"]',
        'button:has-text("Easy Apply")',
        '.jobs-apply-button--top-card',
    ]
    for sel in selectors:
        try:
            easy_apply_btn = await page.wait_for_selector(sel, timeout=3000)
            if easy_apply_btn:
                break
        except Exception:
            continue

    if not easy_apply_btn:
        return {
            "status": "not_easy_apply",
            "job": job_info,
            "message": "This job doesn't have Easy Apply. External application required.",
        }

    # Click Easy Apply
    await _human_delay(0.5, 1.5)
    await easy_apply_btn.click()
    await _human_delay(1, 3)

    # Handle the multi-step application form
    step = 0
    max_steps = 10

    while step < max_steps:
        step += 1
        await _human_delay(1, 2)

        # Check if there's a resume upload step
        if resume_path:
            file_input = await page.query_selector('input[type="file"]')
            if file_input:
                try:
                    await file_input.set_input_files(resume_path)
                    await _human_delay(1, 2)
                    logger.info("resume_uploaded", path=resume_path)
                except Exception as e:
                    logger.warning("resume_upload_failed", error=str(e))

        # Try to fill in text fields with common answers
        text_fields = await page.query_selector_all('input[type="text"]:not([readonly]), textarea')
        for field in text_fields:
            try:
                label_el = await field.evaluate_handle("""el => {
                    const label = el.closest('.fb-dash-form-element')?.querySelector('label');
                    return label;
                }""")
                label_text = await label_el.evaluate("el => el ? el.textContent.trim().toLowerCase() : ''") if label_el else ""

                # Auto-fill common fields
                value = await field.input_value()
                if not value.strip():
                    if "phone" in label_text:
                        fill_val = answers.get("phone", "")
                    elif "email" in label_text:
                        fill_val = answers.get("email", "")
                    elif "salary" in label_text or "compensation" in label_text:
                        fill_val = answers.get("salary", "")
                    elif "year" in label_text and "experience" in label_text:
                        fill_val = answers.get("years_experience", "")
                    elif "linkedin" in label_text:
                        fill_val = answers.get("linkedin_url", "")
                    elif "website" in label_text or "portfolio" in label_text:
                        fill_val = answers.get("website", "")
                    elif "city" in label_text:
                        fill_val = answers.get("city", "")
                    else:
                        fill_val = ""

                    if fill_val:
                        await field.click()
                        await _human_delay(0.3, 0.6)
                        await _human_type(page, str(fill_val))
                        await _human_delay(0.3, 0.6)
            except Exception:
                continue

        # Handle radio buttons / dropdowns
        try:
            selects = await page.query_selector_all('select')
            for sel in selects:
                options = await sel.evaluate("""el => {
                    return Array.from(el.options).map(o => ({value: o.value, text: o.text}));
                }""")
                # Select first non-empty option if nothing selected
                current = await sel.input_value()
                if not current and len(options) > 1:
                    await sel.select_option(options[1]["value"])
                    await _human_delay(0.3, 0.6)
        except Exception:
            pass

        # Check for "Submit application" button (final step)
        submit_btn = await page.query_selector('button[aria-label*="Submit"], button:has-text("Submit application")')
        if submit_btn:
            is_visible = await submit_btn.is_visible()
            if is_visible:
                await _human_delay(0.5, 1.5)
                await submit_btn.click()
                await _human_delay(2, 4)

                # Check for success
                try:
                    await page.wait_for_selector('.artdeco-inline-feedback--success, [data-test-modal-close-btn], .jpac-modal-header', timeout=5000)
                    logger.info("linkedin_application_submitted", job=job_info)
                    return {
                        "status": "applied",
                        "job": job_info,
                        "message": f"Successfully applied to {job_info['title']} at {job_info['company']}",
                    }
                except Exception:
                    pass

                return {
                    "status": "submitted",
                    "job": job_info,
                    "message": f"Application submitted for {job_info['title']} at {job_info['company']}",
                }

        # Look for "Next" / "Review" / "Continue" button
        next_btn = await page.query_selector(
            'button[aria-label*="next"], button[aria-label*="Review"], '
            'button[aria-label*="Continue"], button:has-text("Next"), '
            'button:has-text("Review"), button:has-text("Continue")'
        )
        if next_btn:
            is_visible = await next_btn.is_visible()
            if is_visible:
                await _human_delay(0.5, 1)
                await next_btn.click()
                continue

        # Check for "Discard" — means we might be stuck
        discard = await page.query_selector('button[data-test-dialog-primary-btn], button:has-text("Discard")')
        if discard and step > 5:
            logger.warning("linkedin_apply_stuck", step=step)
            return {
                "status": "incomplete",
                "job": job_info,
                "message": f"Application incomplete after {step} steps. May need manual completion.",
                "step": step,
            }

        # Wait and try again
        await _human_delay(1, 2)

    return {
        "status": "timeout",
        "job": job_info,
        "message": f"Application timed out after {max_steps} steps",
    }


# ── Job Detail Extraction ─────────────────────────────────────────────

async def linkedin_get_job_details(page, job_url: str) -> dict:
    """Extract full job details from a LinkedIn job posting."""

    await page.goto(job_url, wait_until="domcontentloaded", timeout=30000)
    await _human_delay(2, 3)

    # Click "Show more" if present
    try:
        show_more = await page.query_selector('button[aria-label*="Show more"], button.jobs-description__footer-button')
        if show_more:
            await show_more.click()
            await _human_delay(0.5, 1)
    except Exception:
        pass

    details = await page.evaluate("""() => {
        const title = document.querySelector('.job-details-jobs-unified-top-card__job-title, .t-24.t-bold');
        const company = document.querySelector('.job-details-jobs-unified-top-card__company-name, .t-14 a');
        const location = document.querySelector('.job-details-jobs-unified-top-card__bullet, .t-14.t-black--light');
        const desc = document.querySelector('.jobs-description__content, .jobs-box__html-content');
        const criteria = document.querySelectorAll('.description__job-criteria-item, .job-criteria__item');

        const criteriaData = {};
        criteria.forEach(item => {
            const label = item.querySelector('.job-criteria__subheader, h3');
            const value = item.querySelector('.job-criteria__text, span');
            if (label && value) {
                criteriaData[label.textContent.trim().toLowerCase()] = value.textContent.trim();
            }
        });

        return {
            title: title ? title.textContent.trim() : '',
            company: company ? company.textContent.trim() : '',
            location: location ? location.textContent.trim() : '',
            description: desc ? desc.innerText.trim().substring(0, 5000) : '',
            criteria: criteriaData,
            url: window.location.href.split('?')[0],
        };
    }""")

    return details


# ── Send Connection Request / InMail ───────────────────────────────────

async def linkedin_send_message(
    page,
    profile_url: str,
    message: str,
    connection_note: Optional[str] = None,
) -> dict:
    """
    Send a LinkedIn connection request or message.

    Args:
        page: Playwright page
        profile_url: LinkedIn profile URL of the person
        message: Message to send (InMail or connection note)
        connection_note: If provided, sends as a connection request with note

    Returns:
        Status dict
    """
    await page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
    await _human_delay(2, 4)

    name = await page.evaluate("""() => {
        const el = document.querySelector('.text-heading-xlarge, .pv-text-details__left-panel h1');
        return el ? el.textContent.trim() : 'Unknown';
    }""")

    if connection_note:
        # Send connection request
        try:
            connect_btn = await page.query_selector('button:has-text("Connect"), button[aria-label*="Connect"]')
            if connect_btn:
                await connect_btn.click()
                await _human_delay(1, 2)

                # Click "Add a note"
                add_note = await page.query_selector('button:has-text("Add a note")')
                if add_note:
                    await add_note.click()
                    await _human_delay(0.5, 1)

                    # Type the note
                    textarea = await page.query_selector('textarea[name="message"], #custom-message')
                    if textarea:
                        await textarea.click()
                        await _human_type(page, connection_note[:300])  # LinkedIn limits to 300
                        await _human_delay(0.5, 1)

                # Click Send
                send_btn = await page.query_selector('button[aria-label*="Send"], button:has-text("Send")')
                if send_btn:
                    await send_btn.click()
                    await _human_delay(1, 2)
                    return {"status": "sent", "type": "connection", "to": name}

            return {"status": "failed", "type": "connection", "to": name, "reason": "Connect button not found"}
        except Exception as e:
            return {"status": "failed", "type": "connection", "to": name, "reason": str(e)}

    else:
        # Send direct message
        try:
            msg_btn = await page.query_selector('button:has-text("Message"), button[aria-label*="Message"]')
            if msg_btn:
                await msg_btn.click()
                await _human_delay(1, 2)

                # Type in message box
                msg_box = await page.query_selector('.msg-form__contenteditable, div[contenteditable="true"]')
                if msg_box:
                    await msg_box.click()
                    await _human_type(page, message)
                    await _human_delay(0.5, 1)

                    # Send
                    send_btn = await page.query_selector('button.msg-form__send-button, button:has-text("Send")')
                    if send_btn:
                        await send_btn.click()
                        await _human_delay(1, 2)
                        return {"status": "sent", "type": "message", "to": name}

            return {"status": "failed", "type": "message", "to": name, "reason": "Message button not found"}
        except Exception as e:
            return {"status": "failed", "type": "message", "to": name, "reason": str(e)}
