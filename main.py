#!/usr/bin/env python3
"""
Scrape DjangoCon US 2025 schedule and export to ICS.

Usage:
  python main.py [--url https://2025.djangocon.us/schedule/] [--out djangocon-2025.ics]
"""

import argparse
import re
import uuid
from datetime import datetime, timezone, date
from typing import Any

import requests
from bs4 import BeautifulSoup, Tag
from dateutil import tz, parser as dateparser

DEFAULT_URL = "https://2025.djangocon.us/schedule/"
TZ_LOCAL = tz.gettz("America/Chicago")  # conference timezone
CONFERENCE_YEAR = 2025
LINE_FOLD_LIMIT = 75

DAY_H2_RE = re.compile(
    r"^\s*(Talks: .*?|Sprints: .*?)\s*/\s*(.+)$"
)  # captures label and "Monday, Sep 8"


def main() -> None:
    """CLI entry point for DjangoCon calendar scraper."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--out", default="djangocon-2025.ics")
    args = ap.parse_args()

    try:
        events = scrape_schedule(args.url)
        generate_ics(events, args.out)
        print(f"Wrote {len(events)} events to {args.out}")
    except Exception as e:
        print(f"Error: {e}")
        return 1
    return 0


def scrape_schedule(url: str) -> list[dict[str, Any]]:
    """Fetch and parse DjangoCon schedule HTML into structured events."""
    try:
        html = requests.get(url, timeout=30).text
    except requests.RequestException as e:
        raise Exception(f"Failed to fetch schedule from {url}: {e}")
    
    soup = BeautifulSoup(html, "html.parser")
    events = []

    # Process each day section
    for h2 in soup.find_all("h2"):
        day_events = parse_day_events(h2)
        events.extend(day_events)
    
    return events


def parse_day_events(h2: Tag) -> list[dict[str, Any]]:
    """Extract all events from a day's schedule section."""
    events = []
    
    # Skip non-day headers
    day_link = h2.find("a")
    if not day_link:
        return events

    day_text = clean_text(day_link.get_text(" "))
    if not day_text or "Schedule" in day_text:
        return events

    # Extract day type and date from header text
    day_label, day_date = parse_day_date(day_text)
    if not day_date:
        return events

    # Locate the day's event container
    day_container = h2.find_parent("div", class_="relative")
    if not day_container:
        print(f"Warning: Could not find day container for {day_text}")
        return events

    # Process each time slot in the day
    for time_block in day_container.find_all(
        "div", class_="flex flex-wrap gap-4 lg:gap-8"
    ):
        time_events = parse_time_block_events(time_block)
        events.extend(time_events)
    
    return events


def parse_time_block_events(time_block: Tag) -> list[dict[str, Any]]:
    """Extract events from a specific time slot."""
    events = []
    
    # Get start/end times from h3 element
    h3 = time_block.find("h3")
    if not h3:
        return events

    time_elements = h3.find_all("time")
    if len(time_elements) != 2:
        return events

    start_time_str = time_elements[0].get("datetime")
    end_time_str = time_elements[1].get("datetime")

    if not start_time_str or not end_time_str:
        return events

    # Convert ISO datetime strings to datetime objects
    try:
        start_dt = dateparser.parse(start_time_str)
        end_dt = dateparser.parse(end_time_str)
    except (ValueError, TypeError) as e:
        print(f"Warning: Failed to parse datetime '{start_time_str}' or '{end_time_str}': {e}")
        return events

    # Process each event in this time slot
    event_sections = time_block.find_all("section")
    for section in event_sections:
        event = parse_section_event(section, start_dt, end_dt)
        if event:
            events.append(event)
    
    return events


