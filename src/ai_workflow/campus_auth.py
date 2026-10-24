from __future__ import annotations

import argparse
from http.cookiejar import MozillaCookieJar
import json
from pathlib import Path
import re
import time
from typing import Any
import urllib.parse

import requests
from pypdf import PdfReader

DEFAULT_AUTH_DIR = Path(__file__).resolve().parents[2] / ".local_auth"
DEFAULT_STORAGE_STATE = DEFAULT_AUTH_DIR / "campus_browser_state.json"
DEFAULT_COOKIES_TXT = DEFAULT_AUTH_DIR / "cookies.txt"


def load_campus_cookies(
    storage_state_path: Path = DEFAULT_STORAGE_STATE,
    cookies_txt_path: Path = DEFAULT_COOKIES_TXT,
) -> requests.cookies.RequestsCookieJar:
    """Load saved campus/library cookies from Playwright storage_state.json or Netscape cookies.txt."""

    jar = requests.cookies.RequestsCookieJar()

    if storage_state_path.exists():
        try:
            data = json.loads(storage_state_path.read_text(encoding="utf-8"))
            for c in data.get("cookies", []):
                jar.set(
                    c["name"],
                    c["value"],
                    domain=c.get("domain", ""),
                    path=c.get("path", "/"),
                )
        except Exception:
            pass

    if cookies_txt_path.exists():
        try:
            moz_jar = MozillaCookieJar(str(cookies_txt_path))
            moz_jar.load(ignore_discard=True, ignore_expires=True)
            for cookie in moz_jar:
                jar.set(cookie.name, cookie.value, domain=cookie.domain, path=cookie.path)
        except Exception:
            pass

    return jar


