from __future__ import annotations

import dataclasses
import html
import logging
import re
import time
from typing import Iterable, List, Sequence
from urllib.parse import urlsplit, urlunsplit

import requests

LOGGER = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}

COMMITTEE_URLS: Sequence[str] = (
    "https://cst.na.go.kr:444/cmmit/mem/cmmitMemList/subCmt.do?menuNo=2000014",
    "https://steering.na.go.kr:444/cmmit/mem/cmmitMemList/subCmt.do?menuNo=2000014",
    "https://legislation.na.go.kr:444/cmmit/mem/cmmitMemList/subCmt.do?menuNo=2000014",
    "https://policy.na.go.kr:444/cmmit/mem/cmmitMemList/subCmt.do?menuNo=2000014",
    "https://finance.na.go.kr/cmmit/mem/cmmitMemList/subCmt.do?menuNo=2000014",
    "https://edu.na.go.kr:444/cmmit/mem/cmmitMemList/subCmt.do?menuNo=2000014",
    "https://science.na.go.kr:444/cmmit/mem/cmmitMemList/subCmt.do?menuNo=2000014",
    "https://uft.na.go.kr:444/cmmit/mem/cmmitMemList/subCmt.do?menuNo=2000014",
    "https://defense.na.go.kr:444/cmmit/mem/cmmitMemList/subCmt.do?menuNo=2000014",
    "https://adminhom.na.go.kr:444/cmmit/mem/cmmitMemList/subCmt.do?menuNo=2000014",
    "https://agri.na.go.kr:444/cmmit/mem/cmmitMemList/subCmt.do?menuNo=2000014",
    "https://industry.na.go.kr/cmmit/mem/cmmitMemList/subCmt.do?menuNo=2000014",
    "https://health.na.go.kr/cmmit/mem/cmmitMemList/subCmt.do?menuNo=2000014",
    "https://environment.na.go.kr:444/cmmit/mem/cmmitMemList/subCmt.do?menuNo=2000014",
    "https://ltc.na.go.kr:444/cmmit/mem/cmmitMemList/subCmt.do?menuNo=2000014",
    "https://intelligence.na.go.kr:444/cmmit/mem/cmmitMemList/subCmt.do?menuNo=2000014",
    "https://women.na.go.kr:444/cmmit/mem/cmmitMemList/subCmt.do?menuNo=2000014",
    "https://budget.na.go.kr:444/cmmit/mem/cmmitMemList/subCmt.do?menuNo=2000014",
)


@dataclasses.dataclass(frozen=True)
class BudgetSubcommitteeMember:
    committee_url: str
    subcommittee_name: str
    party: str
    name: str


def fetch_budget_subcommittee_members(
    session: requests.Session | None = None,
    *,
    urls: Sequence[str] = COMMITTEE_URLS,
    sleep_seconds: float = 0.4,
) -> List[BudgetSubcommitteeMember]:
    """Collect the membership list for every budget sub-committee.

    The National Assembly websites occasionally return EUC-KR encoded
    responses or require a warm-up request to issue cookies.  This helper
    mimics the Google Apps Script implementation that the user relied on by
    issuing a warm-up request, attempting both port 444 and the default port,
    and falling back to EUC-KR decoding if the UTF-8 version looks garbled.
    """

    if session is None:
        session = requests.Session()

    rows: List[BudgetSubcommitteeMember] = []
    for url in urls:
        if not url:
            continue
        LOGGER.info("Processing %s", url)
        html_text = fetch_html_robust(url, session=session)
        if not html_text:
            LOGGER.warning("No HTML retrieved from %s", url)
            continue

        subcommittees = [name for name in extract_subcommittees(html_text) if "예산" in name]
        if not subcommittees:
            LOGGER.info("No budget sub-committees detected for %s", url)
            continue

        members = extract_members(html_text)
        for subcommittee in subcommittees:
            for member in members:
                rows.append(
                    BudgetSubcommitteeMember(
                        committee_url=url,
                        subcommittee_name=subcommittee,
                        party=member.party,
                        name=member.name,
                    )
                )
        time.sleep(sleep_seconds)
    return rows


@dataclasses.dataclass(frozen=True)
class Member:
    party: str
    name: str


_MEMBER_PARTIES = ("더불어민주당", "국민의힘", "비교섭단체")


