import unittest

import adsp_popup_ocr_watcher as watcher
from adsp_seat_parser import clipboard_rows_to_hits, parse_clipboard_rows, parse_table_like_hits


SCREENSHOT_TABLE_TSV = """No.\t지역\t고사장명\t주소\t엘리베이터 운영 여부\t잔여좌석\t지도
1\t서울특별시\tADsP (서울) 성동공업고등학교\t서울 중구 다산로 290 성동공업고등학교\t운영\t0\t보기
15\t서울특별시\tADsP (서울) 문현중학교\t서울 송파구 충민로 99 문현중학교\t운영\t0\t보기
30\t서울특별시\tADsP (서울) 용강중학교\t서울 용산구 이촌로65가길 91 용강중학교\t운영\t12\t보기
34\t서울특별시\tADsP (서울) 천일중학교\t서울 강동구 천중로 57 천일중학교\t운영\t1\t보기
38\t경기도\tADsP (경기) 경일고등학교\t경기 안산시 단원구 석수로 131 경일고등학교\t미운영\t7\t보기
40\t경기도\tADsP (경기) 동남보건대학교 사담기념관, 동남관\t경기 수원시 장안구 천천로74번길 50 동남보건대학교 사담기념관, 동남관\t운영\t1\t보기
59\t대구광역시\tADsP (대구) 대구가톨릭대학교 종합강의동, 교양관\t경북 경산시 하양읍 하양로 13-13 대구가톨릭대학교 종합강의동, 교양관\t운영\t53\t보기
61\t대구광역시\tADsP (대구) 왕선중학교\t대구 달성군 다사읍 대실역북로 83 왕선중학교\t운영\t1\t보기
63\t부산광역시\tADsP (부산) 경성대학교 건학기념관\t부산 남구 수영로 309 경성대학교 건학기념관\t운영\t7\t보기
66\t부산광역시\tADsP (부산) 물금동아중학교\t경남 양산시 물금읍 청운로 46 물금동아중학교\t미운영\t5\t보기
71\t광주광역시\tADsP (광주) 동성중학교\t광주 남구 서문대로627번길 20 광주동성중학교\t미운영\t1\t보기
75\t광주광역시\tADsP (광주) 광주화정중학교\t전남광주통합특별시 서구 화운로 53 광주화정중학교\t운영\t307\t보기
77\t울산광역시\tADsP (울산) 신일중학교\t울산 남구 두왕로 278 신일중학교\t운영\t287\t보기
79\t강원도\tADsP (강원) 한림대학교 기초교육관\t강원특별자치도 춘천시 한림대학길 1 한림대학교 기초교육관\t운영\t91\t보기
80\t제주도\tADsP (제주) 제주대학교 (아라캠퍼스 교양강의동)\t제주특별자치도 제주시 제주대학로 102 제주대학교 (아라캠퍼스 교양강의동)\t운영\t9\t보기
"""


EXPECTED_POSITIVES = {
    30: ("서울특별시", "ADsP (서울) 용강중학교", "서울 용산구 이촌로65가길 91 용강중학교", 12),
    34: ("서울특별시", "ADsP (서울) 천일중학교", "서울 강동구 천중로 57 천일중학교", 1),
    38: ("경기도", "ADsP (경기) 경일고등학교", "경기 안산시 단원구 석수로 131 경일고등학교", 7),
    40: ("경기도", "ADsP (경기) 동남보건대학교 사담기념관, 동남관", "경기 수원시 장안구 천천로74번길 50 동남보건대학교 사담기념관, 동남관", 1),
    59: ("대구광역시", "ADsP (대구) 대구가톨릭대학교 종합강의동, 교양관", "경북 경산시 하양읍 하양로 13-13 대구가톨릭대학교 종합강의동, 교양관", 53),
    61: ("대구광역시", "ADsP (대구) 왕선중학교", "대구 달성군 다사읍 대실역북로 83 왕선중학교", 1),
    63: ("부산광역시", "ADsP (부산) 경성대학교 건학기념관", "부산 남구 수영로 309 경성대학교 건학기념관", 7),
    66: ("부산광역시", "ADsP (부산) 물금동아중학교", "경남 양산시 물금읍 청운로 46 물금동아중학교", 5),
    71: ("광주광역시", "ADsP (광주) 동성중학교", "광주 남구 서문대로627번길 20 광주동성중학교", 1),
    75: ("광주광역시", "ADsP (광주) 광주화정중학교", "전남광주통합특별시 서구 화운로 53 광주화정중학교", 307),
    77: ("울산광역시", "ADsP (울산) 신일중학교", "울산 남구 두왕로 278 신일중학교", 287),
    79: ("강원도", "ADsP (강원) 한림대학교 기초교육관", "강원특별자치도 춘천시 한림대학길 1 한림대학교 기초교육관", 91),
    80: ("제주도", "ADsP (제주) 제주대학교 (아라캠퍼스 교양강의동)", "제주특별자치도 제주시 제주대학로 102 제주대학교 (아라캠퍼스 교양강의동)", 9),
}


