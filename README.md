# DTC Sports Eyewear Lead Finder

Python project to discover and crawl official DTC sports eyewear brand websites and extract **public contact emails**.

## Features
- Discovers candidate websites via DuckDuckGo keyword search.
- Supports manual fallback seeds via `data/seed_urls.txt` when search scraping is blocked.
- Filters obvious marketplaces, blogs/news/review domains, and blocked major brands.
- Crawls public pages only with robots checks and CAPTCHA/anti-bot detection.
- Uses polite crawling:
  - Normal User-Agent
  - Random 1-3 second delay between requests
  - Max 15 pages per website
  - Timeout + continue on errors
- Extracts and deduplicates public emails.
- Exports:
  - Full leads CSV (always)
  - Full leads XLSX (when `openpyxl` is available)
  - Email-only CSV/TXT (always)
- Scores each lead and exports both CSV and Excel:
  - `output/dtc_sports_eyewear_leads.csv`
  - `output/dtc_sports_eyewear_leads.xlsx`
  - `output/emails_only.csv`
  - `output/emails_only.txt`

## Install
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage
```bash
python src/main.py
```

Optional args:
```bash
python src/main.py --seed-file data/seed_urls.txt --output-dir output --max-sites 120 --max-pages 15
```

## Seed URL workflow (fallback)
If search-engine scraping is blocked or returns weak results:
1. Open `data/seed_urls.txt`
2. Add official brand homepages (one per line)
3. Run `python src/main.py`

The crawler will automatically process those websites and extract public emails.

## Notes
- The script only accesses public pages and does not bypass login/CAPTCHA/protected pages.
- It skips disallowed robots pages when detectable.
- Privacy/legal emails are kept but labeled as lower value (`email_type=privacy`).
- If XLSX dependencies are unavailable, CSV/TXT outputs are still generated and usable.

## ICP tuning for your factory
- Target customers: small/medium DTC brands and China sports-eyewear distributors.
- Exclude large brands even if relevant category matches.
- Practical volume heuristic: prioritize leads likely in **5-300 orders/day** range.
- Recommended workflow:
  1. Keep `data/seed_urls.txt` curated manually for SMB targets only.
  2. Run crawler to get public emails.
  3. Manually remove any site that appears enterprise-scale before outreach.


## Seed v3 strict filter (recommended)
For your factory ICP (B2B, China supplier, target 5-300 orders/day), use this priority process:
1. Start from Tier A in `data/seed_urls.txt` first.
2. Run crawler and keep leads with:
   - `Email Type` = `business` or `general`
   - `DTC Fit Score` >= 4
   - `Potential Customer Score` >= 4
3. Review company size signals manually (catalog width, team size, global retail footprint).
4. Use Tier B and Tier C only after Tier A is exhausted.

This reduces outreach noise from brands that are too large for OEM/ODM conversion.