def interactive_campus_login(
    portal_url: str = "https://wisdom.chaoxing.com/newwisdom/doordatabase/database.html?pageId=426497&wfwfid=22943&websiteId=231987",
    storage_state_path: Path = DEFAULT_STORAGE_STATE,
) -> Path:
    """Launch an interactive Chromium window so the user can log into XTU Library / ScienceDirect / IEEE once.

    Saves all cookies and localStorage to `.local_auth/campus_browser_state.json` (git-ignored).
    """

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is required for interactive browser login. "
            "Install it with: pip install playwright && playwright install chromium"
        ) from exc

    storage_state_path.parent.mkdir(parents=True, exist_ok=True)
    user_data_dir = storage_state_path.parent / "browser_profile"
    user_data_dir.mkdir(parents=True, exist_ok=True)
    debug_port = 9234

    print("======================================================================")
    print("[CampusAuth] Using Windows native GUI launcher to open browser window...")
    print("1. Please log in with your student account in the opened browser window.")
    print("2. Click into ScienceDirect / IEEE Xplore / CNKI to activate session cookies.")
    print("3. Return to this terminal and press [ENTER] to save!")
    print("======================================================================")

    # Prefer Edge first (since user actively uses Edge on this desktop), and launch
    # via Windows Shell (`os.startfile` / `cmd /c start`) so it ALWAYS opens on the visible desktop!
    import os
    import subprocess

    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    browser_exe = next((p for p in candidates if os.path.exists(p)), None)
    if not browser_exe:
        raise RuntimeError("Could not find Edge or Chrome executable on standard Windows paths.")

    # Kill any zombie headless chrome/msedge holding port 9234 before starting
    subprocess.run(
        f'for /f "tokens=5" %a in (\'netstat -aon ^| findstr :{debug_port}\') do taskkill /F /PID %a',
        shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    args_str = (
        f'--remote-debugging-port={debug_port} '
        f'--user-data-dir="{user_data_dir}" '
        f'--new-window --start-maximized --no-first-run --no-default-browser-check "{portal_url}"'
    )
    os.startfile(browser_exe, arguments=args_str)  # noqa: S606
    time.sleep(3.0)

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{debug_port}")
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            print(f"[CampusAuth] Connected to visible browser ({Path(browser_exe).name} on port {debug_port}).")
        except Exception as exc:
            raise RuntimeError(f"Failed to connect to launched browser on port {debug_port}: {exc}") from exc

        try:
            input("\n>>> 登录完成后（不要提前关掉浏览器），请回到此处按【回车键 Enter】自动保存凭证并退出: ")
        except EOFError:
            pass

        try:
            # Use context.cookies() instead of context.storage_state() because
            # storage_state() hangs if any tab (like mh.chaoxing.com) is still spinning!
            cookies = context.cookies()
            payload = {"cookies": cookies, "origins": []}
            storage_state_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"[CampusAuth] Immediately saved {len(cookies)} cookies to: {storage_state_path}")
        except Exception as exc:
            print(f"[CampusAuth] Could not save session: {exc}")
        finally:
            try:
                subprocess.run(
                    f'for /f "tokens=5" %a in (\'netstat -aon ^| findstr :{debug_port}\') do taskkill /F /PID %a',
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass
    return storage_state_path


def download_pdf_with_campus_auth(
    doi: str | None,
    title: str,
    target_pdf_path: Path,
    elsevier_api_key: str = "",
    storage_state_path: Path = DEFAULT_STORAGE_STATE,
    timeout_sec: int = 25,
) -> tuple[bool, str, list[str]]:
    """Attempt to download full-text PDF using campus credentials:

    Tier 1: Official Elsevier API (`X-ELS-APIKey` + Campus IP) if `ELSEVIER_API_KEY` is set or DOI is `10.1016/...`
    Tier 2: Authenticated requests session using saved `.local_auth/campus_browser_state.json` or `cookies.txt`
    Tier 3: Playwright headless browser session (bypasses Cloudflare JS challenge on ScienceDirect / IEEE)
    """

    logs: list[str] = []
    target_pdf_path.parent.mkdir(parents=True, exist_ok=True)

    # Tier 1: Elsevier Full-Text API (works immediately on campus IP with free dev.elsevier.com key)
    if doi and doi.startswith("10.1016/"):
        api_url = f"https://api.elsevier.com/content/article/doi/{doi}?httpAccept=application/pdf"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/pdf",
        }
        if elsevier_api_key:
            headers["X-ELS-APIKey"] = elsevier_api_key
        try:
            resp = requests.get(api_url, headers=headers, timeout=timeout_sec)
            if resp.status_code == 200 and resp.content.startswith(b"%PDF"):
                target_pdf_path.write_bytes(resp.content)
                text = _extract_pdf_text(target_pdf_path, logs)
                if text:
                    logs.append(f"Downloaded full PDF via Elsevier Campus API for DOI `{doi}`.")
                    return True, text, logs
        except Exception as exc:
            logs.append(f"Elsevier API PDF attempt failed: {exc}")

    # Tier 2: Saved Campus Cookies with Requests
    jar = load_campus_cookies(storage_state_path=storage_state_path)
    if len(jar) > 0 and doi:
        session = requests.Session()
        session.cookies.update(jar)
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            }
        )
        try:
            doi_url = f"https://doi.org/{doi}"
            resp = session.get(doi_url, timeout=timeout_sec, allow_redirects=True)
            if resp.content.startswith(b"%PDF"):
                target_pdf_path.write_bytes(resp.content)
                text = _extract_pdf_text(target_pdf_path, logs)
                if text:
                    logs.append(f"Downloaded PDF via saved campus cookies from `{doi_url}`.")
                    return True, text, logs
        except Exception as exc:
            logs.append(f"Cookie session download attempt failed: {exc}")

    # Tier 3: Playwright Authenticated Browser Context (if storage_state.json exists)
    if storage_state_path.exists() and doi:
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(
                    storage_state=str(storage_state_path),
                    accept_downloads=True,
                )
                page = context.new_page()
                page.goto(f"https://doi.org/{doi}", wait_until="domcontentloaded", timeout=timeout_sec * 1000)
                # Look for ScienceDirect PII and construct pdfft link
                current_url = page.url
                pii_match = re.search(r"/pii/(S[0-9X]+)", current_url)
                if pii_match:
                    pii = pii_match.group(1)
                    pdf_url = f"https://www.sciencedirect.com/science/article/pii/{pii}/pdfft?isDTMRedir=true&download=true"
                    with page.expect_download(timeout=timeout_sec * 1000) as dl_info:
                        page.goto(pdf_url)
                    download = dl_info.value
                    download.save_as(str(target_pdf_path))
                    text = _extract_pdf_text(target_pdf_path, logs)
                    if text:
                        logs.append(f"Downloaded ScienceDirect PDF via Playwright campus session (`{pii}`).")
                        browser.close()
                        return True, text, logs
                browser.close()
        except Exception as exc:
            logs.append(f"Playwright campus session download skipped/failed: {exc}")

    return False, "", logs


