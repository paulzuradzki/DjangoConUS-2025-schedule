#!/usr/bin/env python3
"""
Tests for DjangoCon schedule scraper.
"""

from datetime import date, datetime
from unittest.mock import patch

import pytest
import requests
from bs4 import BeautifulSoup
from dateutil import tz

# Import the functions we want to test
from main import (
    clean_text,
    fold_line,
    ics_escape,
    parse_day_date,
    to_utc_z,
    scrape_schedule,
    generate_ics,
    main,
    parse_day_events,
    parse_time_block_events,
    parse_section_event,
    fetch_talk_description,
)


class TestCleanText:
    """Test the clean_text function."""
    
    @pytest.mark.parametrize("input_text,expected", [
        ("  hello   world  ", "hello world"),
        ("line1\nline2\tline3", "line1 line2 line3"),
        (None, ""),
        ("", ""),
    ])
    def test_clean_text(self, input_text, expected):
        """Test text cleaning with various inputs."""
        # Act
        result = clean_text(input_text)
        
        # Assert
        assert result == expected


class TestParseDayDate:
    """Test the parse_day_date function."""
    
    @pytest.mark.parametrize("input_text,expected_label,expected_date", [
        ("Talks: Day 1 / Monday, Sep 8", "Talks: Day 1", date(2025, 9, 8)),
        ("Sprints: Day 2 / Tuesday, Sep 9", "Sprints: Day 2", date(2025, 9, 9)),
        ("Invalid format", None, None),
    ])
    def test_parse_day_date(self, input_text, expected_label, expected_date):
        """Test parsing day labels with various formats."""
        # Act
        label, day_date = parse_day_date(input_text)
        
        # Assert
        assert label == expected_label
        assert day_date == expected_date


class TestToUtcZ:
    """Test the to_utc_z function."""
    
    def test_to_utc_z_conversion(self):
        """Test timezone conversion to UTC Z format."""
        # Arrange
        chicago_tz = tz.gettz("America/Chicago")
        local_dt = datetime(2025, 9, 8, 14, 30, tzinfo=chicago_tz)
        
        # Act
        utc_z = to_utc_z(local_dt)
        
        # Assert
        assert utc_z.endswith('Z')
        assert len(utc_z) == 16  # YYYYMMDDTHHMMSSZ format


class TestIcsEscape:
    """Test the ics_escape function."""
    
    @pytest.mark.parametrize("input_text,expected", [
        ("hello, world", "hello\\, world"),
        ("test; semicolon", "test\\; semicolon"),
        ("back\\slash", "back\\\\slash"),
        ("line1\nline2", "line1\\nline2"),
    ])
    def test_ics_escape(self, input_text, expected):
        """Test ICS text escaping with various inputs."""
        # Act
        result = ics_escape(input_text)
        
        # Assert
        assert result == expected


class TestFoldLine:
    """Test the fold_line function."""
    
    @pytest.mark.parametrize("input_line,expected_single_line,expected_multiple_lines", [
        ("This is a short line", True, False),
        ("This is a very long line that should be folded because it exceeds the 75 character limit", False, True),
    ])
    def test_fold_line(self, input_line, expected_single_line, expected_multiple_lines):
        """Test line folding with various line lengths."""
        # Act
        folded = fold_line(input_line)
        
        # Assert
        if expected_single_line:
            assert folded == input_line
        elif expected_multiple_lines:
            lines = folded.split('\r\n')
            assert len(lines) > 1
            # Each line should be <= 75 characters (except the continuation space)
            for line in lines[1:]:  # Skip first line, check continuation lines
                assert len(line) <= 76  # 75 + 1 for continuation space


