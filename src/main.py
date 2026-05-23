import argparse
import random
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse
from urllib import robotparser

import pandas as pd
import requests
from bs4 import BeautifulSoup


SEARCH_KEYWORDS = [
    "cycling sunglasses brand",
    "sports sunglasses brand",
    "running sunglasses brand",
    "baseball sunglasses brand",
    "fishing sunglasses brand",
    "water sports sunglasses brand",
    "motocross goggles brand",
    "ski goggles brand",
    "TR90 sports sunglasses",
    "TR90 cycling sunglasses",
    "photochromic cycling sunglasses",
    "polarized sports sunglasses",
]

BLOCKED_BRANDS = {
    "oakley", "100%", "poc", "smith", "nike", "adidas", "rockbros", "kapvoe"
}

BLOCKED_DOMAINS = [
    "amazon.", "walmart.", "ebay.", "aliexpress.", "temu.", "etsy.",
    "alibaba.", "made-in-china.", "globalsources.", "gearjunkie.", "reddit.",
]

LOW_VALUE_EMAILS = {"support@shopify.com"}
LOW_VALUE_PATTERNS = ["no-reply", "noreply", "donotreply"]

TARGET_PAGES = [
    "/", "/contact", "/contact-us", "/about", "/about-us",
    "/pages/contact", "/pages/contact-us", "/pages/about", "/pages/about-us",
    "/pages/wholesale", "/pages/retailers", "/pages/dealers", "/pages/stockists",
    "/pages/privacy-policy", "/pages/terms-of-service",
]

CATEGORY_KEYWORDS = {
    "cycling sunglasses": ["cycling"],
    "sports sunglasses": ["sports sunglasses", "sport sunglasses"],
    "running sunglasses": ["running"],
    "baseball sunglasses": ["baseball"],
    "fishing sunglasses": ["fishing"],
    "water sports sunglasses": ["water sports", "watersports", "surf"],
    "motocross goggles": ["motocross", "mx goggle"],
    "ski goggles": ["ski goggle", "snow goggle"],
    "sports eyewear": ["eyewear", "sunglasses", "goggle"],
}

FRAME_KEYWORDS = ["tr90", "tr-90", "tr frame", "tpu frame", "grilamid", "nylon frame"]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


@dataclass
class Lead:
    brand_name: str
    website: str
    country_or_region: str
    product_category: str
    main_products: str
    email: str
    email_type: str
    contact_page_url: str
    evidence_url: str
    frame_material: str
    dtc_fit_score_1_to_5: int
    potential_customer_score_1_to_5: int
    reason: str
    notes: str


