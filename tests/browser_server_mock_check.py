"""Browser smoke test of NAS mode with mocked fetch (real HTTP separately tested in test_app.py)."""
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
html=(ROOT/'web/index.html').read_text().replace("const SERVER_MODE=location.protocol==='http:'||location.protocol==='https:'",'const SERVER_MODE=true')
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1440,'height':900})
    page.set_default_timeout(3500)
    errs=[]
    page.on('pageerror',lambda e:errs.append(str(e)))
    page.goto('about:blank')
    page.evaluate('''() => {
      for(const key of ['sessionStorage','localStorage']){
        Object.defineProperty(window,key,{configurable:true,value:{data:{},getItem(k){return this.data[k]??null},setItem(k,v){this.data[k]=v},removeItem(k){delete this.data[k]}}});
      }
      window.__testServer={revision:0,state:{version:2,subscriptions:[],transactions:[],wallets:[],settings:{budget:500,rates:{CNY:1,USD:7,JPY:0.05,EUR:7.5,HKD:0.9}}}};
      window.fetch=async(url,init={})=>{
        const db=window.__testServer;
        if(!init.headers || init.headers.Authorization!=='Bearer test-token-nas-1234567890')return new Response(JSON.stringify({error:'Unauthorized'}),{status:401});
        if(init.method==='PUT'){
          const body=JSON.parse(init.body);
          if(body.revision!==db.revision)return new Response(JSON.stringify({error:'conflict'}),{status:409});
          db.state=body.state;db.revision++;
          return new Response(JSON.stringify({revision:db.revision}),{status:200});
        }
        return new Response(JSON.stringify(db),{status:200});
      };
    }''')
    page.set_content(html)
    assert page.locator('#loginDialog').evaluate('(e)=>e.open')
    assert page.locator('#addSub').is_disabled()
    page.locator('#accessToken').fill('test-token-nas-1234567890')
    page.get_by_role('button',name='连接服务器').click()
    page.locator('#connectionStatus').get_by_text('NAS 已连接').wait_for()
    page.locator('#addSub').click()
    page.locator('#f-provider').fill('ChatGPT')
    page.locator('#f-amount').fill('20')
    page.locator('#f-next').fill('2026-10-20')
    page.locator('#editorForm button[type=submit]').click()
    page.locator('#editor').wait_for(state='hidden')
    assert page.evaluate('window.__testServer.revision')==1
    assert page.evaluate('window.__testServer.state.subscriptions[0].provider')=='ChatGPT'
    page.locator('#addTx').click()
    page.locator('#f-provider').fill('ChatGPT')
    page.locator('#f-amount').fill('20')
    page.locator('#f-date').fill('2026-10-09')
    page.locator('#editorForm button[type=submit]').click()
    page.locator('#editor').wait_for(state='hidden')
    assert page.evaluate('window.__testServer.revision')==2
    assert page.evaluate('window.__testServer.state.transactions.length')==1
    assert not errs,errs
    page.screenshot(path=str(ROOT/'ui-preview.png'),full_page=True)
    print('BROWSER MOCK SERVER MODE PASS: login, save 2 items, revision increments, no page JS errors')
    browser.close()
