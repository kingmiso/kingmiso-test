import asyncio,json,datetime,traceback
from pathlib import Path
from playwright.async_api import async_playwright
from support import ROOT, HTML, launch_browser, TEST_HEADERS
BASE='http://economy-audit.invalid/'
NOW=datetime.datetime(2026,10,14,1,tzinfo=datetime.timezone.utc)
results=[]
async def main():
 async with async_playwright() as p:
  browser=await launch_browser(p)
  async def test(name,fn):
   ctx=await browser.new_context(service_workers='block');page=await ctx.new_page();errors=[]
   async def route(r):
    if r.request.url==BASE:await r.fulfill(status=200,content_type='text/html',body=HTML,headers=TEST_HEADERS)
    else:await r.abort()
   await ctx.route('**/*',route)
   page.on('pageerror',lambda e:errors.append(str(e)));page.on('dialog',lambda d:d.accept())
   await page.clock.install(time=NOW);await page.clock.pause_at(NOW)
   await page.goto(BASE,wait_until='domcontentloaded')
   await page.evaluate("window.currentCustomId='VIRTUAL_A';kmSaveEnabledV204=true;window.cloudSaveGame=()=>kmSaveLocalV204();playSfx=()=>{};")
   try:
    detail=await fn(page)
    assert not errors,errors
    results.append({'name':name,'status':'PASS','detail':detail})
   except Exception as e:results.append({'name':name,'status':'FAIL','error':str(e),'pageErrors':errors})
   print(results[-1],flush=True);await ctx.close()
  async def evaluate(page,code):return await page.evaluate(code)
  async def build(page):
   await page.evaluate("startBuildingUpgrade('farm')")
   await page.clock.run_for(1500)
   r=await page.evaluate("({level:BUILDINGS.farm.level,remaining:gameState.upgradesInProgress['building:farm'].endTime-Date.now(),rate:kmFacilityRate241('building','farm')})")
   assert r['level']==1 and r['remaining']==1500 and r['rate']==1
   await page.clock.run_for(1600)
   done=await page.evaluate("({level:BUILDINGS.farm.level,job:!!gameState.upgradesInProgress['building:farm'],rate:kmFacilityRate241('building','farm')})")
   assert done=={'level':2,'job':False,'rate':3};return {'during':r,'after':done}
  await test('normal_construction_start_progress_complete',build)
  async def unlock(page):
   r=await page.evaluate("()=>{const peers=HEROES.map((h,idx)=>({h,idx})).filter(x=>x.h.type==='infantry');const locked=!getHeroTierUnlockV196(peers,1).ok;HEROES[peers[0].idx].level=2;renderHeroes();return {locked,unlocked:getHeroTierUnlockV196(peers,1).ok,tier:getHighestUnlockedHeroTierV196(peers)}}")
   assert r=={'locked':True,'unlocked':True,'tier':1};return r
  await test('hero_tier_unlock',unlock)
  async def chat(page):
   r=await page.evaluate("()=>{const old=JSON.stringify(gameState);kmOpenChat238();const opened=!document.getElementById('km-chat-page').hidden;kmCloseChat238();return {opened,closed:document.getElementById('km-chat-page').hidden,stateSame:old===JSON.stringify(gameState)}}")
   assert all(r.values());return r
  await test('chat_navigation_without_server',chat)
  (ROOT/'supplement-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print('TOTAL',len(results),'PASS',sum(r['status']=='PASS' for r in results),flush=True)
  await browser.close()
asyncio.run(main())
raise SystemExit(1 if any(r['status']!='PASS' for r in results) else 0)
