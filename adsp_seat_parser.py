from __future__ import annotations

import re
from dataclasses import dataclass


TARGET_EXAM = "DataQ 자격검정"

REGION_KEYWORDS = [
    "서울특별시",
    "경기도",
    "인천광역시",
    "광주광역시",
    "울산광역시",
    "강원도",
    "부산광역시",
    "대전광역시",
    "대구광역시",
    "충청북도",
    "충청남도",
    "전라북도",
    "전라남도",
    "경상북도",
    "경상남도",
    "세종특별자치시",
    "제주특별자치도",
    "제주도",
]
ALL_REGION_KEYWORDS = REGION_KEYWORDS

SEAT_PATTERN = re.compile(r"잔여\s*좌석\s*[:：]?\s*(\d+)")
NUMBER_ONLY_PATTERN = re.compile(r"^\s*(\d+)\s*$")
TABLE_ROW_SEAT_PATTERN = re.compile(r"(?:운영|미운영)\s+(\d+)\s+(?:보기|지도)?\s*$")
OCR_ROW_PATTERN = re.compile(r"^\s*(\d{1,3})\b")
INTEGER_PATTERN = re.compile(r"\d+")
KNOWN_EXAM_CODE_PATTERN = re.compile(
    r"\b(?:ADSP|ADP|SQLD|SQLP|DAP|DASP|DATAQ)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class SeatHit:
    region: str
    seats: int
    line: str
    priority: int
    no: int | None = None
    site_name: str = ""
    address: str = ""
    source: str = "ocr"


@dataclass(frozen=True)
class ClipboardSeatRow:
    no: int
    region: str
    site_name: str
    address: str
    seats: int | None
    line: str


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return re.sub(r"[ \t]+", " ", text)


def seat_hit_sort_key(hit: SeatHit) -> tuple[int, str]:
    row_number = hit.no if hit.no is not None else hit.priority
    return row_number, hit.line


def find_region(line: str) -> str | None:
    for region in REGION_KEYWORDS:
        if region in line:
            return region
    return None


def find_any_region(line: str) -> str | None:
    for region in ALL_REGION_KEYWORDS:
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
    if not row_match:
        return None
    if not KNOWN_EXAM_CODE_PATTERN.search(line):
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
        priority=row_number,
        no=row_number,
    )


def _compact_cells(line: str) -> list[str]:
    if "\t" in line:
        return [cell.strip() for cell in line.split("\t") if cell.strip()]
    return [cell.strip() for cell in re.split(r"\s{2,}", line) if cell.strip()]


def _seat_from_cells(cells: list[str]) -> int | None:
    for cell in reversed(cells):
        if cell in {"보기", "지도", "운영", "미운영"}:
            continue
        match = NUMBER_ONLY_PATTERN.match(cell)
        if match:
            return int(match.group(1))
    return None


def _row_from_cells(cells: list[str]) -> ClipboardSeatRow | None:
    if len(cells) < 4 or not NUMBER_ONLY_PATTERN.match(cells[0]):
        return None
    no = int(cells[0])
    if no < 1 or no > 300:
        return None
    region = find_any_region(cells[1]) or find_any_region(" ".join(cells))
    if region is None:
        return None
    site_name = cells[2] if len(cells) > 2 else ""
    address = cells[3] if len(cells) > 3 else ""
    seats = _seat_from_cells(cells[4:])
    return ClipboardSeatRow(no=no, region=region, site_name=site_name, address=address, seats=seats, line=" | ".join(cells))


def _row_from_flat_line(line: str) -> ClipboardSeatRow | None:
    row_match = OCR_ROW_PATTERN.match(line)
    if not row_match:
        return None
    no = int(row_match.group(1))
    region = find_any_region(line)
    if region is None:
        return None
    seats = extract_seat_count(line)
    site_name = ""
    site_match = re.search(
        r"((?:ADsP|ADP|SQLD|SQLP|DAP|DAsP)\s*\([^)]*\)\s*.+?)(?:\s{2,}|\s+[가-힣]+[시군구]\s)",
        line,
        re.IGNORECASE,
    )
    if site_match:
        site_name = site_match.group(1).strip()
    return ClipboardSeatRow(no=no, region=region, site_name=site_name, address="", seats=seats, line=line)


