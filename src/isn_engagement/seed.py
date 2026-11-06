"""Synthetic data generator producing realistic, slightly messy CSV exports.

Every person is fake (generated with Faker using a fixed seed). The raw exports
intentionally include the kinds of problems real club tools produce (duplicate
rows, inconsistent casing, blank fields, mixed date formats, orphan check-ins,
invalid capacities) so the ETL data quality step has something to catch.
"""

from __future__ import annotations

import argparse
import csv
import random
from datetime import date, datetime, timedelta
from pathlib import Path

from faker import Faker

MAJORS = {
    "Management Information Systems": 0.35,
    "Computer Science and Engineering": 0.18,
    "Finance": 0.12,
    "Marketing": 0.10,
    "Economics": 0.08,
    "Accounting": 0.07,
    "Business Analytics": 0.10,
}
CLASS_YEARS = ["Freshman", "Sophomore", "Junior", "Senior"]
TOPICS: dict[str, list[str]] = {
    "SQL & Data": ["Intro to SQL", "Advanced SQL Joins", "Data Modeling 101", "Query Tuning Lab"],
    "Product Management": [
        "PM Case Interview Prep",
        "Writing a PRD",
        "Agile and Scrum Basics",
        "Roadmapping Workshop",
    ],
    "Data Visualization": ["Tableau Bootcamp", "Dashboard Design", "Storytelling with Data"],
    "Career": [
        "Resume Review Night",
        "Tech Consulting Panel",
        "Mock Interviews",
        "LinkedIn Headshots",
    ],
    "Python": ["Python for Analysts", "Pandas Workshop", "Automating Excel with Python"],
    "GenAI": ["Prompting for Analysts", "Building with LLM APIs", "AI in the Enterprise Panel"],
    "Social": ["Kickoff Mixer", "Boba Social", "End of Quarter Social"],
}
TOPIC_PULL = {
    "SQL & Data": 1.2,
    "Product Management": 1.3,
    "Career": 1.45,
    "Data Visualization": 1.0,
    "Python": 1.1,
    "GenAI": 1.35,
    "Social": 0.85,
}
EVENT_TYPE = {"Career": "Panel", "Social": "Social"}
LOCATIONS = [
    "Lucas Hall 126",
    "Lucas Hall 207",
    "Benson Center Parlors",
    "Learning Commons 1st Floor",
    "Zoom",
]
# Fall 2025, Winter 2026, Spring 2026 quarter start dates.
TERM_STARTS = [date(2025, 9, 22), date(2026, 1, 5), date(2026, 3, 30)]
TERM_LENGTH_DAYS = 70
JOIN_WEIGHTS = [0.6, 0.25, 0.15]


def _pick_weighted(rng: random.Random, weights: dict[str, float]) -> str:
    return rng.choices(list(weights), weights=list(weights.values()), k=1)[0]


def _members(rng: random.Random, fake: Faker, n: int) -> list[dict[str, str]]:
    rows = []
    for i in range(1, n + 1):
        first, last = fake.first_name(), fake.last_name()
        start = TERM_STARTS[rng.choices(range(len(TERM_STARTS)), weights=JOIN_WEIGHTS)[0]]
        join = start + timedelta(days=rng.randint(0, 20))
        rows.append(
            {
                "member_id": f"M{i:04d}",
                "first_name": first,
                "last_name": last,
                "email": f"{first[0].lower()}{last.lower().replace(' ', '')}{i}@scu.edu",
                "major": _pick_weighted(rng, MAJORS),
                "class_year": rng.choice(CLASS_YEARS),
                "join_date": join.isoformat(),
            }
        )
    return rows


def _events(rng: random.Random, n: int) -> list[dict[str, str]]:
    per_term = [
        n // len(TERM_STARTS) + (1 if k < n % len(TERM_STARTS) else 0)
        for k in range(len(TERM_STARTS))
    ]
    rows: list[dict[str, str]] = []
    for start, count in zip(TERM_STARTS, per_term, strict=True):
        for k in range(count):
            topic = "Social" if k == 0 else rng.choice(list(TOPICS))
            day = int(k * TERM_LENGTH_DAYS / max(count, 1)) + rng.randint(0, 3)
            rows.append(
                {
                    "event_id": f"E{len(rows) + 1:03d}",
                    "title": "Kickoff Mixer" if k == 0 else rng.choice(TOPICS[topic]),
                    "topic": topic,
                    "event_type": EVENT_TYPE.get(topic, "Workshop"),
                    "event_date": (start + timedelta(days=day)).isoformat(),
                    "location": rng.choice(LOCATIONS),
                    "capacity": str(rng.choice([30, 40, 50, 60, 80])),
                }
            )
    return rows


