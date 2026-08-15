import json
import os
import sys
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
import requests
from dotenv import load_dotenv, find_dotenv

# =======================================================
# 🔐 ENV & DISCORD CONFIGURATION WITH ERROR HANDLING
# =======================================================

# 1. Locate and load .env explicitly
dotenv_file = find_dotenv()
if dotenv_file:
    load_dotenv(dotenv_file)
    print(f"✅ Loaded environment variables from: {dotenv_file}")
else:
    print("⚠️  Warning: No '.env' file found in the working directory.")

# 2. Validate Discord Webhook URL
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

if not DISCORD_WEBHOOK_URL or not DISCORD_WEBHOOK_URL.startswith("https://discord.com/api/webhooks/"):
    print("\n❌ CRITICAL CONFIGURATION ERROR:")
    print("   DISCORD_WEBHOOK_URL is missing or invalid in your .env file!")
    print("   Please create/edit '.env' and add:")
    print("   DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_ACTUAL_WEBHOOK_URL\n")
else:
    print("✅ Discord Webhook URL recognized.\n")

SEEN_JOBS_FILE = "seen_jobs.json"

# =======================================================
# 🎯 KEYWORDS CONFIGURATION
# =======================================================

TECH_KEYWORDS = [
    "web", "developer", "react", "node", "php", "mpesa", 
    "frontend", "fullstack", "wordpress", "python", "javascript", 
    "laravel", "vue", "django", "css", "html"
]

FREELANCE_KEYWORDS = [
    "freelance", "contract", "gig", "part-time", "project", 
    "short-term", "hourly", "consultant", "remote gig", "task", "urgent", "[hiring]"
]

# =======================================================
# 🌐 TARGET SITES (With old.reddit & Fallback Selectors)
# =======================================================
TARGET_SITES = [
{
        "name": "Careerjet Kenya (Freelance Web Dev)",
        "url": "https://www.careerjet.co.ke/freelance-web-developer-jobs",
        "card": ".job, article.job, div.job_search_item, .jobs",
        "title": "a.title, header h2 a, h2 a",
        "link": "a.title, header h2 a, h2 a",
        "is_freelance_board": True
    },






    {
        "name": "Reddit r/forhire ([Hiring] Gigs)",
        # Using old.reddit.com to avoid Javascript dynamic component rendering issues
        "url": "https://old.reddit.com/r/forhire/new/",
        "card": "#siteTable .thing",
        "title": "a.title",
        "link": "a.title",
        "is_freelance_board": True
    },
    {
        "name": "MyJobMag Kenya (Software Dev)",
        "url": "https://www.myjobmag.co.ke/jobs-by-title/software-developer",
        "card": "li.job-info",
        "title": "h2 a",
        "link": "h2 a",
        "is_freelance_board": False
    },
    {
        "name": "RemoteOK (Remote Dev Jobs)",
        "url": "https://remoteok.com/remote-dev-jobs",
        "card": "tr.job",
        "title": "td.company h2, td.company a",
        "link": "a.preventLink, td.company a",
        "is_freelance_board": False
    }
]

# =======================================================

def load_seen_jobs():
    """Reads previously notified job IDs from local JSON storage."""
    if os.path.exists(SEEN_JOBS_FILE):
        try:
            with open(SEEN_JOBS_FILE, "r") as f:
                return set(json.load(f))
        except Exception as e:
            print(f"⚠️ Warning: Failed to read {SEEN_JOBS_FILE} ({e}). Starting clean.")
            return set()
    return set()

def save_seen_jobs(seen_jobs):
    """Saves updated set of notified job IDs back to file."""
    try:
        with open(SEEN_JOBS_FILE, "w") as f:
            json.dump(list(seen_jobs), f, indent=2)
    except Exception as e:
        print(f"❌ Error saving state to {SEEN_JOBS_FILE}: {e}")