class LeadFinder:
    def __init__(self, timeout: int = 12, max_pages: int = 15):
        self.timeout = timeout
        self.max_pages = max_pages
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": UA})
        self.seen_domains: Set[str] = set()

    def random_delay(self):
        time.sleep(random.uniform(1.0, 3.0))

    def search_duckduckgo(self, query: str, limit: int = 20) -> List[str]:
        urls = []
        try:
            self.random_delay()
            resp = self.session.get("https://duckduckgo.com/html/", params={"q": query}, timeout=self.timeout)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            for a in soup.select("a.result__a"):
                href = a.get("href", "")
                if href.startswith("http"):
                    urls.append(href)
                if len(urls) >= limit:
                    break
        except Exception:
            return []
        return urls

    def domain_of(self, url: str) -> str:
        return urlparse(url).netloc.lower().replace("www.", "")

    def blocked_or_irrelevant(self, url: str) -> bool:
        d = self.domain_of(url)
        if any(b in d for b in BLOCKED_DOMAINS):
            return True
        if any(b in d for b in ["blog", "news", "review"]):
            return True
        return False

    def appears_major_or_blocked_brand(self, text: str) -> bool:
        t = text.lower()
        return any(b in t for b in BLOCKED_BRANDS)

    def can_fetch(self, url: str) -> bool:
        parsed = urlparse(url)
        rp = robotparser.RobotFileParser()
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        try:
            rp.set_url(robots_url)
            rp.read()
            return rp.can_fetch(UA, url)
        except Exception:
            return True

    def fetch(self, url: str) -> Optional[str]:
        try:
            self.random_delay()
            r = self.session.get(url, timeout=self.timeout)
            if r.status_code in (403, 429):
                return None
            text = r.text.lower()
            if "captcha" in text or "cloudflare" in text and "attention required" in text:
                return None
            return r.text
        except Exception:
            return None

    def find_country_hint(self, soup: BeautifulSoup) -> str:
        txt = soup.get_text(" ", strip=True)[:3000]
        for token in ["usa", "united states", "canada", "uk", "australia", "germany", "france", "italy", "spain"]:
            if token in txt.lower():
                return token.upper() if len(token) <= 3 else token.title()
        return "Unknown"

    def classify_email(self, email: str) -> str:
        em = email.lower()
        if em in LOW_VALUE_EMAILS or any(p in em for p in LOW_VALUE_PATTERNS):
            return "low_value"
        if any(k in em for k in ["privacy", "legal"]):
            return "privacy"
        if any(k in em for k in ["sales", "wholesale", "b2b", "dealer"]):
            return "business"
        return "general"

    def parse_brand_name(self, soup: BeautifulSoup, domain: str) -> str:
        title = soup.title.text.strip() if soup.title else ""
        if title:
            return title.split("|")[0].split("-")[0].strip()
        return domain.split(".")[0].title()

    def detect_categories(self, text: str) -> str:
        matches = []
        lt = text.lower()
        for cat, kws in CATEGORY_KEYWORDS.items():
            if any(kw in lt for kw in kws):
                matches.append(cat)
        return ", ".join(sorted(set(matches))) if matches else "sports eyewear"

    def frame_material(self, text: str) -> str:
        lt = text.lower()
        found = [kw for kw in FRAME_KEYWORDS if kw in lt]
        return ", ".join(sorted(set(found))) if found else "unknown"

    def score(self, categories: str, frame_material: str, text: str) -> Tuple[int, int, str]:
        dtc = 3
        potential = 3
        reasons = []
        lt = text.lower()
        if "shop" in lt or "cart" in lt or "add to cart" in lt:
            dtc += 1
            reasons.append("ecommerce signals")
        if any(w in categories for w in ["cycling", "running", "sports"]):
            dtc += 1
            reasons.append("sports eyewear relevance")
        if frame_material != "unknown":
            potential += 2
            reasons.append("premium frame material mention")
        if "wholesale" in lt or "dealer" in lt:
            potential += 1
            reasons.append("B2B intent signal")
        return min(dtc, 5), min(potential, 5), "; ".join(reasons) or "basic fit"

    def extract_footer_links(self, soup: BeautifulSoup, base: str) -> List[str]:
        links = []
        footers = soup.find_all("footer")
        for f in footers:
            for a in f.find_all("a", href=True):
                links.append(urljoin(base, a["href"]))
        return links

    def crawl_site(self, website: str) -> List[Lead]:
        leads: List[Lead] = []
        domain = self.domain_of(website)
        if domain in self.seen_domains:
            return leads
        self.seen_domains.add(domain)

        if self.blocked_or_irrelevant(website):
            return leads

        home = website if website.startswith("http") else f"https://{website}"
        if not self.can_fetch(home):
            return leads

        home_html = self.fetch(home)
        if not home_html:
            return leads

        soup_home = BeautifulSoup(home_html, "lxml")
        site_text = soup_home.get_text(" ", strip=True)
        if self.appears_major_or_blocked_brand(site_text + " " + domain):
            return leads

        to_visit = [urljoin(home, p) for p in TARGET_PAGES]
        to_visit.extend(self.extract_footer_links(soup_home, home))

        visited = set()
        emails_seen = set()
        all_text = site_text

        for page_url in to_visit:
            if len(visited) >= self.max_pages:
                break
            if page_url in visited:
                continue
            visited.add(page_url)
            if not self.can_fetch(page_url):
                continue
            html = self.fetch(page_url)
            if not html:
                continue
            soup = BeautifulSoup(html, "lxml")
            page_text = soup.get_text(" ", strip=True)
            all_text += " " + page_text
            emails = set(e.lower() for e in EMAIL_RE.findall(html))
            for em in emails:
                if em in emails_seen:
                    continue
                emails_seen.add(em)
                et = self.classify_email(em)
                if et == "low_value":
                    continue
                brand = self.parse_brand_name(soup_home, domain)
                categories = self.detect_categories(all_text)
                fm = self.frame_material(all_text)
                dtc, potential, reason = self.score(categories, fm, all_text)
                notes = "privacy-only lead" if et == "privacy" else ""
                leads.append(Lead(
                    brand_name=brand,
                    website=f"https://{domain}",
                    country_or_region=self.find_country_hint(soup_home),
                    product_category=categories,
                    main_products="sports sunglasses / goggles",
                    email=em,
                    email_type=et,
                    contact_page_url=page_url,
                    evidence_url=page_url,
                    frame_material=fm,
                    dtc_fit_score_1_to_5=dtc,
                    potential_customer_score_1_to_5=potential,
                    reason=reason,
                    notes=notes,
                ))

        return leads