def _attendance(
    rng: random.Random, members: list[dict[str, str]], events: list[dict[str, str]]
) -> list[dict[str, str]]:
    # Each member gets a latent engagement level; some drift away term over term.
    engagement = {m["member_id"]: rng.betavariate(2, 4) for m in members}
    decay = {m["member_id"]: rng.choice([1.0, 1.0, 0.85, 0.6, 0.35]) for m in members}
    rows = []
    for ev in events:
        ev_date = date.fromisoformat(ev["event_date"])
        term_idx = sum(ev_date >= s for s in TERM_STARTS) - 1
        for m in members:
            join = date.fromisoformat(m["join_date"])
            if join > ev_date:
                continue
            mid = m["member_id"]
            join_idx = sum(join >= s for s in TERM_STARTS) - 1
            terms_in = term_idx - join_idx
            p = engagement[mid] * (decay[mid] ** terms_in) * TOPIC_PULL[ev["topic"]] * 0.55
            if rng.random() < p:
                ts = (
                    datetime.combine(ev_date, datetime.min.time())
                    + timedelta(hours=18)
                    - timedelta(hours=rng.randint(2, 240))
                )
                rows.append(
                    {
                        "member_id": mid,
                        "event_id": ev["event_id"],
                        "signup_ts": ts.strftime("%Y-%m-%d %H:%M:%S"),
                        "checked_in": rng.choices(["Y", "N"], weights=[0.8, 0.2])[0],
                    }
                )
    return rows


def _inject_dirt(
    rng: random.Random,
    members: list[dict[str, str]],
    events: list[dict[str, str]],
    attendance: list[dict[str, str]],
) -> None:
    """Add the realistic messiness that the ETL quality step is built to catch."""
    for m in rng.sample(members, 6):
        m["email"] = "  " + m["email"].upper() + " "
    for m in rng.sample(members, 5):
        m["major"] = ""
    for m in rng.sample(members, 4):
        m["class_year"] = m["class_year"].lower()
    members.append(dict(members[3]))  # duplicate export row
    members[10]["join_date"] = date.fromisoformat(members[10]["join_date"]).strftime("%m/%d/%Y")
    events[5]["event_date"] = events[5]["event_date"].replace("-", "/")  # alt date format
    events[8]["capacity"] = "0"  # invalid capacity from the room booking tool
    events[12]["topic"] = " " + events[12]["topic"].lower() + " "
    attendance.append(dict(attendance[0]))  # duplicate check-in
    for row in rng.sample(attendance, 8):
        row["checked_in"] = (
            rng.choice(["yes", "TRUE", "1"])
            if row["checked_in"] == "Y"
            else rng.choice(["no", "FALSE", "0"])
        )
    attendance.append(
        {
            "member_id": "M9999",
            "event_id": "E001",
            "signup_ts": "2025-09-20 10:00:00",
            "checked_in": "Y",
        }
    )  # orphan member
    attendance.append(
        {
            "member_id": "M0001",
            "event_id": "E999",
            "signup_ts": "2025-09-20 10:00:00",
            "checked_in": "yes",
        }
    )  # orphan event
    attendance.append(
        {
            "member_id": "M0002",
            "event_id": "E002",
            "signup_ts": "not a timestamp",
            "checked_in": "Y",
        }
    )


def generate(
    out_dir: Path, n_members: int = 200, n_events: int = 40, seed: int = 42, dirty: bool = True
) -> dict[str, int]:
    """Write members.csv, events.csv, attendance.csv into ``out_dir``.

    Returns the number of rows written per file. Output is deterministic for a
    given seed.
    """
    if n_members < 12 or n_events < 13:
        raise ValueError("Need at least 12 members and 13 events to generate a dataset")
    rng = random.Random(seed)
    fake = Faker("en_US")
    fake.seed_instance(seed)
    out_dir.mkdir(parents=True, exist_ok=True)

    members = _members(rng, fake, n_members)
    events = _events(rng, n_events)
    attendance = _attendance(rng, members, events)
    if dirty:
        _inject_dirt(rng, members, events, attendance)

    for name, rows in (("members", members), ("events", events), ("attendance", attendance)):
        with open(out_dir / f"{name}.csv", "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return {"members": len(members), "events": len(events), "attendance": len(attendance)}


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Generate synthetic ISN CSV exports.")
    p.add_argument("--out", type=Path, default=Path("data/raw"))
    p.add_argument("--members", type=int, default=200)
    p.add_argument("--events", type=int, default=40)
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args(argv)
    counts = generate(args.out, args.members, args.events, args.seed)
    print(f"Wrote {counts} to {args.out}")


if __name__ == "__main__":
    main()