class ClipboardRegressionTest(unittest.TestCase):
    def test_parse_exact_rows_from_user_screenshots(self):
        rows = parse_clipboard_rows(SCREENSHOT_TABLE_TSV)

        for no, expected in EXPECTED_POSITIVES.items():
            with self.subTest(no=no):
                row = rows[no]
                self.assertEqual((row.region, row.site_name, row.address, row.seats), expected)

    def test_alert_hits_include_all_positive_rows_without_region_filter(self):
        hits = clipboard_rows_to_hits(SCREENSHOT_TABLE_TSV)
        hit_by_no = {hit.no: hit for hit in hits}

        self.assertEqual(set(hit_by_no), set(EXPECTED_POSITIVES))

        for no, (region, site_name, address, seats) in EXPECTED_POSITIVES.items():
            with self.subTest(no=no):
                hit = hit_by_no[no]
                self.assertEqual(hit.region, region)
                self.assertEqual(hit.seats, seats)
                self.assertIn(site_name, hit.line)
                self.assertIn(address, hit.line)

    def test_scan_pages_prefers_clipboard_rows_over_ocr_noise(self):
        original_screenshot_text = watcher.screenshot_text
        original_screenshot_digits = watcher.screenshot_digits
        try:
            watcher.screenshot_text = lambda *args, **kwargs: "30 broken ADSP text 999\n75 broken ADSP text 777"
            watcher.screenshot_digits = lambda *args, **kwargs: "307\n287\n91\n0"

            _text, hits = watcher.scan_pages(
                bbox=None,
                lang="kor+eng",
                pages=1,
                page_wait=0,
                focus_click=None,
                scroll_method="wheel",
                wheel_notches=0,
                ocr_scale=1,
                ocr_contrast=1,
                seat_bbox=(0, 0, 10, 10),
                clipboard_provider=lambda _page: SCREENSHOT_TABLE_TSV,
            )
        finally:
            watcher.screenshot_text = original_screenshot_text
            watcher.screenshot_digits = original_screenshot_digits

        hit_by_no = {hit.no: hit for hit in hits}
        self.assertEqual(set(hit_by_no), set(EXPECTED_POSITIVES))
        self.assertEqual(hit_by_no[75].seats, 307)
        self.assertEqual(hit_by_no[77].seats, 287)
        self.assertEqual(hit_by_no[79].seats, 91)
        self.assertTrue(all(not hit.region.startswith("OCR") for hit in hits))

    def test_clipboard_table_suppresses_ocr_noise_across_cycle(self):
        originals = {
            "screenshot_text": watcher.screenshot_text,
            "screenshot_digits": watcher.screenshot_digits,
            "click_point": watcher.click_point,
            "press_ctrl_home": watcher.press_ctrl_home,
            "scroll_wheel": watcher.scroll_wheel,
            "press_key": watcher.press_key,
            "sleep": watcher.time.sleep,
        }
        try:
            watcher.screenshot_text = lambda *args, **kwargs: "5 eS ADSP noisy row 24"
            watcher.screenshot_digits = lambda *args, **kwargs: "53\n1\n1\n1"
            watcher.click_point = lambda *args, **kwargs: None
            watcher.press_ctrl_home = lambda *args, **kwargs: None
            watcher.scroll_wheel = lambda *args, **kwargs: None
            watcher.press_key = lambda *args, **kwargs: None
            watcher.time.sleep = lambda *args, **kwargs: None

            _text, hits = watcher.scan_pages(
                bbox=None,
                lang="kor+eng",
                pages=2,
                page_wait=0,
                focus_click=None,
                scroll_method="wheel",
                wheel_notches=0,
                ocr_scale=1,
                ocr_contrast=1,
                seat_bbox=(0, 0, 10, 10),
                clipboard_provider=lambda page: SCREENSHOT_TABLE_TSV if page == 1 else "",
            )
        finally:
            watcher.screenshot_text = originals["screenshot_text"]
            watcher.screenshot_digits = originals["screenshot_digits"]
            watcher.click_point = originals["click_point"]
            watcher.press_ctrl_home = originals["press_ctrl_home"]
            watcher.scroll_wheel = originals["scroll_wheel"]
            watcher.press_key = originals["press_key"]
            watcher.time.sleep = originals["sleep"]

        self.assertTrue(hits)
        self.assertTrue(all(hit.line.startswith("No.") for hit in hits))
        self.assertTrue(all(not hit.region.startswith("OCR") for hit in hits))
        self.assertTrue({80, 79, 77, 75}.issubset({hit.no for hit in hits}))

    def test_hits_keep_table_number_order(self):
        hits = clipboard_rows_to_hits(SCREENSHOT_TABLE_TSV)
        hit_numbers = [hit.no for hit in hits]
        self.assertEqual(hit_numbers, sorted(hit_numbers))
        self.assertEqual(hit_numbers[:4], [30, 34, 38, 40])

    def test_auto_copy_failure_does_not_reuse_stale_clipboard(self):
        originals = {
            "click_point": watcher.click_point,
            "set_clipboard_text": watcher.set_clipboard_text,
            "press_ctrl_key": watcher.press_ctrl_key,
            "read_clipboard_text": watcher.read_clipboard_text,
            "sleep": watcher.time.sleep,
        }
        sentinel_holder = {"value": ""}
        try:
            watcher.click_point = lambda *args, **kwargs: None
            watcher.set_clipboard_text = lambda value: sentinel_holder.update(value=value)
            watcher.press_ctrl_key = lambda *args, **kwargs: None
            watcher.read_clipboard_text = lambda: sentinel_holder["value"]
            watcher.time.sleep = lambda *args, **kwargs: None

            copied = watcher.copy_active_window_text(None)
        finally:
            watcher.click_point = originals["click_point"]
            watcher.set_clipboard_text = originals["set_clipboard_text"]
            watcher.press_ctrl_key = originals["press_ctrl_key"]
            watcher.read_clipboard_text = originals["read_clipboard_text"]
            watcher.time.sleep = originals["sleep"]

        self.assertEqual(copied, "")

    def test_ocr_path_has_no_region_exclusion(self):
        hits = parse_table_like_hits("제주도 ADsP (제주) 제주대학교 잔여좌석 : 2")
        self.assertTrue(any(hit.region == "제주도" and hit.seats == 2 for hit in hits))

    def test_parser_accepts_other_dataq_exam_codes(self):
        text = """No.\t지역\t고사장명\t주소\t엘리베이터 운영 여부\t잔여좌석\t지도
12\t서울특별시\tSQLD (서울) 테스트고등학교\t서울 강남구 테스트로 12 테스트고등학교\t운영\t3\t보기
"""
        hits = clipboard_rows_to_hits(text)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].site_name, "SQLD (서울) 테스트고등학교")
        self.assertEqual(hits[0].seats, 3)

        ocr_hits = parse_table_like_hits("12 SQLD (서울) 테스트고등학교 잔여좌석 3")
        self.assertTrue(any(hit.no == 12 and hit.seats == 3 for hit in ocr_hits))


if __name__ == "__main__":
    unittest.main()
