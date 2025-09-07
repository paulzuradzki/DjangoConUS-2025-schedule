# DjangoCon US 2025 Schedule to ICS

Scrapes the DjangoCon US 2025 schedule and exports it to an ICS calendar file.

## Installation

```bash
uv sync                    # Install dependencies
uv sync --group dev       # Include dev dependencies for testing
```

## Usage

```bash
uv run python main.py                                   # Default output. Creates djangocon-2025.ics in current directory.
uv run python main.py --out my-schedule.ics             # Custom output file
uv run python main.py --url <url> --out <file>          # Custom URL
```

## Testing

```bash
uv run pytest
```

## Output

Generates an ICS file with all conference events:
- Talks, keynotes, breaks, meals, special events, sprints
- Times converted to UTC, includes locations and presenters

## Dependencies

To add dependencies:
```bash
uv add requests beautifulsoup4 python-dateutil
uv add --group dev pytest
```
