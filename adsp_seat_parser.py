from __future__ import annotations

import re
from dataclasses import dataclass


TARGET_EXAM = "제50회 데이터 분석 준전문가(ADsP)"

REGION_PRIORITY = [
    "서울특별시",
    "경기도",
    "인천광역시",
    "광주광역시",
    "울산광역시",
    "강원도",
    "부산광역시",
    "대전광역시",
    "대구광역시",
]

EXCLUDED_REGION_KEYWORDS = ["제주도", "제주"]

SEAT_PATTERN = re.compile(r"잔여\s*좌석\s*[:：]?\s*(\d+)")
NUMBER_ONLY_PATTERN = re.compile(r"^\s*(\d+)\s*$")
TABLE_ROW_SEAT_PATTERN = re.compile(r"(?:운영|미운영)?\s+(\d+)\s+(?:보기|지도)\s*$")
OCR_ROW_PATTERN = re.compile(r"^\s*(\d{1,3})\b")
INTEGER_PATTERN = re.compile(r"\d+")


@dataclass(frozen=True)
class SeatHit:
    region: str
    seats: int
    line: str
    priority: int


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"[ \t]+", " ", text)


def is_excluded(line: str) -> bool:
    return any(keyword in line for keyword in EXCLUDED_REGION_KEYWORDS)


def region_priority(region: str) -> int:
    try:
        return REGION_PRIORITY.index(region)
    except ValueError:
        return len(REGION_PRIORITY)


def find_region(line: str) -> str | None:
    for region in REGION_PRIORITY:
        if region in line:
            return region
    return None


def extract_seat_count(line: str) -> int | None:
    match = SEAT_PATTERN.search(line)
    if match:
        return int(match.group(1))

    table_match = TABLE_ROW_SEAT_PATTERN.search(line)
    if table_match:
        return int(table_match.group(1))

    return None


def extract_ocr_row_hit(line: str) -> SeatHit | None:
    row_match = OCR_ROW_PATTERN.match(line)
    if not row_match or is_excluded(line):
        return None
    if "ADSP" not in line.upper():
        return None

    row_number = int(row_match.group(1))
    if row_number < 1 or row_number > 300:
        return None

    numbers = [int(match.group(0)) for match in INTEGER_PATTERN.finditer(line)]
    if len(numbers) < 2:
        return None

    if numbers[0] == row_number:
        numbers = numbers[1:]
    if not numbers:
        return None

    seat_candidate = numbers[-1]
    if seat_candidate < 1 or seat_candidate > 999:
        return None

    return SeatHit(
        region=f"OCR No.{row_number}",
        seats=seat_candidate,
        line=line,
        priority=len(REGION_PRIORITY),
    )


def parse_seat_hits(text: str) -> list[SeatHit]:
    normalized = normalize_text(text)
    hits: list[SeatHit] = []

    for raw_line in normalized.splitlines():
        line = raw_line.strip()
        if not line or is_excluded(line):
            continue

        region = find_region(line)
        seats = extract_seat_count(line)

        if region is None or seats is None or seats < 1:
            continue

        hits.append(
            SeatHit(
                region=region,
                seats=seats,
                line=line,
                priority=region_priority(region),
            )
        )

    hits.sort(key=lambda hit: (hit.priority, -hit.seats, hit.line))
    return hits


def parse_table_like_hits(text: str) -> list[SeatHit]:
    normalized = normalize_text(text)
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    hits = parse_seat_hits(normalized)

    for index, line in enumerate(lines):
        if is_excluded(line):
            continue

        region = find_region(line)
        if region is None:
            continue

        explicit_seats = extract_seat_count(line)
        if explicit_seats is not None:
            continue

        candidates = [line]
        if index + 1 < len(lines):
            candidates.append(lines[index + 1])
        if index + 2 < len(lines):
            candidates.append(lines[index + 2])

        for candidate in candidates:
            if "보기" in candidate or "지도" in candidate:
                continue
            match = NUMBER_ONLY_PATTERN.match(candidate)
            if not match:
                continue

            seats = int(match.group(1))
            if seats < 1:
                break

            hits.append(
                SeatHit(
                    region=region,
                    seats=seats,
                    line=line,
                    priority=region_priority(region),
                )
            )
            break

    for line in lines:
        fallback_hit = extract_ocr_row_hit(line)
        if fallback_hit is not None:
            hits.append(fallback_hit)

    unique: dict[tuple[str, int, str], SeatHit] = {
        (hit.region, hit.seats, hit.line): hit for hit in hits
    }
    return sorted(unique.values(), key=lambda hit: (hit.priority, -hit.seats, hit.line))