def fetch_html_robust(url: str, *, session: requests.Session) -> str | None:
    base = get_base_url(url)
    warmup_targets = [base + "/"]

    for target in warmup_targets:
        try:
            session.get(target, headers=DEFAULT_HEADERS, allow_redirects=False, timeout=10)
        except requests.RequestException as exc:  # pragma: no cover - network issues
            LOGGER.debug("Warm-up failed for %s: %s", target, exc)

    variants = [url, remove_port_444(url)]
    for variant in variants:
        if not variant:
            continue
        try:
            response = session.get(
                variant,
                headers={**DEFAULT_HEADERS, "Referer": base + "/"},
                allow_redirects=True,
                timeout=20,
            )
        except requests.RequestException as exc:  # pragma: no cover - network issues
            LOGGER.warning("Fetching %s failed: %s", variant, exc)
            continue

        html_text = decode_html(response)
        if response.ok:
            return html_text
        LOGGER.warning("Fetching %s returned status %s", variant, response.status_code)
    return None


def decode_html(response: requests.Response) -> str:
    binary = response.content
    try:
        html_text = binary.decode("utf-8")
    except UnicodeDecodeError:
        return binary.decode("euc-kr", errors="replace")

    charset_match = re.search(r"charset\s*=\s*([A-Za-z0-9\-_]+)", html_text, re.IGNORECASE)
    charset = charset_match.group(1).upper() if charset_match else ""
    if "EUC" in charset or "CP949" in charset or looks_broken_korean(html_text):
        return binary.decode("euc-kr", errors="replace")
    return html_text


def get_base_url(url: str) -> str:
    parsed = urlsplit(url)
    netloc = parsed.netloc
    if not parsed.port and ":" not in netloc and parsed.scheme == "https":
        netloc = parsed.hostname or ""
    return urlunsplit((parsed.scheme, netloc, "", "", ""))


def remove_port_444(url: str) -> str:
    if not url:
        return url
    return url.replace(":444", "", 1)


def looks_broken_korean(text: str) -> bool:
    sample = text[:2000]
    hangul = len(re.findall(r"[\uAC00-\uD7A3]", sample))
    weird = len(re.findall(r"[�□\?]{2,}", sample))
    return (len(sample) > 0 and hangul / len(sample) < 0.02) and weird > 0


def extract_subcommittees(html_text: str) -> List[str]:
    table_match = re.search(r"<table[^>]*id=\"subNmTb\"[^>]*>(.*?)</table>", html_text, re.IGNORECASE | re.DOTALL)
    if not table_match:
        return []
    table_body = table_match.group(1)
    cells = [strip_tags(cell) for cell in re.findall(r"<td[^>]*>(.*?)</td>", table_body, re.IGNORECASE | re.DOTALL)]
    return [" ".join(cell.split()).strip() for cell in cells if cell and cell.strip()]


def extract_members(html_text: str) -> List[Member]:
    table_match = re.search(r"<table[^>]*id=\"polyCnTb\"[^>]*>(.*?)</table>", html_text, re.IGNORECASE | re.DOTALL)
    if not table_match:
        return []

    cells = [strip_tags(cell).strip() for cell in re.findall(r"<td[^>]*>(.*?)</td>", table_match.group(1), re.IGNORECASE | re.DOTALL)]
    members: List[Member] = []
    for party, cell in zip(_MEMBER_PARTIES, cells):
        normalized = cell.replace("\r\n", "\n")
        for name in (chunk.strip() for chunk in normalized.split("\n")):
            if name:
                members.append(Member(party=party, name=name))
    return members


def strip_tags(fragment: str) -> str:
    no_tags = re.sub(r"<[^>]*>", "", fragment)
    return html.unescape(no_tags)


def render_html_table(rows: Iterable[BudgetSubcommitteeMember]) -> str:
    header = """<thead><tr><th>위원회 URL</th><th>소위원회명</th><th>정당</th><th>성명</th></tr></thead>"""
    body_rows = []
    for row in rows:
        body_rows.append(
            "<tr>"
            f"<td><a href='{html.escape(row.committee_url)}' target='_blank' rel='noopener'>"
            f"{html.escape(row.committee_url)}</a></td>"
            f"<td>{html.escape(row.subcommittee_name)}</td>"
            f"<td>{html.escape(row.party)}</td>"
            f"<td>{html.escape(row.name)}</td>"
            "</tr>"
        )
    body = "<tbody>" + "".join(body_rows) + "</tbody>"
    return "<table>" + header + body + "</table>"


__all__ = [
    "BudgetSubcommitteeMember",
    "COMMITTEE_URLS",
    "DEFAULT_HEADERS",
    "fetch_budget_subcommittee_members",
    "render_html_table",
]
