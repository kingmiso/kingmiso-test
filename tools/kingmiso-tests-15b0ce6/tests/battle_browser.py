import asyncio,json,datetime
from playwright.async_api import async_playwright
from support import ROOT,HTML,TEST_HEADERS,launch_browser
BASE='http://battle-test.invalid/'
results=[]
async def main():
 async with async_playwright() as p:
  browser=await launch_browser(p)
  async def test(name,fn):
   ctx=await browser.new_context(service_workers='block');page=await ctx.new_page();errors=[]
   async def route(r):
    if r.request.url==BASE:await r.fulfill(status=200,content_type='text/html',body=HTML,headers=TEST_HEADERS)
    else:await r.abort()
   await ctx.route('**/*',route);page.on('pageerror',lambda e:errors.append(str(e)));page.on('dialog',lambda d:d.accept())
   now=datetime.datetime(2026,10,16,0,tzinfo=datetime.timezone.utc)
   await page.clock.install(time=now);await page.clock.pause_at(now)
   await page.goto(BASE,wait_until='domcontentloaded')
   await page.evaluate("window.currentCustomId='BATTLE_FAKE';kmSaveEnabledV204=true;window.cloudSaveGame=()=>kmSaveLocalV204();playSfx=()=>{};gameState.selectedSquad=[0];Object.assign(gameState.resources,{gold:10000,food:10000,herb:10000,magicDust:10000});window.originalRun=runBattleV12;runBattleV12=async()=>{};")
   try:
    detail=await fn(page);assert not errors,errors;results.append({'name':name,'status':'PASS','detail':detail})
   except Exception as e:results.append({'name':name,'status':'FAIL','error':str(e),'pageErrors':errors})
   print(results[-1],flush=True);await ctx.close()
  async def start(page,floor=1):
   await page.evaluate('(f)=>{gameState.towerFloor=f;startBattle()}',floor)
   if floor%5==0:await page.clock.run_for(2100)
   assert await page.evaluate('gameState.isBattling&&BATTLE_V12.running')
  for floor in [1,2,4,5,9,10]:
   async def transition(page,floor=floor):
    await start(page,floor)
    r=await page.evaluate("()=>{Math.random=()=>0;const old=gameState.resources.pureGold;BATTLE_V12.enemy.hp=0;updateBattleHpV12();finishBattleV12(true,BATTLE_V12.enemy);return {floor:gameState.towerFloor,delta:gameState.resources.pureGold-old,units:document.querySelectorAll('#battle-team-v12>*,#battle-enemy-v12>*').length,result:!!document.querySelector('.battle-result-v12'),log:document.getElementById('battle-log').textContent.includes('정복'),saved:kmLocalReadV204(currentCustomId).state.towerFloor}}")
    assert r=={'floor':floor+1,'delta':2 if floor%5==0 else 1,'units':0,'result':True,'log':True,'saved':floor+1};return r
   await test('transition_'+str(floor),transition)
  async def duplicate(page):
   await start(page)
   r=await page.evaluate("()=>{const save=window.cloudSaveGame;let calls=0;window.cloudSaveGame=()=>{calls++;save()};finishBattleV12(true);const once=JSON.stringify(gameState);for(let i=0;i<10;i++)finishBattleV12(true);finishBattleV12(false);return {same:once===JSON.stringify(gameState),calls,results:document.querySelectorAll('.battle-result-v12').length}}")
   assert r=={'same':True,'calls':1,'results':1};return r
  await test('duplicate_settlement',duplicate)
  async def stale(page):
   await start(page)
   r=await page.evaluate("()=>{const old=BATTLE_V12.enemy;finishBattleV12(true,old);startBattle();const before=JSON.stringify(gameState);finishBattleV12(true,old);return {same:before===JSON.stringify(gameState),running:BATTLE_V12.running}}")
   await page.clock.run_for(1200)
   assert r=={'same':True,'running':True}
   assert await page.evaluate("document.getElementById('battle-controls-box').classList.contains('battle-hidden-v121')");return r
  await test('stale_finish_and_controls',stale)
  async def defeat(page):
   await start(page)
   r=await page.evaluate("()=>{const old=gameState.resources.pureGold;finishBattleV12(false);const cleared=!document.getElementById('battle-enemy-v12').childElementCount;startBattle();return {floor:gameState.towerFloor,delta:gameState.resources.pureGold-old,cleared,hp:document.getElementById('enemy-hp-text-v12').textContent}}")
   assert r=={'floor':1,'delta':0,'cleared':True,'hp':'260 / 260'};return r
  await test('defeat_retry',defeat)
  async def spam(page):
   await page.evaluate('gameState.towerFloor=5;for(let i=0;i<10;i++)startBattle()');await page.clock.run_for(2100)
   r=await page.evaluate("()=>{for(let i=0;i<10;i++)startBattle();return {r:gameState.resources,c:getTowerEntryCosts(5)}}")
   assert all(r['r'][k]==10000-v for k,v in r['c'].items());return 'single charge'
  await test('boss_start_spam',spam)
  async def drift(page):
   await page.evaluate('gameState.towerFloor=5;startBattle();gameState.resources.food=0;window.before=JSON.stringify(gameState.resources)');await page.clock.run_for(2100)
   assert await page.evaluate('before===JSON.stringify(gameState.resources)&&!BATTLE_V12.running');return 'no partial debit'
  await test('boss_resource_drift',drift)
  async def reload(page):
   await start(page);await page.evaluate('finishBattleV12(true);window.saved=kmLocalReadV204(currentCustomId).state')
   saved=await page.evaluate('saved');await page.reload(wait_until='domcontentloaded')
   r=await page.evaluate("s=>{kmRestoreV204(s);finishBattleV12(true);return {floor:gameState.towerFloor,pureGold:gameState.resources.pureGold,units:document.getElementById('battle-enemy-v12').childElementCount}}",saved)
   assert r=={'floor':2,'pureGold':saved['resources']['pureGold'],'units':0};return r
  await test('reload_restore_no_reward_replay',reload)
  async def live_run(page):
   await page.evaluate('runBattleV12=window.originalRun;getHeroStats=()=>({hp:100000,atk:100000});startBattle()');await page.clock.run_for(5000)
   assert await page.evaluate('gameState.towerFloor===2&&!BATTLE_V12.running');return 'actual async loop completed'
  await test('actual_async_run',live_run)
  async def stale_attack(page):
   await start(page)
   await page.evaluate('window.attackPromise=heroAttackV12(BATTLE_V12.heroes[0],0);finishBattleV12(false);startBattle();window.newHP=BATTLE_V12.enemy.hp')
   await page.clock.run_for(500);await page.evaluate('window.attackPromise')
   assert await page.evaluate('BATTLE_V12.enemy.hp===newHP');return 'old attack ignored'
  await test('stale_attack_after_await',stale_attack)
  await browser.close()
 (ROOT/'battle-browser-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
 print('TOTAL',len(results),'PASS',sum(r['status']=='PASS' for r in results))
asyncio.run(main())
raise SystemExit(1 if any(r['status']!='PASS' for r in results) else 0)
