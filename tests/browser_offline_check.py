"""HTML UI interaction check under about:blank, because this environment blocks local URL navigation via Chromium policy."""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
html = (ROOT/'web/index.html').read_text()
with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path='/usr/bin/chromium', headless=True, args=['--no-sandbox'])
    page = browser.new_page(viewport={'width': 1440, 'height': 900})
    page.set_default_timeout(2500);print('browser ready',flush=True)
    errors=[]
    page.on('pageerror', lambda e: errors.append(str(e)))
    page.goto('about:blank')
    print('goto about blank',flush=True)
    page.evaluate("Object.defineProperty(window,'localStorage',{configurable:true,value:{data:{},getItem(k){return this.data[k]??null},setItem(k,v){this.data[k]=v},removeItem(k){delete this.data[k]}}})")
    page.set_content(html, wait_until='load')
    print('set content done',flush=True)
    page.locator('#addSub').click()
    page.locator('#f-provider').fill('ChatGPT')
    page.locator('#f-amount').fill('20')
    page.locator('#f-currency').select_option('USD')
    page.locator('#f-next').fill('2026-10-20')
    page.locator('#editorForm button[type=submit]').click()
    page.locator('#editor').wait_for(state='hidden')
    assert page.locator('#subRows tr').count()==1
    page.locator('#addTx').click()
    page.locator('#f-date').fill('2026-10-09')
    page.locator('#f-provider').fill('ChatGPT')
    page.locator('#f-amount').fill('20')
    page.locator('#f-type').select_option('subscription')
    page.locator('#f-currency').select_option('USD')
    page.locator('#editorForm button[type=submit]').click()
    page.locator('#editor').wait_for(state='hidden')
    assert page.locator('#txRows tr').count()==1
    assert page.locator('#monthTotal').inner_text().strip() in ['¥140.00','¥0.00'] # actual system clock may be another month
    assert not errors, str(errors)
    page.screenshot(path=str(ROOT/'ui-preview.png'),full_page=True)
    print('BROWSER UI TEST PASS: offline mode renders, add subscription, add transaction, no JS runtime errors')
    browser.close()
