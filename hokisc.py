import re
import time
from collections import defaultdict
from playwright.sync_api import sync_playwright
import gspread
from google.oauth2.service_account import Credentials
import os
import json

# Daftar pasaran lengkap
markets = {
    "HKDW": "HOKI DRAW",
}

def extract_4digit_akhir(nomor):
    match = re.match(r"\d+", nomor)
    if match:
        return match.group(0)[-4:]
    return None

def extract_tanggal_jam(raw_datetime):
    match = re.match(r"(\d{4}-\d{2}-\d{2}) (\d{2}):", raw_datetime)
    if match:
        return match.group(1), match.group(2)
    return None, None

def extract_all_pages(page, pasaran_name, data, all_dates, max_pages):
    for page_number in range(1, max_pages + 1):
        print(f"[{pasaran_name}] Ambil halaman {page_number}")
        rows = page.locator("table tbody tr")
        count = rows.count()
        for i in range(count):
            row = rows.nth(i)
            raw_datetime = row.locator("td").nth(2).text_content().strip()
            nomor = row.locator("td").nth(3).text_content().strip()

            tanggal, jam = extract_tanggal_jam(raw_datetime)
            nomor_akhir = extract_4digit_akhir(nomor)

            if tanggal and jam and nomor_akhir:
                data[pasaran_name][jam][tanggal] = nomor_akhir
                all_dates.add(tanggal)

        try:
            next_btn = page.get_by_role("link", name="›")
            if next_btn.is_enabled():
                next_btn.click()
                page.wait_for_timeout(1500)
            else:
                break
        except:
            break

def upload_to_sheet(sheet_name, data_dict, sorted_dates):
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if not creds_json:
        raise ValueError("GOOGLE_CREDENTIALS_JSON not found in environment variables")

    info = json.loads(creds_json)
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(info, scopes=scope)
    client = gspread.authorize(creds)

    sheet = client.open(sheet_name)
    worksheet_title = "HOKI 4D"

    try:
        worksheet = sheet.worksheet(worksheet_title)
    except:
        worksheet = sheet.add_worksheet(title=worksheet_title, rows="100", cols="100")

    header = worksheet.row_values(1)
    if not header:
        header = ["JAM"]

    header_dates = header[1:]
    for tanggal in sorted_dates:
        if tanggal not in header_dates:
            header.append(tanggal)
    worksheet.update(values=[header], range_name="A1")

    jam_rows = worksheet.col_values(1)[1:]
    jam_map = {jam.zfill(2): i + 2 for i, jam in enumerate(jam_rows)}

    for jam, tanggal_data in data_dict.items():
        jam_str = jam.zfill(2)
        row_idx = jam_map.get(jam_str)

        if not row_idx:
            worksheet.append_row([jam_str] + [""] * (len(header) - 1))
            row_idx = worksheet.row_count

        row_values = worksheet.row_values(row_idx)
        if len(row_values) < len(header):
            row_values += [""] * (len(header) - len(row_values))

        for tanggal in sorted_dates:
            col_idx = header.index(tanggal)
            if not row_values[col_idx]:
                value = tanggal_data.get(tanggal, "")
                if value:
                    row_values[col_idx] = value

        worksheet.update(values=[row_values], range_name=f"A{row_idx}")

def scrape(selected_codes, max_pages):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(java_script_enabled=True, bypass_csp=True)
        context.route("**/*", lambda route, request: route.abort() if request.resource_type == "image" else route.continue_())
        page = context.new_page()
        page.goto("https://depobos80993.com/#/index?category=lottery")
        page.get_by_role("img", name="close").click()

        with page.expect_popup() as popup_info:
            page.get_by_role("img", name="MAGNUM4D").click()
        page1 = popup_info.value

        page1.get_by_role("textbox", name="-14 digit atau kombinasi huruf").fill("babikecilku")
        page1.get_by_role("textbox", name="-16 angka atau kombinasi huruf").fill("Basokikil6")
        page1.get_by_text("Masuk").click()
        page1.get_by_role("link", name="Saya Setuju").click()
        time.sleep(3)
        page1.get_by_role("link", name="NOMOR HISTORY NOMOR").click()
        page1.wait_for_timeout(1500)

        data = defaultdict(lambda: defaultdict(lambda: defaultdict(str)))
        all_dates = set()

        for code in selected_codes:
            pasaran_name = markets[code]
            page1.locator("#marketSelect").select_option(code)
            page1.wait_for_timeout(1500)
            extract_all_pages(page1, pasaran_name, data, all_dates, max_pages)

        sorted_dates = sorted(all_dates, reverse=True)
        for code in selected_codes:
            pasaran_name = markets[code]
            upload_to_sheet("DATA HOKI", data[pasaran_name], sorted_dates)

        context.close()
        browser.close()
        print("\n✅ Semua data berhasil disimpan ke Google Spreadsheet")

if __name__ == "__main__":
    selected_codes = list(markets.keys())
    max_pages = 1
    scrape(selected_codes, max_pages)