def parse_section_event(section: Tag, start_dt: datetime, end_dt: datetime) -> dict[str, Any] | None:
    """Extract event details from a schedule section."""
    # Get room information
    room_p = section.find("p", class_="text-sm")
    room = clean_text(room_p.get_text(" ")) if room_p else ""

    # Get event title
    h4 = section.find("h4")
    if not h4:
        return None

    title_link = h4.find("a")
    if title_link:
        title = clean_text(title_link.get_text(" "))
    else:
        title = clean_text(h4.get_text(" "))

    if not title:
        return None

    # Get presenter names
    presenter_section = section.find("div", class_="pt-6 mt-auto")
    presenters = []
    if presenter_section:
        presenter_names = presenter_section.find_all("h6")
        presenters = [
            clean_text(name.get_text(" ")) for name in presenter_names
        ]

    # Get audience level (skip "All" as it's redundant)
    audience_span = section.find(
        "span",
        class_="px-2 py-[.125rem] text-sm font-bold text-white bg-black rounded",
    )
    audience_level = ""
    if audience_span:
        audience_text = clean_text(audience_span.get_text(" "))
        if audience_text and audience_text != "All":
            audience_level = f"Audience level: {audience_text}"

    # Combine metadata into description
    desc_parts = []
    if presenters:
        desc_parts.append("Presented by: " + ", ".join(presenters))
    if audience_level:
        desc_parts.append(audience_level)
    if room:
        desc_parts.append(f"Location: {room}")

    description = "\n".join(desc_parts) if desc_parts else ""

    return {
        "title": title,
        "start": start_dt,
        "end": end_dt,
        "room": room,
        "description": description,
    }


def generate_ics(events: list[dict[str, Any]], output_file: str) -> None:
    """Create iCalendar file from parsed events."""
    # Create ICS with UTC times for portability
    lines = [
        "BEGIN:VCALENDAR",
        "PRODID:-//Custom//DjangoCon US 2025 Export//EN",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    for ev in events:
        uid = f"{uuid.uuid4()}@djangocon-2025"
        summary = ics_escape(ev["title"])
        dtstart = to_utc_z(ev["start"])
        dtend = to_utc_z(ev["end"])
        description = (
            ics_escape(ev.get("description", "")) if ev.get("description") else ""
        )
        location = ics_escape(ev["room"]) if ev.get("room") else ""
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{dtstamp}",
                f"DTSTART:{dtstart}",
                f"DTEND:{dtend}",
                fold_line(f"SUMMARY:{summary}"),
            ]
        )
        if location:
            lines.append(fold_line(f"LOCATION:{location}"))
        if description:
            lines.append(fold_line(f"DESCRIPTION:{description}"))
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\r\n".join(lines))


def clean_text(s: str | None) -> str:
    """Normalize whitespace in extracted text."""
    return re.sub(r"\s+", " ", s or "").strip()


def parse_day_date(label_text: str) -> tuple[str | None, date | None]:
    """Extract day type and date from schedule header.
    
    Args:
        label_text: Header text like "Talks: Day 1 / Monday, Sep 8"
    
    Returns:
        (day_label, date) or (None, None) if parsing fails
    """
    m = DAY_H2_RE.match(label_text)
    if not m:
        return None, None
    day_text = m.group(2)  # "Monday, Sep 8"
    # Add year since schedule only shows month/day
    try:
        dt = dateparser.parse(f"{day_text}, {CONFERENCE_YEAR}", fuzzy=True).date()
        return m.group(1).strip(), dt
    except (ValueError, TypeError) as e:
        print(f"Warning: Failed to parse date '{day_text}': {e}")
        return None, None


def to_utc_z(dt_local: datetime) -> str:
    """Format datetime as UTC for iCalendar."""
    return dt_local.astimezone(tz.UTC).strftime("%Y%m%dT%H%M%SZ")


def ics_escape(text: str) -> str:
    """Escape special characters for iCalendar."""
    return (
        text.replace("\\", "\\\\")
        .replace(",", "\\,")
        .replace(";", "\\;")
        .replace("\n", "\\n")
    )


def fold_line(s: str, limit: int = LINE_FOLD_LIMIT) -> str:
    """Fold long lines per iCalendar spec."""
    out = []
    while len(s.encode("utf-8")) > limit:
        cut = limit
        while cut > 0 and (len(s[:cut].encode("utf-8")) > limit):
            cut -= 1
        out.append(s[:cut])
        s = " " + s[cut:]
    out.append(s)
    return "\r\n".join(out)


if __name__ == "__main__":
    main()
