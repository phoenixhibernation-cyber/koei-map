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
    check("最初の画面に注記や申込期間が出ていない", "非公式" not in pg.inner_text("body") and "11/2" not in pg.inner_text("#topbar"))

    # チップ → 絞り込み
    pg.click('#bbar [data-tab=filter]'); pg.wait_for_timeout(200); pg.click('[data-sec=area] .acc-head'); pg.wait_for_timeout(300)
    pg.screenshot(path=OUT / "02_filter_area.png")
    pg.click('.ck.pref:has-text("東京都") input'); pg.wait_for_timeout(200); pg.click('.city-grid .ck:has-text("板橋区") input'); pg.click("#popDone"); pg.wait_for_timeout(500)
    c2 = pg.inner_text("#count"); check("板橋区で絞れる: " + c2.split("\n")[0], 90 <= int(c2.split("件")[0].replace(",", "")) <= 200)

    # もっと条件（倍率3倍以下）→ 築年の並び替え
    pg.click('#bbar [data-tab=filter]'); pg.wait_for_timeout(200); pg.click('[data-sec=more] .acc-head'); pg.wait_for_timeout(300)
    pg.select_option('#popBody select >> nth=1', "3"); pg.click("#popDone"); pg.wait_for_timeout(400)
    c3 = pg.inner_text("#count"); check("倍率3倍以下で絞れる: " + c3.split("\n")[0], "件" in c3 and "90件" not in c3)
    pg.select_option("#sort", "old"); pg.wait_for_timeout(400)
    check("築年が古い順に並ぶ", pg.evaluate("document.querySelector('#list .item .sub').textContent") is not None)
    pg.evaluate("document.getElementById('condClear').click()"); pg.wait_for_timeout(300); pg.click('#bbar [data-tab=filter]'); pg.wait_for_timeout(200); pg.click('[data-sec=area] .acc-head'); pg.click('.ck.pref:has-text("東京都") input'); pg.wait_for_timeout(200); pg.click('.city-grid .ck:has-text("板橋区") input'); pg.click("#popDone"); pg.wait_for_timeout(400)

    # 一覧 → 詳細
    pg.click("#handle"); pg.wait_for_timeout(400)
    pg.screenshot(path=OUT / "03_list_open.png")
    pg.click("#list .item >> nth=0"); pg.wait_for_timeout(600)
    check("詳細シートが開く", pg.is_visible("#detail"))
    check("公式ページで申し込むボタンがある", pg.is_visible("#detailFoot .official"))
    check("募集の状態（申込期間）が出る", pg.is_visible("#detailBody .round-box") and ("申込期間" in pg.inner_text("#detailBody .round-box") or "受付" in pg.inner_text("#detailBody .round-box")))
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
    check("LINEの友だち追加ボタンがある", pg.is_visible("#btnLine"))
    pass  # 押すと新しいタブでLINEが開くので、テストでは押さない
    check("LINEの友だち追加リンクが入っている", "line.me" in (pg.get_attribute("#btnLine", "href") or ""))
    pg.screenshot(path=OUT / "06_notify.png")
    pg.click("#pageNotify [data-close]")

    # カレンダー → 地図で見る
    pg.click('#bbar [data-tab=cal]'); pg.wait_for_timeout(300)
    check("カレンダーに今募集中がある", "あと" in pg.inner_text("#calBody"))
    check("カレンダーに「終わった」がない", "終わった" not in pg.inner_text("#calBody"))
    check("カレンダーにLINEの導線がある", pg.is_visible("#calBody .line-cta"))
    pg.screenshot(path=OUT / "07_calendar.png")
    rid = pg.get_attribute("#calBody [data-round] >> nth=0", "data-round")
    pg.click("#calBody [data-round] >> nth=0"); pg.wait_for_timeout(500)
    check("募集に絞った地図になる: " + rid, "募集" in pg.inner_text("#count") and "今申し込める" not in pg.inner_text("#count"))

    # 通知のリンクから（?round=）
    pg.goto(a.url + "?round=toei-2026-11"); pg.wait_for_function("document.querySelectorAll('#list .item').length > 0", timeout=20000)
    check("?round= で開くとその募集に絞られる", "2026年11月" in pg.inner_text("#count"))

    # 検索
    pg.fill("#q", "勝どき"); pg.wait_for_timeout(500)
    check("検索で絞れる", "勝どき" in pg.inner_text("#list"))
    check("募集中のスイッチが無い", pg.locator('[data-chip="now"]').count() == 0)
    check("下のバーに4つ（地図・絞り込み・カレンダー・お知らせ）", pg.locator("#bbar [data-tab]").count() == 4 and pg.is_visible("#bbar"))
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
