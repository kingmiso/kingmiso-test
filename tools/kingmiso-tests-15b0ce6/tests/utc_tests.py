import asyncio,json,datetime
from pathlib import Path
from playwright.async_api import async_playwright
from support import ROOT, HTML, launch_browser, TEST_HEADERS
results=[]
def dt(s):return datetime.datetime.fromisoformat(s.replace('Z','+00:00'))
async def main():
 async with async_playwright() as p:
  b=await launch_browser(p)
  async def case(name,zone,fn):
   c=await b.new_context(timezone_id=zone,service_workers='block');page=await c.new_page();errors=[]
   async def route(r):
    if r.request.url=='http://utc.invalid/':await r.fulfill(status=200,content_type='text/html',body=HTML,headers=TEST_HEADERS)
    else:await r.abort()
   await c.route('**/*',route);page.on('pageerror',lambda e:errors.append(str(e)));page.on('dialog',lambda d:d.accept())
   await page.clock.install(time=dt('2026-10-14T23:59:59Z'));await page.clock.pause_at(dt('2026-10-14T23:59:59Z'))
   await page.goto('http://utc.invalid/',wait_until='domcontentloaded')
   await page.evaluate("currentCustomId='UTC_FAKE';kmSaveEnabledV204=true;cloudSaveGame=()=>kmSaveLocalV204();playSfx=()=>{};")
   try:
    r=await fn(page);assert not errors,errors;results.append({'name':name,'zone':zone,'status':'PASS','detail':r})
   except Exception as e:results.append({'name':name,'zone':zone,'status':'FAIL','error':str(e),'pageErrors':errors})
   print(results[-1],flush=True);await c.close()
  async def boundary(page):
   await page.evaluate("gameState.roulette={countToday:3,lastSpinTime:Date.now()-7200000,dayKey:'2026-10-15'};openRouletteModal();kmUpdateUTCClock()")
   before=await page.evaluate("({day:gameState.roulette.dayKey,count:gameState.roulette.countToday,clock:document.getElementById('km-utc-clock').textContent,reset:document.getElementById('km-roulette-reset').textContent,button:document.getElementById('btn-spin-roulette').textContent})")
   assert before['count']==3 and before['day']=='2026-10-14' and before['clock']=='UTC 23:59:59' and before['reset']=='00:00:01' and '00:00 UTC' in before['button'],before
   await page.clock.run_for(1000)
   after=await page.evaluate("({day:gameState.roulette.dayKey,count:gameState.roulette.countToday,clock:document.getElementById('km-utc-clock').textContent,date:document.getElementById('km-utc-clock').dateTime,hour:new Date().getHours(),minute:new Date().getMinutes(),reset:document.getElementById('km-roulette-reset').textContent,disabled:document.getElementById('btn-spin-roulette').disabled})")
   assert after['count']==0 and after['day']=='2026-10-15' and after['clock']=='UTC 00:00:00' and after['date'].startswith('2026-10-15') and not after['disabled'],after
   return {'before':before,'after':after}
  async def cooldown(page):
   await page.evaluate("gameState.roulette={countToday:3,lastSpinTime:Date.now()-9000,dayKey:'2026-10-15'};openRouletteModal()")
   await page.clock.run_for(2000)
   r=await page.evaluate("({status:kmRouletteStatus(),display:document.getElementById('km-roulette-wait').textContent,disabled:document.getElementById('btn-spin-roulette').disabled})")
   assert r['status']['left']==3 and r['status']['wait']==3589000 and r['display']=='00:59:49' and r['disabled'];return r
  async def kst_boundary(page):
   await page.clock.set_system_time(dt('2026-10-14T14:59:59Z'))
   await page.evaluate("gameState.roulette={countToday:3,lastSpinTime:Date.now()-7200000,dayKey:'2026-10-14'};openRouletteModal()")
   await page.clock.run_for(2000)
   r=await page.evaluate('kmRouletteStatus()');assert r['left']==0 and r['r']['dayKey']=='2026-10-14';return r
  async def migration(page):
   await page.clock.set_system_time(dt('2026-10-14T18:00:00Z'))
   r=await page.evaluate("""()=>{gameState.resources.gem=321;gameState.roulette={countToday:2,lastSpinTime:Date.parse('2026-10-14T16:00:00Z'),dayKey:'2026-10-15',cooldownMs:3600000};const oldTime=gameState.roulette.lastSpinTime;const first={...kmRouletteStatus().r};for(let i=0;i<10;i++)kmRouletteStatus();kmLocalWriteV204(currentCustomId);kmRestoreV204(kmLocalReadV204(currentCustomId).state);const again=kmRouletteStatus();return {first,again,gem:gameState.resources.gem,oldTime}}""")
   assert r['first']['dayKey']=='2026-10-14' and r['again']['r']['countToday']==2 and r['gem']==321 and r['again']['r']['lastSpinTime']==r['oldTime'];return r
  for zone,hour in [('UTC',0),('Asia/Bangkok',7),('Asia/Seoul',9),('America/Los_Angeles',17)]:
   async def bound(page,hour=hour):
    r=await boundary(page);assert r['after']['hour']==hour and r['after']['minute']==0;return r
   for name,fn in [('utc_midnight_local_hour',bound),('midnight_preserves_wait',cooldown),('old_kst_midnight_no_reset',kst_boundary),('kst_save_utc_restore_no_extra_use',migration)]:await case(name,zone,fn)
  async def missing(page):
   r=await page.evaluate("""()=>{const out=[];for(const state of [{countToday:2,lastSpinTime:0},{countToday:2,lastSpinTime:Date.now()-1000},{countToday:0,lastSpinTime:Date.now()-1000,dayKey:'2026-10-15'}]){gameState.roulette=state;out.push(JSON.parse(JSON.stringify(kmRouletteStatus())));}return out}""")
   assert [x['left'] for x in r]==[1,1,3] and all(x['r']['dayKey']=='2026-10-14' for x in r);return r
  await case('legacy_missing_key_timestamp_and_empty_day','UTC',missing)
  async def timer(page):
   await page.evaluate("window.renderCount=0;window.realUpdate=updateUI;updateUI=()=>{renderCount++;realUpdate()};window.clockCalls=0;window.origClock=kmRenderUTCTime;kmRenderUTCTime=(id,now)=>{if(id==='km-utc-clock')clockCalls++;origClock(id,now)};for(let i=0;i<10;i++){kmUpdateUTCClock();document.dispatchEvent(new Event('visibilitychange'));}clockCalls=0;")
   await page.clock.run_for(3000)
   r=await page.evaluate("({calls:clockCalls,renders:renderCount,text:document.getElementById('km-utc-clock').textContent})");assert r=={'calls':3,'renders':0,'text':'UTC 00:00:02'};return r
  await case('clock_single_timer_and_no_game_rerender','Asia/Bangkok',timer)
  async def production(page):
   await page.evaluate("kmLastResourceTickV202=Date.now();startBuildingUpgrade('farm');window.beforeFood=gameState.resources.food;window.prod=setInterval(productionTickV201,100)")
   await page.clock.run_for(4000)
   r=await page.evaluate("({level:BUILDINGS.farm.level,job:!!gameState.upgradesInProgress['building:farm'],food:gameState.resources.food-beforeFood,clock:document.getElementById('km-utc-clock').textContent})")
   assert r['level']==2 and not r['job'] and r['food']>=5.8 and r['food']<=6.3 and r['clock']=='UTC 00:00:03',r;return r
  await case('clock_with_online_production_and_construction','Asia/Seoul',production)
  async def rollback(page):
   await page.evaluate("gameState.roulette={countToday:3,lastSpinTime:Date.now()+3600000,dayKey:'2026-10-15'}")
   r=await page.evaluate('kmRouletteStatus()');assert r['left']==0 and r['wait']==7200000;return r
  await case('backward_clock_retains_restriction','UTC',rollback)
  await b.close()
 (ROOT/'utc-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print('TOTAL',len(results),'PASS',sum(r['status']=='PASS' for r in results))
asyncio.run(main())
raise SystemExit(1 if any(r['status']!='PASS' for r in results) else 0)