def parse_clipboard_rows(text: str) -> dict[int, ClipboardSeatRow]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    raw_lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    rows: dict[int, ClipboardSeatRow] = {}

    for line in raw_lines:
        if line in {"No.", "No", "지역", "고사장명", "주소", "잔여좌석", "지도"}:
            continue
        row = _row_from_cells(_compact_cells(line)) or _row_from_flat_line(line)
        if row is not None:
            rows[row.no] = row

    for index, line in enumerate(raw_lines):
        if not NUMBER_ONLY_PATTERN.match(line):
            continue
        no = int(line)
        if no in rows or index + 2 >= len(raw_lines):
            continue
        region = find_any_region(raw_lines[index + 1])
        if region is None:
            continue
        cells = raw_lines[index : min(len(raw_lines), index + 8)]
        seat = _seat_from_cells(cells[4:])
        rows[no] = ClipboardSeatRow(
            no=no,
            region=region,
            site_name=cells[2] if len(cells) > 2 else "",
            address=cells[3] if len(cells) > 3 else "",
            seats=seat,
            line=" | ".join(cells),
        )

    return rows


def ocr_hit_row_number(hit: SeatHit) -> int | None:
    match = re.search(r"(?:OCR\s*)?No\.(\d{1,3})", hit.region)
    if match:
        return int(match.group(1))
    line_match = OCR_ROW_PATTERN.match(hit.line)
    if line_match:
        return int(line_match.group(1))
    return None


def clipboard_rows_to_hits(text: str) -> list[SeatHit]:
    hits: list[SeatHit] = []
    for row in parse_clipboard_rows(text).values():
        if row.seats is None or row.seats < 1:
            continue
        detail_parts = [f"No.{row.no}", row.region]
        if row.site_name:
            detail_parts.append(row.site_name)
        if row.address:
            detail_parts.append(row.address)
        detail_parts.append(f"클립보드 {row.seats}석")
        hits.append(
            SeatHit(
                region=row.region,
                seats=row.seats,
                line=" - ".join(detail_parts),
                priority=row.no,
                no=row.no,
                site_name=row.site_name,
                address=row.address,
                source="clipboard",
            )
        )
    return sorted(hits, key=seat_hit_sort_key)


def enrich_hits_with_clipboard(hits: list[SeatHit], clipboard_text: str) -> list[SeatHit]:
    if not clipboard_text.strip():
        return hits
    rows = parse_clipboard_rows(clipboard_text)
    if not rows:
        return hits

    enriched: list[SeatHit] = []
    for hit in hits:
        row_no = ocr_hit_row_number(hit)
        row = rows.get(row_no) if row_no is not None else None
        if row is None:
            enriched.append(hit)
            continue
        if row.seats == 0 and hit.seats > 0:
            continue
        final_seats = row.seats if row.seats is not None else hit.seats
        detail_parts = [f"No.{row.no}", row.region]
        if row.site_name:
            detail_parts.append(row.site_name)
        if row.address:
            detail_parts.append(row.address)
        if row.seats is not None:
            detail_parts.append(f"클립보드 {row.seats}석")
        if row.seats is None or row.seats != hit.seats:
            detail_parts.append(f"OCR {hit.seats}석")
        enriched.append(
            SeatHit(
                region=row.region,
                seats=final_seats,
                line=" - ".join(detail_parts),
                priority=row.no,
                no=row.no,
                site_name=row.site_name,
                address=row.address,
                source="clipboard+ocr",
            )
        )
    unique: dict[tuple[str, int, str], SeatHit] = {
        (hit.region, hit.seats, hit.line): hit for hit in enriched
    }
    return sorted(unique.values(), key=seat_hit_sort_key)


def parse_seat_hits(text: str) -> list[SeatHit]:
    normalized = normalize_text(text)
    hits: list[SeatHit] = []

    for raw_line in normalized.splitlines():
        line = raw_line.strip()
        if not line:
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
                priority=0,
            )
        )

    hits.sort(key=seat_hit_sort_key)
    return hits


def parse_table_like_hits(text: str) -> list[SeatHit]:
    normalized = normalize_text(text)
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    hits = parse_seat_hits(normalized)

    for index, line in enumerate(lines):
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
                    priority=0,
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
    return sorted(unique.values(), key=seat_hit_sort_key)
