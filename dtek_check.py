#!/usr/bin/env python3
"""Версія для GitHub Actions (Linux, Selenium). Назва файла в репо: dtek_check.py

Env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID  (з GitHub Secrets)
  python dtek_check.py            -> надсилає в Telegram
  python dtek_check.py --dry-run  -> лише друкує
"""
import json
import os
import re
import sys
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

PAGE_URL = "https://www.dtek-dnem.com.ua/ua/shutdowns"
CITY = ("Дніпро", "м. Дніпро")
STREET = ("Калинова", "вул. Калинова")
HOUSE = ("53", "53")

UP = "АБВГҐДЕЄЖЗИІЇЙКЛМНОПРСТУФХЦЧШЩЬЮЯ"
LOW = "абвгґдеєжзиіїйклмнопрстуфхцчшщьюя"


def pick(d, wait, field_id, text, option):
    el = d.find_element(By.ID, field_id)
    el.click()
    el.clear()
    for ch in text:
        el.send_keys(ch)
        time.sleep(0.08)
    # текст у списку малими літерами (великі лише через CSS) -> порівнюємо без регістру
    xp = ("//div[contains(@class,'autocomplete-items')]/div"
          f"[translate(normalize-space(.),'{UP}','{LOW}')='{option.lower()}']")
    try:
        opt = wait.until(EC.element_to_be_clickable((By.XPATH, xp)))
    except Exception:
        print("DEBUG список:", d.execute_script(
            "return [...document.querySelectorAll('.autocomplete-items div')]"
            ".slice(0,8).map(e=>e.textContent.trim())"))
        print("DEBUG сторінка:", d.page_source[:400].replace("\n", " "))
        raise
    opt.click()


def ranges(cells):
    off = []
    for h, c in enumerate(cells):
        if "non-scheduled" in c:
            continue
        if "first-half" in c:
            off.append([h * 60, h * 60 + 30])
        elif "second-half" in c:
            off.append([h * 60 + 30, h * 60 + 60])
        elif "scheduled" in c:
            off.append([h * 60, h * 60 + 60])
    merged = []
    for s, e in off:
        if merged and merged[-1][1] == s:
            merged[-1][1] = e
        else:
            merged.append([s, e])
    f = lambda m: f"{m // 60:02d}:{m % 60:02d}"
    return [f"{f(s)}–{f(e)}" for s, e in merged]


def scrape():
    opts = webdriver.ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1280,1000")
    opts.add_argument("--lang=uk-UA")
    d = webdriver.Chrome(options=opts)
    try:
        wait = WebDriverWait(d, 20)
        d.get(PAGE_URL)
        wait.until(EC.presence_of_element_located((By.ID, "city")))
        time.sleep(2)
        for b in d.find_elements(By.CSS_SELECTOR, "button[aria-label='Close modal']"):
            if b.is_displayed():
                b.click()
        pick(d, wait, "city", *CITY)
        time.sleep(2)
        pick(d, wait, "street", *STREET)
        time.sleep(2)
        pick(d, wait, "house_num", *HOUSE)
        wait.until(EC.visibility_of_element_located((By.ID, "discon-fact")))
        time.sleep(1.5)

        status = d.find_element(By.ID, "showCurOutage").text.strip()
        m = re.search(r"Черга \d+\.\d+", d.find_element(By.TAG_NAME, "body").text)
        queue = m.group(0) if m else ""

        days = []
        n = len(d.find_elements(By.CSS_SELECTOR, ".dates .date"))
        for i in range(n):
            el = d.find_elements(By.CSS_SELECTOR, ".dates .date")[i]
            label = " ".join(el.text.split())
            d.execute_script("arguments[0].click()", el)
            time.sleep(0.7)
            tables = d.find_elements(By.CSS_SELECTOR, ".discon-fact-table")
            t = tables[i] if len(tables) > i else tables[0]
            cells = [td.get_attribute("class") or ""
                     for td in t.find_elements(By.CSS_SELECTOR, "tbody td")][-24:]
            days.append((label, ranges(cells)))
        return queue, status, days
    finally:
        d.quit()


def main():
    queue, status, days = scrape()
    lines = [f"⚡ ДТЕК: Дніпро, вул. Калинова, 53 ({queue})", "", status]
    for label, off in days:
        lines += ["", f"📅 {label}:", "🔌 Без світла: " + (", ".join(off) or "відключень немає")]
    msg = "\n".join(lines)
    print(msg)
    if "--dry-run" not in sys.argv:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/sendMessage",
            json.dumps({"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": msg}).encode(),
            {"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=30).read()


if __name__ == "__main__":
    main()
