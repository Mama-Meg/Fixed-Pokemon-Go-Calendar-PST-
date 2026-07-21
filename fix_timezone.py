#!/usr/bin/env python3
"""
Fix the floating-time bug in the go-calendar Pokemon GO .ics feed.

Problem: go-calendar publishes timed events as "floating" times
(DTSTART:20260720T060000 with no TZID and no Z). Google Calendar does
NOT support floating times and treats them as UTC, which shifts every
timed event by the viewer's UTC offset (e.g. 06:00 -> 06:00 UTC = 23:00
Pacific the day before).

Fix: add TZID=America/Los_Angeles to every timed DTSTART/DTEND and emit a
VTIMEZONE block so the zone resolves. All-day (VALUE=DATE) events are
left untouched. The result keeps Leek Duck's intended local times.

Usage:
  python3 fix_timezone.py <input.ics> <output.ics> [TZID]
  python3 fix_timezone.py gocal.ics gocal-fixed.ics America/Los_Angeles
"""
import sys
import re

TZID_DEFAULT = "America/Los_Angeles"

# VTIMEZONE for America/Los_Angeles (PST/PDT). Browsers/calendars resolve
# the TZID via tzdata; the embedded VTIMEZONE is a fallback for strict parsers.
VTIMEZONE_BLOCK = """BEGIN:VTIMEZONE
TZID:America/Los_Angeles
X-LIC-LOCATION:America/Los_Angeles
BEGIN:DAYLIGHT
TZOFFSETFROM:-0800
TZOFFSETTO:-0700
TZNAME:PDT
DTSTART:19700308T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0700
TZOFFSETTO:-0800
TZNAME:PST
DTSTART:19701101T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
END:STANDARD
END:VTIMEZONE
"""

# Matches timed DTSTART/DTEND lines WITHOUT a TZID and WITHOUT a Z suffix,
# and WITHOUT VALUE=DATE (all-day). Captures: (1) prop name, (2) any params
# already present like ";VALUE=DATE-TIME", (3) the datetime value.
TIMED_RE = re.compile(
    r"^(DTSTART|DTEND)((?:;[^:=]+(?:=[^;:]+)?)*)"
    r":(\d{8}T\d{6})$"
)


def is_all_day_params(params: str) -> bool:
    # Match VALUE=DATE exactly, not VALUE=DATE-TIME (which is a timed event).
    return re.search(r";VALUE=DATE(?=;|$)", params.upper()) is not None


def line_ending(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    return ""


def fix_line(line: str, tzid: str) -> str:
    eol = line_ending(line)
    body = line[:-len(eol)] if eol else line
    m = TIMED_RE.match(body)
    if not m:
        return line
    prop, params, value = m.group(1), m.group(2) or "", m.group(3)
    if is_all_day_params(params):
        return line  # all-day event, leave as-is
    if "TZID=" in params.upper():
        return line  # already has a timezone
    return f"{prop}{params};TZID={tzid}:{value}{eol}"


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    in_path, out_path = sys.argv[1], sys.argv[2]
    tzid = sys.argv[3] if len(sys.argv) > 3 else TZID_DEFAULT

    with open(in_path, "r", encoding="utf-8") as f:
        lines = f.read().splitlines(keepends=True)

    out = []
    vtimezone_injected = False
    fixed_count = 0

    for line in lines:
        stripped = line.rstrip("\r\n")
        # Inject VTIMEZONE + X-WR-TIMEZONE right after BEGIN:VCALENDAR.
        if stripped == "BEGIN:VCALENDAR" and not vtimezone_injected:
            out.append(line)
            out.append(f"X-WR-TIMEZONE:{tzid}\r\n")
            out.append(VTIMEZONE_BLOCK)
            vtimezone_injected = True
            continue

        before = line.rstrip("\r\n")
        new = fix_line(line, tzid)
        if new.rstrip("\r\n") != before and new.startswith(("DTSTART", "DTEND")):
            fixed_count += 1
        out.append(new)

    if not vtimezone_injected:
        # Fallback: prepend into the calendar body somewhere safe.
        out.insert(0, VTIMEZONE_BLOCK)

    with open(out_path, "w", encoding="utf-8") as f:
        f.writelines(out)

    print(f"Wrote {out_path} | TZID={tzid} | fixed {fixed_count} timed DTSTART/DTEND lines")


if __name__ == "__main__":
    main()