class TestHtmlParsing:
    """Test HTML parsing functionality."""
    
    def test_parse_simple_schedule(self):
        """Test parsing a simple schedule HTML with the new structure."""
        # Arrange
        html = """
        <html>
        <body>
            <div class="relative">
                <h2>
                    <a href="#Day-1">
                        <span class="font-medium">Talks: Day 1</span> /
                        <time datetime="2025-09-08">Monday, Sep 8</time>
                    </a>
                </h2>
                <div class="flex flex-wrap gap-4 lg:gap-8">
                    <div class="w-full md:w-48">
                        <h3>
                            <time datetime="2025-09-08T09:00:00-05:00">9:00 am</time> to
                            <time datetime="2025-09-08T10:00:00-05:00">10:00 am</time>
                        </h3>
                    </div>
                    <ul>
                        <li>
                            <section>
                                <header>
                                    <div>
                                        <p class="text-sm">Main Ballroom</p>
                                    </div>
                                </header>
                                <h4>
                                    <a href="/talks/opening-keynote/">Opening Keynote</a>
                                </h4>
                                <div class="pt-6 mt-auto">
                                    <ul>
                                        <li>
                                            <h6>John Doe</h6>
                                        </li>
                                    </ul>
                                </div>
                            </section>
                        </li>
                    </ul>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Act
        soup = BeautifulSoup(html, "html.parser")
        h2 = soup.find("h2")
        day_link = h2.find("a")
        day_text = clean_text(day_link.get_text(" "))
        day_label, day_date = parse_day_date(day_text)
        time_elements = soup.find_all("time")
        start_time_str = time_elements[1].get("datetime")
        end_time_str = time_elements[2].get("datetime")
        
        # Assert
        assert h2 is not None
        assert day_link is not None
        assert day_label == "Talks: Day 1"
        assert day_date == date(2025, 9, 8)
        assert len(time_elements) == 3  # One for date, two for time range
        assert start_time_str == "2025-09-08T09:00:00-05:00"
        assert end_time_str == "2025-09-08T10:00:00-05:00"


class TestIcsGeneration:
    """Test ICS file generation."""
    
    def test_ics_basic_structure(self):
        """Test basic ICS structure generation."""
        # Arrange
        events = [
            {
                "title": "Test Event",
                "start": datetime(2025, 9, 8, 9, 0, tzinfo=tz.gettz("America/Chicago")),
                "end": datetime(2025, 9, 8, 10, 0, tzinfo=tz.gettz("America/Chicago")),
                "room": "Main Ballroom",
                "description": "A test event"
            }
        ]
        
        # Act
        for ev in events:
            summary = ics_escape(ev["title"])
            dtstart = to_utc_z(ev["start"])
            dtend = to_utc_z(ev["end"])
            description = ics_escape(ev.get("description", ""))
            location = ics_escape(ev["room"]) if ev.get("room") else ""
        
        # Assert
        assert summary == "Test Event"
        assert len(dtstart) == 16
        assert len(dtend) == 16
        assert description == "A test event"
        assert location == "Main Ballroom"


class TestIntegration:
    """Integration tests for the complete workflow using mocked data."""
    
    def test_scrape_schedule_with_mock_html(self):
        """Test that scrape_schedule works with mocked HTML."""
        # Arrange
        mock_html = """
        <html>
        <body>
            <div class="relative">
                <h2>
                    <a href="#Day-1">
                        <span class="font-medium">Talks: Day 1</span> /
                        <time datetime="2025-09-08">Monday, Sep 8</time>
                    </a>
                </h2>
                <div class="flex flex-wrap gap-4 lg:gap-8">
                    <div class="w-full md:w-48">
                        <h3>
                            <time datetime="2025-09-08T09:00:00-05:00">9:00 am</time> to
                            <time datetime="2025-09-08T10:00:00-05:00">10:00 am</time>
                        </h3>
                    </div>
                    <ul>
                        <li>
                            <section>
                                <header>
                                    <div>
                                        <p class="text-sm">Main Ballroom</p>
                                    </div>
                                </header>
                                <h4>
                                    <a href="/talks/opening-keynote/">Opening Keynote</a>
                                </h4>
                                <div class="pt-6 mt-auto">
                                    <ul>
                                        <li>
                                            <h6>John Doe</h6>
                                        </li>
                                    </ul>
                                </div>
                                <span class="px-2 py-[.125rem] text-sm font-bold text-white bg-black rounded">Beginner</span>
                            </section>
                        </li>
                    </ul>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Act
        with patch('requests.get') as mock_get:
            mock_get.return_value.text = mock_html
            events = scrape_schedule("https://example.com/schedule/")
        
        # Assert
        assert len(events) == 1, "Should have scraped 1 event"
        
        event = events[0]
        assert event["title"] == "Opening Keynote"
        assert event["room"] == "Main Ballroom"
        assert "Presented by: John Doe" in event["description"]
        assert "Audience level: Beginner" in event["description"]
        assert "Location: Main Ballroom" in event["description"]
        assert isinstance(event["start"], datetime)
        assert isinstance(event["end"], datetime)
        assert event["end"] > event["start"]
    
    def test_generate_ics_with_mock_events(self, tmp_path):
        """Test that generate_ics creates a valid ICS file with mock events."""
        # Arrange
        chicago_tz = tz.gettz("America/Chicago")
        events = [
            {
                "title": "Test Event 1",
                "start": datetime(2025, 9, 8, 9, 0, tzinfo=chicago_tz),
                "end": datetime(2025, 9, 8, 10, 0, tzinfo=chicago_tz),
                "room": "Test Room",
                "description": "A test event for integration testing"
            },
            {
                "title": "Test Event 2",
                "start": datetime(2025, 9, 8, 14, 0, tzinfo=chicago_tz),
                "end": datetime(2025, 9, 8, 15, 0, tzinfo=chicago_tz),
                "room": "Another Room",
                "description": "Another test event"
            }
        ]
        
        ics_file = tmp_path / "test.ics"
        
        # Act
        generate_ics(events, str(ics_file))
        
        # Assert
        assert ics_file.exists(), "ICS file should be created"
        
        content = ics_file.read_text(encoding='utf-8')
        
        assert content.startswith("BEGIN:VCALENDAR"), "Should start with VCALENDAR"
        assert content.endswith("END:VCALENDAR"), "Should end with VCALENDAR"
        
        event_count = content.count("BEGIN:VEVENT")
        assert event_count == 2, f"Should have 2 events, found {event_count}"
        
        assert "Test Event 1" in content
        assert "Test Event 2" in content
        assert "Test Room" in content
        assert "Another Room" in content
        
        # Verify datetime format (should be in UTC Z format)
        assert "20250908T140000Z" in content  # 9:00 AM CDT = 2:00 PM UTC
        assert "20250908T190000Z" in content  # 2:00 PM CDT = 7:00 PM UTC
    
    def test_end_to_end_workflow_with_mock_data(self, tmp_path):
        """Test the complete workflow from mocked HTML to ICS file."""
        # Arrange
        mock_html = """
        <html>
        <body>
            <div class="relative">
                <h2>
                    <a href="#Day-1">
                        <span class="font-medium">Talks: Day 1</span> /
                        <time datetime="2025-09-08">Monday, Sep 8</time>
                    </a>
                </h2>
                <div class="flex flex-wrap gap-4 lg:gap-8">
                    <div class="w-full md:w-48">
                        <h3>
                            <time datetime="2025-09-08T09:00:00-05:00">9:00 am</time> to
                            <time datetime="2025-09-08T10:00:00-05:00">10:00 am</time>
                        </h3>
                    </div>
                    <ul>
                        <li>
                            <section>
                                <header>
                                    <div>
                                        <p class="text-sm">Main Ballroom</p>
                                    </div>
                                </header>
                                <h4>
                                    <a href="/talks/opening-keynote/">Opening Keynote</a>
                                </h4>
                                <div class="pt-6 mt-auto">
                                    <ul>
                                        <li>
                                            <h6>John Doe</h6>
                                        </li>
                                    </ul>
                                </div>
                            </section>
                        </li>
                    </ul>
                </div>
            </div>
            <div class="relative">
                <h2>
                    <a href="#Day-2">
                        <span class="font-medium">Talks: Day 2</span> /
                        <time datetime="2025-09-09">Tuesday, Sep 9</time>
                    </a>
                </h2>
                <div class="flex flex-wrap gap-4 lg:gap-8">
                    <div class="w-full md:w-48">
                        <h3>
                            <time datetime="2025-09-09T14:00:00-05:00">2:00 pm</time> to
                            <time datetime="2025-09-09T15:00:00-05:00">3:00 pm</time>
                        </h3>
                    </div>
                    <ul>
                        <li>
                            <section>
                                <header>
                                    <div>
                                        <p class="text-sm">Room 101</p>
                                    </div>
                                </header>
                                <h4>
                                    <a href="/talks/django-tips/">Django Tips & Tricks</a>
                                </h4>
                                <div class="pt-6 mt-auto">
                                    <ul>
                                        <li>
                                            <h6>Jane Smith</h6>
                                        </li>
                                    </ul>
                                </div>
                            </section>
                        </li>
                    </ul>
                </div>
            </div>
        </body>
        </html>
        """
        
        ics_file = tmp_path / "test.ics"
        
        # Act
        with patch('requests.get') as mock_get:
            mock_get.return_value.text = mock_html
            events = scrape_schedule("https://example.com/schedule/")
            generate_ics(events, str(ics_file))
        
        # Assert
        assert ics_file.exists(), "ICS file should be created"
        file_size = ics_file.stat().st_size
        assert file_size > 100, f"ICS file should have content, got {file_size} bytes"
        
        content = ics_file.read_text(encoding='utf-8')
        
        assert "BEGIN:VCALENDAR" in content
        assert "END:VCALENDAR" in content
        assert "BEGIN:VEVENT" in content
        assert "END:VEVENT" in content
        
        event_count = content.count("BEGIN:VEVENT")
        assert event_count == 2, f"Should have 2 events, found {event_count}"
        
        assert "Opening Keynote" in content
        assert "Django Tips & Tricks" in content
        assert "Main Ballroom" in content
        assert "Room 101" in content
    
    def test_cli_command_execution(self, tmp_path):
        """Test that the CLI command works correctly."""
        # Arrange
        mock_html = """
        <html>
        <body>
            <div class="relative">
                <h2>
                    <a href="#Day-1">
                        <span class="font-medium">Talks: Day 1</span> /
                        <time datetime="2025-09-08">Monday, Sep 8</time>
                    </a>
                </h2>
                <div class="flex flex-wrap gap-4 lg:gap-8">
                    <div class="w-full md:w-48">
                        <h3>
                            <time datetime="2025-09-08T09:00:00-05:00">9:00 am</time> to
                            <time datetime="2025-09-08T10:00:00-05:00">10:00 am</time>
                        </h3>
                    </div>
                    <ul>
                        <li>
                            <section>
                                <header>
                                    <div>
                                        <p class="text-sm">Main Ballroom</p>
                                    </div>
                                </header>
                                <h4>
                                    <a href="/talks/opening-keynote/">Opening Keynote</a>
                                </h4>
                                <div class="pt-6 mt-auto">
                                    <ul>
                                        <li>
                                            <h6>John Doe</h6>
                                        </li>
                                    </ul>
                                </div>
                            </section>
                        </li>
                    </ul>
                </div>
            </div>
        </body>
        </html>
        """
        
        ics_file = tmp_path / "test.ics"
        
        # Act
        with patch('requests.get') as mock_get:
            mock_get.return_value.text = mock_html
            with patch('sys.argv', ['main.py', '--out', str(ics_file)]):
                result = main()
        
        # Assert
        assert result == 0, "CLI should return success code"
        assert ics_file.exists(), "Output file should be created"
        
        content = ics_file.read_text(encoding='utf-8')
        
        assert "BEGIN:VCALENDAR" in content
        assert "Opening Keynote" in content
        assert "Main Ballroom" in content
    
    def test_cli_command_with_custom_url(self, tmp_path):
        """Test CLI command with custom URL parameter."""
        # Arrange
        mock_html = """
        <html>
        <body>
            <div class="relative">
                <h2>
                    <a href="#Day-1">
                        <span class="font-medium">Talks: Day 1</span> /
                        <time datetime="2025-09-08">Monday, Sep 8</time>
                    </a>
                </h2>
                <div class="flex flex-wrap gap-4 lg:gap-8">
                    <div class="w-full md:w-48">
                        <h3>
                            <time datetime="2025-09-08T09:00:00-05:00">9:00 am</time> to
                            <time datetime="2025-09-08T10:00:00-05:00">10:00 am</time>
                        </h3>
                    </div>
                    <ul>
                        <li>
                            <section>
                                <header>
                                    <div>
                                        <p class="text-sm">Main Ballroom</p>
                                    </div>
                                </header>
                                <h4>
                                    <a href="/talks/opening-keynote/">Opening Keynote</a>
                                </h4>
                            </section>
                        </li>
                    </ul>
                </div>
            </div>
        </body>
        </html>
        """
        
        ics_file = tmp_path / "test.ics"
        
        # Act
        with patch('requests.get') as mock_get:
            mock_get.return_value.text = mock_html
            with patch('main.fetch_talk_description') as mock_fetch:
                mock_fetch.return_value = ""
                with patch('sys.argv', ['main.py', '--url', 'https://custom.example.com/schedule/', '--out', str(ics_file)]):
                    result = main()
        
        # Assert
        assert result == 0, "CLI should return success code"
        assert ics_file.exists(), "Output file should be created"
        
        # Verify the custom URL was called (and the talk description fetch)
        assert mock_get.call_count >= 1, "Should have called requests.get at least once"
        assert mock_get.call_args_list[0] == (('https://custom.example.com/schedule/',), {'timeout': 30})
        
        content = ics_file.read_text(encoding='utf-8')
        
        assert "BEGIN:VCALENDAR" in content
        assert "Opening Keynote" in content


