import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[1]


async def main() -> int:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        await page.goto((ROOT / "pbcafe" / "index.html").resolve().as_uri(), wait_until="load")
        await page.wait_for_timeout(1000)
        result = await page.evaluate(
            """
            () => {
                const stores = window.DAMING_DATA?.storesPayload?.stores || [];
                const banqiao = stores.find((store) => store.storeId === 'pbcafe-022') || {};
                return {
                    stores: stores.length,
                    banqiaoLinks: (banqiao.gmbOrderLinks || []).map((link) => link.platform),
                    hasInstagramText: document.body.innerText.includes('Instagram'),
                    hasOrderLinksLabel: document.body.innerText.includes('點餐連結')
                };
            }
            """
        )
        await browser.close()

    ok = (
        not errors
        and result.get("stores") == 30
        and "Instagram" in (result.get("banqiaoLinks") or [])
        and result.get("hasInstagramText")
        and result.get("hasOrderLinksLabel")
    )
    print(json.dumps({"ok": ok, "errors": errors, "result": result}, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