def normalize_site(u: str) -> Optional[str]:
    u = u.strip()
    if not u or u.startswith("#"):
        return None
    if not u.startswith("http"):
        u = "https://" + u
    parsed = urlparse(u)
    if not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def load_seed_urls(seed_file: Path) -> List[str]:
    if not seed_file.exists():
        return []
    out = []
    for line in seed_file.read_text(encoding="utf-8").splitlines():
        u = normalize_site(line)
        if u:
            out.append(u)
    return sorted(set(out))


def save_outputs(leads: List[Lead], out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for l in leads:
        d = asdict(l)
        rows.append({
            "Brand Name": d["brand_name"],
            "Website": d["website"],
            "Country or Region": d["country_or_region"],
            "Product Category": d["product_category"],
            "Main Products": d["main_products"],
            "Email": d["email"],
            "Email Type": d["email_type"],
            "Contact Page URL": d["contact_page_url"],
            "Evidence URL": d["evidence_url"],
            "Frame Material": d["frame_material"],
            "DTC Fit Score 1 to 5": d["dtc_fit_score_1_to_5"],
            "Potential Customer Score 1 to 5": d["potential_customer_score_1_to_5"],
            "Reason": d["reason"],
            "Notes": d["notes"],
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.drop_duplicates(subset=["Website", "Email"])
    csv_path = out_dir / "dtc_sports_eyewear_leads.csv"
    xlsx_path = out_dir / "dtc_sports_eyewear_leads.xlsx"
    df.to_csv(csv_path, index=False)
    df.to_excel(xlsx_path, index=False)
    return csv_path, xlsx_path, len(df)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-file", default="data/seed_urls.txt")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--max-sites", type=int, default=120)
    parser.add_argument("--max-pages", type=int, default=15)
    args = parser.parse_args()

    finder = LeadFinder(max_pages=args.max_pages)

    candidates = []
    for kw in SEARCH_KEYWORDS:
        candidates.extend(finder.search_duckduckgo(kw, limit=20))

    seeds = load_seed_urls(Path(args.seed_file))
    candidates.extend(seeds)

    norm = []
    for c in candidates:
        n = normalize_site(c)
        if n:
            norm.append(n)
    websites = list(dict.fromkeys(norm))[: args.max_sites]

    all_leads: List[Lead] = []
    for site in websites:
        all_leads.extend(finder.crawl_site(site))

    csv_path, xlsx_path, count = save_outputs(all_leads, Path(args.output_dir))
    print(f"Saved {count} leads to {csv_path} and {xlsx_path}")
    if count < 50:
        print("Collected fewer than 50 leads. Add more domains to data/seed_urls.txt and rerun.")


if __name__ == "__main__":
    main()