class TestParseDayEvents:
    """Test the parse_day_events function."""
    
    @pytest.fixture
    def valid_h2_with_events(self):
        """Fixture providing a valid h2 element with events."""
        html = """
        <div class="relative">
            <h2>
                <a href="#Day-1">
                    <span class="font-medium">Talks: Day 1</span> /
                    <time datetime="2025-09-08">Monday, Sep 8</time>
                </a>
            </h2>
            <div class="flex flex-wrap gap-4 lg:gap-8">
                <div class="w-full md:w-48">
                    <h3>
                        <time datetime="2025-09-08T09:00:00-05:00">9:00 am</time> to
                        <time datetime="2025-09-08T10:00:00-05:00">10:00 am</time>
                    </h3>
                </div>
                <ul>
                    <li>
                        <section>
                            <header>
                                <div>
                                    <p class="text-sm">Main Ballroom</p>
                                </div>
                            </header>
                            <h4>
                                <a href="/talks/opening-keynote/">Opening Keynote</a>
                            </h4>
                            <div class="pt-6 mt-auto">
                                <ul>
                                    <li>
                                        <h6>John Doe</h6>
                                    </li>
                                </ul>
                            </div>
                        </section>
                    </li>
                </ul>
            </div>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        return soup.find("h2")
    
    @pytest.fixture
    def h2_without_link(self):
        """Fixture providing an h2 element without a link."""
        html = """
        <h2>Talks: Day 1 / Monday, Sep 8</h2>
        """
        soup = BeautifulSoup(html, "html.parser")
        return soup.find("h2")
    
    @pytest.fixture
    def h2_with_schedule_text(self):
        """Fixture providing an h2 element with 'Schedule' text."""
        html = """
        <h2>
            <a href="#schedule">Schedule Overview</a>
        </h2>
        """
        soup = BeautifulSoup(html, "html.parser")
        return soup.find("h2")
    
    def test_parse_day_events_valid_h2(self, valid_h2_with_events):
        """Test parsing events from a valid h2 element."""
        # Arrange
        # The datetime strings in the HTML are "2025-09-08T09:00:00-05:00" and "2025-09-08T10:00:00-05:00"
        # which parse to 9:00 AM and 10:00 AM in CDT (UTC-5)
        expected = [
            {
                "title": "Opening Keynote",
                "room": "Main Ballroom",
                "description": "Presented by: John Doe\nLocation: Main Ballroom\n\nMore info: https://2025.djangocon.us/talks/opening-keynote/",
                "start": datetime(2025, 9, 8, 9, 0, tzinfo=tz.tzoffset(None, -5*3600)),  # 9:00 AM CDT
                "end": datetime(2025, 9, 8, 10, 0, tzinfo=tz.tzoffset(None, -5*3600)),    # 10:00 AM CDT
                "url": "https://2025.djangocon.us/talks/opening-keynote/",
                "talk_description": "",
            }
        ]
        
        # Act
        with patch('main.fetch_talk_description') as mock_fetch:
            mock_fetch.return_value = ""
            result = parse_day_events(valid_h2_with_events)
        
        # Assert
        assert result == expected
    
    def test_parse_day_events_no_link(self, h2_without_link):
        """Test parsing events from h2 without link returns empty list."""
        # Arrange
        expected = []
        
        # Act
        result = parse_day_events(h2_without_link)
        
        # Assert
        assert result == expected
    
    def test_parse_day_events_schedule_text(self, h2_with_schedule_text):
        """Test parsing events from h2 with 'Schedule' text returns empty list."""
        # Arrange
        expected = []
        
        # Act
        result = parse_day_events(h2_with_schedule_text)
        
        # Assert
        assert result == expected
    
    def test_parse_day_events_invalid_day_date(self):
        """Test parsing events with invalid day date format."""
        # Arrange
        html = """
        <h2>
            <a href="#Day-1">Invalid day format</a>
        </h2>
        """
        soup = BeautifulSoup(html, "html.parser")
        h2 = soup.find("h2")
        expected = []
        
        # Act
        result = parse_day_events(h2)
        
        # Assert
        assert result == expected
    
    def test_parse_day_events_no_day_container(self):
        """Test parsing events when day container is not found."""
        # Arrange
        html = """
        <h2>
            <a href="#Day-1">
                <span class="font-medium">Talks: Day 1</span> /
                <time datetime="2025-09-08">Monday, Sep 8</time>
            </a>
        </h2>
        """
        soup = BeautifulSoup(html, "html.parser")
        h2 = soup.find("h2")
        expected = []
        
        # Act
        result = parse_day_events(h2)
        
        # Assert
        assert result == expected


class TestParseTimeBlockEvents:
    """Test the parse_time_block_events function."""
    
    @pytest.fixture
    def valid_time_block(self):
        """Fixture providing a valid time block with events."""
        html = """
        <div class="flex flex-wrap gap-4 lg:gap-8">
            <div class="w-full md:w-48">
                <h3>
                    <time datetime="2025-09-08T09:00:00-05:00">9:00 am</time> to
                    <time datetime="2025-09-08T10:00:00-05:00">10:00 am</time>
                </h3>
            </div>
            <ul>
                <li>
                    <section>
                        <header>
                            <div>
                                <p class="text-sm">Main Ballroom</p>
                            </div>
                        </header>
                        <h4>
                            <a href="/talks/opening-keynote/">Opening Keynote</a>
                        </h4>
                        <div class="pt-6 mt-auto">
                            <ul>
                                <li>
                                    <h6>John Doe</h6>
                                </li>
                            </ul>
                        </div>
                    </section>
                </li>
            </ul>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        return soup.find("div", class_="flex flex-wrap gap-4 lg:gap-8")
    
    @pytest.fixture
    def time_block_no_h3(self):
        """Fixture providing a time block without h3 element."""
        html = """
        <div class="flex flex-wrap gap-4 lg:gap-8">
            <ul>
                <li>
                    <section>
                        <h4>Test Event</h4>
                    </section>
                </li>
            </ul>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        return soup.find("div", class_="flex flex-wrap gap-4 lg:gap-8")
    
    @pytest.fixture
    def time_block_wrong_time_elements(self):
        """Fixture providing a time block with wrong number of time elements."""
        html = """
        <div class="flex flex-wrap gap-4 lg:gap-8">
            <div class="w-full md:w-48">
                <h3>
                    <time datetime="2025-09-08T09:00:00-05:00">9:00 am</time>
                </h3>
            </div>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        return soup.find("div", class_="flex flex-wrap gap-4 lg:gap-8")
    
    @pytest.fixture
    def time_block_invalid_datetime(self):
        """Fixture providing a time block with invalid datetime attributes."""
        html = """
        <div class="flex flex-wrap gap-4 lg:gap-8">
            <div class="w-full md:w-48">
                <h3>
                    <time datetime="invalid">9:00 am</time> to
                    <time datetime="also-invalid">10:00 am</time>
                </h3>
            </div>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        return soup.find("div", class_="flex flex-wrap gap-4 lg:gap-8")
    
    def test_parse_time_block_events_valid(self, valid_time_block):
        """Test parsing events from a valid time block."""
        # Arrange
        # The datetime strings in the HTML are "2025-09-08T09:00:00-05:00" and "2025-09-08T10:00:00-05:00"
        # which parse to 9:00 AM and 10:00 AM in CDT (UTC-5)
        expected = [
            {
                "title": "Opening Keynote",
                "room": "Main Ballroom",
                "description": "Presented by: John Doe\nLocation: Main Ballroom\n\nMore info: https://2025.djangocon.us/talks/opening-keynote/",
                "start": datetime(2025, 9, 8, 9, 0, tzinfo=tz.tzoffset(None, -5*3600)),  # 9:00 AM CDT
                "end": datetime(2025, 9, 8, 10, 0, tzinfo=tz.tzoffset(None, -5*3600)),    # 10:00 AM CDT
                "url": "https://2025.djangocon.us/talks/opening-keynote/",
                "talk_description": "",
            }
        ]
        
        # Act
        with patch('main.fetch_talk_description') as mock_fetch:
            mock_fetch.return_value = ""
            result = parse_time_block_events(valid_time_block)
        
        # Assert
        assert result == expected
    
    def test_parse_time_block_events_no_h3(self, time_block_no_h3):
        """Test parsing events from time block without h3 returns empty list."""
        # Arrange
        expected = []
        
        # Act
        result = parse_time_block_events(time_block_no_h3)
        
        # Assert
        assert result == expected
    
    def test_parse_time_block_events_wrong_time_elements(self, time_block_wrong_time_elements):
        """Test parsing events from time block with wrong number of time elements."""
        # Arrange
        expected = []
        
        # Act
        result = parse_time_block_events(time_block_wrong_time_elements)
        
        # Assert
        assert result == expected
    
    def test_parse_time_block_events_invalid_datetime(self, time_block_invalid_datetime):
        """Test parsing events from time block with invalid datetime returns empty list."""
        # Arrange
        expected = []
        
        # Act
        result = parse_time_block_events(time_block_invalid_datetime)
        
        # Assert
        assert result == expected
    
    def test_parse_time_block_events_missing_datetime_attributes(self):
        """Test parsing events from time block with missing datetime attributes."""
        # Arrange
        html = """
        <div class="flex flex-wrap gap-4 lg:gap-8">
            <div class="w-full md:w-48">
                <h3>
                    <time>9:00 am</time> to
                    <time>10:00 am</time>
                </h3>
            </div>
        </div>
        """
        soup = BeautifulSoup(html, "html.parser")
        time_block = soup.find("div", class_="flex flex-wrap gap-4 lg:gap-8")
        expected = []
        
        # Act
        result = parse_time_block_events(time_block)
        
        # Assert
        assert result == expected


class TestFetchTalkDescription:
    """Test the fetch_talk_description function."""
    
    def test_fetch_talk_description_with_mock_response(self):
        """Test fetching talk description with mocked response."""
        # Arrange
        mock_html = """
        <html>
        <body>
            <h2>About this session</h2>
            <div class="prose">
                <p>This is a test talk description.</p>
                <p>It has multiple paragraphs.</p>
            </div>
        </body>
        </html>
        """
        
        # Act
        with patch('requests.get') as mock_get:
            mock_response = mock_get.return_value
            mock_response.text = mock_html
            mock_response.raise_for_status.return_value = None
            result = fetch_talk_description("https://example.com/talk")
        
        # Assert
        assert result == "This is a test talk description.\n\nIt has multiple paragraphs."
        mock_get.assert_called_once_with("https://example.com/talk", timeout=10)
    
    def test_fetch_talk_description_empty_url(self):
        """Test fetching talk description with empty URL."""
        # Act
        result = fetch_talk_description("")
        
        # Assert
        assert result == ""
    
    def test_fetch_talk_description_no_about_section(self):
        """Test fetching talk description when no about section exists."""
        # Arrange
        mock_html = "<html><body><h2>Other section</h2></body></html>"
        
        # Act
        with patch('requests.get') as mock_get:
            mock_response = mock_get.return_value
            mock_response.text = mock_html
            mock_response.raise_for_status.return_value = None
            result = fetch_talk_description("https://example.com/talk")
        
        # Assert
        assert result == ""
    
    def test_fetch_talk_description_request_error(self):
        """Test fetching talk description when request fails."""
        # Act
        with patch('requests.get') as mock_get:
            mock_get.side_effect = requests.RequestException("Network error")
            result = fetch_talk_description("https://example.com/talk")
        
        # Assert
        assert result == ""


class TestParseSectionEvent:
    """Test the parse_section_event function."""
    
    @pytest.fixture
    def valid_section_with_all_fields(self):
        """Fixture providing a section with all possible fields."""
        html = """
        <section>
            <header>
                <div>
                    <p class="text-sm">Main Ballroom</p>
                </div>
            </header>
            <h4>
                <a href="/talks/opening-keynote/">Opening Keynote</a>
            </h4>
            <div class="pt-6 mt-auto">
                <ul>
                    <li>
                        <h6>John Doe</h6>
                    </li>
                    <li>
                        <h6>Jane Smith</h6>
                    </li>
                </ul>
            </div>
            <span class="px-2 py-[.125rem] text-sm font-bold text-white bg-black rounded">Intermediate</span>
        </section>
        """
        soup = BeautifulSoup(html, "html.parser")
        return soup.find("section")
    
    @pytest.fixture
    def section_without_h4(self):
        """Fixture providing a section without h4 element."""
        html = """
        <section>
            <header>
                <div>
                    <p class="text-sm">Main Ballroom</p>
                </div>
            </header>
        </section>
        """
        soup = BeautifulSoup(html, "html.parser")
        return soup.find("section")
    
    @pytest.fixture
    def section_h4_without_link(self):
        """Fixture providing a section with h4 but no link."""
        html = """
        <section>
            <h4>Opening Keynote</h4>
        </section>
        """
        soup = BeautifulSoup(html, "html.parser")
        return soup.find("section")
    
    @pytest.fixture
    def section_with_all_level_audience(self):
        """Fixture providing a section with 'All' audience level."""
        html = """
        <section>
            <h4>Opening Keynote</h4>
            <span class="px-2 py-[.125rem] text-sm font-bold text-white bg-black rounded">All</span>
        </section>
        """
        soup = BeautifulSoup(html, "html.parser")
        return soup.find("section")
    
    @pytest.fixture
    def minimal_section(self):
        """Fixture providing a minimal section with only title."""
        html = """
        <section>
            <h4>Minimal Event</h4>
        </section>
        """
        soup = BeautifulSoup(html, "html.parser")
        return soup.find("section")
    
    @pytest.fixture
    def chicago_tz(self):
        """Fixture providing Chicago timezone."""
        return tz.gettz("America/Chicago")
    
    def test_parse_section_event_complete(self, valid_section_with_all_fields, chicago_tz):
        """Test parsing a complete section event with all fields."""
        # Arrange
        start_dt = datetime(2025, 9, 8, 9, 0, tzinfo=chicago_tz)
        end_dt = datetime(2025, 9, 8, 10, 0, tzinfo=chicago_tz)
        expected = {
            "title": "Opening Keynote",
            "room": "Main Ballroom",
            "start": start_dt,
            "end": end_dt,
            "description": "Presented by: John Doe, Jane Smith\nAudience level: Intermediate\nLocation: Main Ballroom\n\nMore info: https://2025.djangocon.us/talks/opening-keynote/",
            "url": "https://2025.djangocon.us/talks/opening-keynote/",
            "talk_description": "",
        }
        
        # Act
        with patch('main.fetch_talk_description') as mock_fetch:
            mock_fetch.return_value = ""
            result = parse_section_event(valid_section_with_all_fields, start_dt, end_dt)
        
        # Assert
        assert result == expected
    
    def test_parse_section_event_no_h4(self, section_without_h4, chicago_tz):
        """Test parsing section without h4 returns None."""
        # Arrange
        start_dt = datetime(2025, 9, 8, 9, 0, tzinfo=chicago_tz)
        end_dt = datetime(2025, 9, 8, 10, 0, tzinfo=chicago_tz)
        expected = None
        
        # Act
        result = parse_section_event(section_without_h4, start_dt, end_dt)
        
        # Assert
        assert result == expected
    
    def test_parse_section_event_h4_without_link(self, section_h4_without_link, chicago_tz):
        """Test parsing section with h4 but no link."""
        # Arrange
        start_dt = datetime(2025, 9, 8, 9, 0, tzinfo=chicago_tz)
        end_dt = datetime(2025, 9, 8, 10, 0, tzinfo=chicago_tz)
        expected = {
            "title": "Opening Keynote",
            "room": "",
            "start": start_dt,
            "end": end_dt,
            "description": "",
            "url": "",
            "talk_description": "",
        }
        
        # Act
        result = parse_section_event(section_h4_without_link, start_dt, end_dt)
        
        # Assert
        assert result == expected
    
    def test_parse_section_event_all_audience_level(self, section_with_all_level_audience, chicago_tz):
        """Test parsing section with 'All' audience level is not included in description."""
        # Arrange
        start_dt = datetime(2025, 9, 8, 9, 0, tzinfo=chicago_tz)
        end_dt = datetime(2025, 9, 8, 10, 0, tzinfo=chicago_tz)
        expected = {
            "title": "Opening Keynote",
            "room": "",
            "start": start_dt,
            "end": end_dt,
            "description": "",
            "url": "",
            "talk_description": "",
        }
        
        # Act
        result = parse_section_event(section_with_all_level_audience, start_dt, end_dt)
        
        # Assert
        assert result == expected
    
    def test_parse_section_event_minimal(self, minimal_section, chicago_tz):
        """Test parsing minimal section with only title."""
        # Arrange
        start_dt = datetime(2025, 9, 8, 9, 0, tzinfo=chicago_tz)
        end_dt = datetime(2025, 9, 8, 10, 0, tzinfo=chicago_tz)
        expected = {
            "title": "Minimal Event",
            "room": "",
            "start": start_dt,
            "end": end_dt,
            "description": "",
            "url": "",
            "talk_description": "",
        }
        
        # Act
        result = parse_section_event(minimal_section, start_dt, end_dt)
        
        # Assert
        assert result == expected
    
    def test_parse_section_event_empty_title(self, chicago_tz):
        """Test parsing section with empty title returns None."""
        # Arrange
        html = """
        <section>
            <h4></h4>
        </section>
        """
        soup = BeautifulSoup(html, "html.parser")
        section = soup.find("section")
        start_dt = datetime(2025, 9, 8, 9, 0, tzinfo=chicago_tz)
        end_dt = datetime(2025, 9, 8, 10, 0, tzinfo=chicago_tz)
        expected = None
        
        # Act
        result = parse_section_event(section, start_dt, end_dt)
        
        # Assert
        assert result == expected
    
    def test_parse_section_event_no_presenters(self, chicago_tz):
        """Test parsing section without presenters."""
        # Arrange
        html = """
        <section>
            <h4>Event Without Presenters</h4>
            <p class="text-sm">Room 101</p>
        </section>
        """
        soup = BeautifulSoup(html, "html.parser")
        section = soup.find("section")
        start_dt = datetime(2025, 9, 8, 9, 0, tzinfo=chicago_tz)
        end_dt = datetime(2025, 9, 8, 10, 0, tzinfo=chicago_tz)
        expected = {
            "title": "Event Without Presenters",
            "room": "Room 101",
            "start": start_dt,
            "end": end_dt,
            "description": "Location: Room 101",
            "url": "",
            "talk_description": "",
        }
        
        # Act
        result = parse_section_event(section, start_dt, end_dt)
        
        # Assert
        assert result == expected


if __name__ == "__main__":
    pytest.main([__file__])