def send_discord_alert(title, link, source_name, is_freelance):
    """Sends a formatted embed notification to your Discord channel."""
    if not DISCORD_WEBHOOK_URL:
        print(f"  ❌ Failed to send alert for '{title}': DISCORD_WEBHOOK_URL missing.")
        return False

    embed_color = 3066993 if is_freelance else 5814783  # Green for freelance, Purple for full-time
    tag = "⚡ FREELANCE GIG" if is_freelance else "💼 CODING JOB"

    payload = {
        "username": "Job & Freelance Hunter",
        "avatar_url": "https://cdn-icons-png.flaticon.com/512/3858/3858691.png",
        "embeds": [
            {
                "title": f"[{tag}] {title[:200]}", # Truncate long titles
                "url": link,
                "color": embed_color,
                "fields": [
                    {"name": "Source Board", "value": source_name, "inline": True},
                    {"name": "Type", "value": "Freelance / Contract" if is_freelance else "Full-Time / General", "inline": True},
                    {"name": "Direct Link", "value": f"[Click Here to View & Apply]({link})", "inline": False}
                ],
                "footer": {"text": "Automated Multi-Site Playwright Scraper"}
            }
        ]
    }

    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        if response.status_code in [200, 204]:
            print(f"  ✅ Discord alert sent: [{tag}] {title[:60]}...")
            return True
        else:
            print(f"  ❌ Failed to send Discord alert ({response.status_code}): {response.text}")
            return False
    except Exception as e:
        print(f"  ❌ Network error sending Discord alert: {e}")
        return False

def run_scraper():
    seen_jobs = load_seen_jobs()
    print(f"Loaded {len(seen_jobs)} previously processed job IDs.\n")

    total_new_matches = 0

    with sync_playwright() as p:
        print("Launching headless Chromium browser...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        for site in TARGET_SITES:
            site_name = site["name"]
            site_url = site["url"]
            is_freelance_board = site.get("is_freelance_board", False)
            print(f"\n🔍 [Scraping Site]: {site_name}")

            try:
                page.goto(site_url, wait_until="domcontentloaded", timeout=30000)

                # Wait for target card element or fallback choices
                try:
                    page.wait_for_selector(site["card"], timeout=10000)
                except Exception:
                    print(f"  ⚠️ Timeout waiting for selector '{site['card']}' on {site_name}. Skipping...")
                    continue

                job_cards = page.query_selector_all(site["card"])
                print(f"  Found {len(job_cards)} entries.")

                site_matches = 0

                for card in job_cards:
                    title_el = card.query_selector(site["title"])
                    link_el = card.query_selector(site["link"])

                    if not title_el or not link_el:
                        continue

                    title = title_el.inner_text().strip()
                    raw_link = link_el.get_attribute("href") or ""

                    if not title or not raw_link:
                        continue

                    # Handle relative URLs (/job/123 -> https://domain.com/job/123)
                    if raw_link.startswith("/"):
                        parsed = urlparse(site_url)
                        link = f"{parsed.scheme}://{parsed.netloc}{raw_link}"
                    else:
                        link = raw_link

                    job_id = link

                    if job_id in seen_jobs:
                        continue

                    title_lower = title.lower()

                    matches_tech = any(kw.lower() in title_lower for kw in TECH_KEYWORDS)
                    has_freelance_term = any(kw.lower() in title_lower for kw in FREELANCE_KEYWORDS)
                    is_freelance = is_freelance_board or has_freelance_term

                    if matches_tech:
                        # Attempt sending alert before adding to seen_jobs
                        alert_sent = send_discord_alert(title, link, site_name, is_freelance)
                        if alert_sent:
                            seen_jobs.add(job_id)
                            site_matches += 1
                            total_new_matches += 1

                print(f"  Completed {site_name}: {site_matches} new alert(s) sent.")

            except Exception as e:
                print(f"  ❌ Error scraping {site_name}: {e}")
                continue

        browser.close()

    save_seen_jobs(seen_jobs)
    print(f"\n🎉 Scraping complete across all sources. Total new matches: {total_new_matches}")

if __name__ == "__main__":
    run_scraper()