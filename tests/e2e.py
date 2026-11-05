#!/usr/bin/env python3
"""スマホ幅で主な流れを通して確かめる（Playwright）。
使い方: ~/Projects/toei-housing-map/.venv/bin/python tests/e2e.py [--url http://127.0.0.1:8777/]
スクリーンショットは tests/screenshots/ に保存。ブラウザのエラーがあれば終了コード1。
"""
import sys, pathlib, argparse
from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser(); ap.add_argument("--url", default="http://127.0.0.1:8777/"); a = ap.parse_args()
OUT = pathlib.Path(__file__).parent / "screenshots"; OUT.mkdir(exist_ok=True)
errors, fails = [], []

def check(name, cond):
    print(("OK " if cond else "NG ") + name)
    if not cond: fails.append(name)

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 390, "height": 780}, device_scale_factor=2, is_mobile=True, has_touch=True, locale="ja-JP")
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.goto(a.url + "?e2e=1"); pg.wait_for_function("document.querySelectorAll('#list .item').length > 0", timeout=20000)
    pg.wait_for_timeout(800)
    pg.screenshot(path=OUT / "01_home.png")
    count = pg.inner_text("#count")
    check("一覧に件数が出る: " + count.replace("\n", " "), "件" in count)
    check("最初の画面に注記や申込期間が出ていない", "非公式" not in pg.inner_text("body") and "11/2" not in pg.inner_text("#chips"))

    # チップ → 絞り込み
    pg.click('.chip[data-chip="area"]'); pg.wait_for_timeout(300)
    pg.screenshot(path=OUT / "02_filter_area.png")
    pg.click('.opt:has-text("板橋区")'); pg.click("#popDone"); pg.wait_for_timeout(500)
    c2 = pg.inner_text("#count"); check("板橋区で絞れる: " + c2.split("\n")[0], "90件" in c2)

    # 一覧 → 詳細
    pg.click("#handle"); pg.wait_for_timeout(400)
    pg.screenshot(path=OUT / "03_list_open.png")
    pg.click("#list .item >> nth=0"); pg.wait_for_timeout(600)
    check("詳細シートが開く", pg.is_visible("#detail"))
    check("公式ページで申し込むボタンがある", pg.is_visible("#detailFoot .official"))
    check("締切の日付が出る", "まで" in pg.inner_text("#detailBody"))
    pg.screenshot(path=OUT / "04_detail.png")
    href = pg.get_attribute("#detailFoot .official", "href"); check("公式リンクが to-kousya.or.jp", "to-kousya.or.jp" in (href or ""))
    pg.click("#detailClose"); pg.wait_for_timeout(300)

    # 公式から戻った体で、1回だけの案内
    pg.evaluate("localStorage.setItem('smiley:visitedOfficial', '1'); document.dispatchEvent(new Event('visibilitychange'))")
    pg.wait_for_timeout(200)
    check("戻ったときの案内が1回出る", pg.is_visible("#nudge"))
    pg.screenshot(path=OUT / "05_nudge.png")
    pg.click("#nudgeYes"); pg.wait_for_timeout(300)
    check("通知登録ページが開く", pg.is_visible("#pageNotify"))
    pg.fill("#mail", "test@example.com"); pg.click('#mailForm button[type="submit"]'); pg.wait_for_timeout(300)
    check("メール登録できる（端末内）", "登録しました" in pg.inner_text("#toast"))
    pg.screenshot(path=OUT / "06_notify.png")
    pg.click("#pageNotify [data-close]")

    # カレンダー → 地図で見る
    pg.click("#btnCal"); pg.wait_for_timeout(300)
    check("カレンダーに今募集中がある", "あと" in pg.inner_text("#calBody"))
    check("カレンダーに「終わった」がない", "終わった" not in pg.inner_text("#calBody"))
    pg.screenshot(path=OUT / "07_calendar.png")
    pg.click("#calBody [data-round] >> nth=0"); pg.wait_for_timeout(500)
    check("募集に絞った地図になる", "定期募集" in pg.inner_text("#count"))

    # 通知のリンクから（?round=）
    pg.goto(a.url + "?round=toei-2026-11"); pg.wait_for_function("document.querySelectorAll('#list .item').length > 0", timeout=20000)
    check("?round= で開くとその募集に絞られる", "2026年11月" in pg.inner_text("#count"))

    # 検索
    pg.fill("#q", "勝どき"); pg.wait_for_timeout(500)
    check("検索で絞れる", "勝どき" in pg.inner_text("#list"))
    pg.screenshot(path=OUT / "08_search.png")

    # パソコン幅
    ctx2 = b.new_context(viewport={"width": 1280, "height": 800}); pg2 = ctx2.new_page()
    pg2.on("pageerror", lambda e: errors.append(str(e)))
    pg2.goto(a.url + "?e2e=2"); pg2.wait_for_function("document.querySelectorAll('#list .item').length > 0", timeout=20000); pg2.wait_for_timeout(800)
    pg2.screenshot(path=OUT / "09_desktop.png")
    b.close()

print("\nブラウザのエラー:", len(errors)); [print("  ", e[:200]) for e in errors[:10]]
print("NG:", len(fails))
sys.exit(1 if errors or fails else 0)