def discover_papers_online(
    query: str,
    max_results: int = 5,
    min_year: int = 2020,
    timeout_sec: int = 20,
) -> list[dict[str, Any]]:
    """AI Paper Scout: search arXiv & Crossref for high-impact scheduling/RL papers."""

    discovered: list[dict[str, Any]] = []
    encoded_q = urllib.parse.quote(query)
    headers = {"User-Agent": "fjsp-agv-rl-research/0.1 (mailto:research@xtu.edu.cn)"}

    # 1. Search Crossref byrelevance (covers Elsevier EJOR/CIE, IEEE, Springer, Taylor & Francis)
    cr_url = (
        f"https://api.crossref.org/works?query.bibliographic={encoded_q}"
        f"&filter=from-pub-date:{min_year}-01-01,type:journal-article"
        f"&rows={max_results}&sort=relevance"
    )
    try:
        resp = requests.get(cr_url, headers=headers, timeout=timeout_sec)
        if resp.status_code == 200:
            items = resp.json().get("message", {}).get("items", [])
            for item in items:
                titles = item.get("title") or ["Untitled"]
                title = titles[0]
                venues = item.get("container-title") or ["Journal"]
                venue = venues[0]
                issued = item.get("issued", {}).get("date-parts", [[min_year]])
                year = issued[0][0] if issued and issued[0] else min_year
                citations = item.get("is-referenced-by-count", 0)
                doi = item.get("DOI")
                discovered.append(
                    {
                        "title": title,
                        "year": year,
                        "venue": venue,
                        "citations": citations,
                        "doi": doi,
                        "arxiv_id": None,
                    }
                )
    except Exception:
        pass

    # 2. Search arXiv API (100% free full-text PDF available)
    arxiv_url = (
        f"http://export.arxiv.org/api/query?search_query=all:{encoded_q}"
        f"&start=0&max_results={max_results}"
    )
    try:
        import xml.etree.ElementTree as ET

        resp = requests.get(arxiv_url, headers=headers, timeout=timeout_sec)
        if resp.status_code == 200:
            root = ET.fromstring(resp.text)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("atom:entry", ns):
                title_el = entry.find("atom:title", ns)
                id_el = entry.find("atom:id", ns)
                pub_el = entry.find("atom:published", ns)
                if title_el is not None and id_el is not None and title_el.text and id_el.text:
                    clean_title = re.sub(r"\s+", " ", title_el.text).strip()
                    arxiv_id = id_el.text.rstrip("/").split("/")[-1]
                    year_str = pub_el.text[:4] if (pub_el is not None and pub_el.text) else str(min_year)
                    discovered.append(
                        {
                            "title": clean_title,
                            "year": int(year_str) if year_str.isdigit() else min_year,
                            "venue": "arXiv Preprint (Open PDF)",
                            "citations": 0,
                            "doi": None,
                            "arxiv_id": arxiv_id,
                        }
                    )
    except Exception:
        pass

    return discovered


def _extract_pdf_text(pdf_path: Path, logs: list[str]) -> str:
    try:
        reader = PdfReader(str(pdf_path))
        pages = [page.extract_text() or "" for page in reader.pages]
        full_text = "\n\n".join(pages).strip()
        if len(full_text) > 1000:
            logs.append(f"Extracted {len(reader.pages)} pages ({len(full_text)} chars) from `{pdf_path.name}`.")
            return full_text
    except Exception as exc:
        logs.append(f"Failed to parse downloaded PDF `{pdf_path.name}`: {exc}")
    return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Manage XTU campus database login credentials & AI paper discovery."
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Open interactive browser to log into XTU Library / ScienceDirect / IEEE and save session.",
    )
    parser.add_argument(
        "--discover",
        type=str,
        default="",
        help="Search OpenAlex for top-cited papers matching this query (e.g., 'flexible job shop AGV reinforcement learning').",
    )
    args = parser.parse_args(argv)

    if args.login:
        interactive_campus_login()
        return 0

    if args.discover:
        papers = discover_papers_online(args.discover, max_results=6)
        print(f"Found {len(papers)} high-impact papers for query: '{args.discover}'\n")
        for idx, p in enumerate(papers, 1):
            print(
                f"[{idx}] ({p['year']}) {p['title']}\n"
                f"    Venue: {p['venue']} | Citations: {p['citations']} | DOI: {p['doi']} | arXiv: {p['arxiv_id']}\n"
            )
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
