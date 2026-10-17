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
  async def donation(page):
   r=await page.evaluate("()=>{const old=JSON.stringify(gameState.resources);for(let i=0;i<10;i++)completeDonationReward();return {same:old===JSON.stringify(gameState.resources),item:SHOP_ITEMS.find(i=>i.id==='buy_cash_gem')}}")
   assert r['same'] and '100' not in r['item']['desc'];return r
  await test('donation_10_calls_preserve_all_balances',donation)
  async def invalid(page):
   r=await page.evaluate("""()=>{const old=JSON.stringify(gameState.resources),bad=[-1,NaN,Infinity,-Infinity,'5',null,undefined,{},[]];const failures=bad.every(a=>!spendResource('gem',a)&&!addResource('gem',a));const keys=['unknown','__proto__','constructor',null,5];return {failures,keys:keys.every(k=>!spendResource(k,1)&&!addResource(k,1)),same:old===JSON.stringify(gameState.resources),zero:spendResource('gem',0)&&addResource('gem',0)}}""")
   assert all(r.values());return r
  await test('invalid_amounts_keys_and_zero_compatibility',invalid)
  async def batch(page):
   r=await page.evaluate("()=>{const old=JSON.stringify(gameState.resources);return {denied:!spendResources({gold:10,food:101}),same:old===JSON.stringify(gameState.resources),valid:spendResources({gold:20,food:30}),gold:gameState.resources.gold,food:gameState.resources.food}}")
   assert r=={'denied':True,'same':True,'valid':True,'gold':80,'food':70};return r
  await test('batch_all_or_nothing',batch)
  async def shop(page):
   r=await page.evaluate("()=>{gameState.resources.gem=90;for(const i of SHOP_ITEMS.filter(i=>i.costType==='gem'))buyShopItem(i.id);buyShopItem('buy_gold');return {r:gameState.resources,saved:kmLocalReadV204(currentCustomId).state.resources,hud:document.getElementById('res-gem').textContent}}")
   assert r['r']==r['saved'] and r['r']['gem']==0 and r['hud']=='0';assert all(r['r'][k]==2100 for k in ['gold','food','wood','ore','herb','magicDust']);return r
  await test('six_shop_products_balance_hud_and_save',shop)
  async def badshop(page):
   r=await page.evaluate("""()=>{const i=SHOP_ITEMS.find(i=>i.id==='buy_gold'),original={...i},old=JSON.stringify(gameState.resources);for(const patch of [{cost:-1},{cost:NaN},{reward:Infinity},{reward:-2},{rewardType:'unknown'}]){Object.assign(i,original,patch);buyShopItem(i.id);}Object.assign(i,original);return old===JSON.stringify(gameState.resources)}""");assert r;return r
  await test('invalid_shop_data_no_partial_debit',badshop)
  async def spin(page,index=2):
   await page.evaluate('(i)=>{Math.random=()=> (i+.1)/5;openRouletteModal();spinRouletteWheel()}',index);await page.clock.run_for(3001)
  async def reopen(page):
   await spin(page);await page.evaluate('closeRouletteModal();openRouletteModal()')
   r=await page.evaluate('({count:gameState.roulette.countToday,gem:gameState.resources.gem,disabled:document.getElementById("btn-spin-roulette").disabled,result:document.getElementById("roulette-result-display").textContent})');assert r['count']==1 and r['gem']==30 and r['disabled'];return r
  await test('roulette_first_close_reopen',reopen)
  async def spam(page):
   await page.evaluate('Math.random=()=>.41;openRouletteModal();for(let i=0;i<10;i++){spinRouletteWheel();closeRouletteModal();openRouletteModal()}');await page.clock.run_for(3001)
   r=await page.evaluate('({count:gameState.roulette.countToday,gem:gameState.resources.gem})');assert r=={'count':1,'gem':30};return r
  await test('roulette_10_reentrant_calls_once',spam)
  async def cooldown(page):
   await spin(page);last=await page.evaluate('gameState.roulette.lastSpinTime')
   await page.clock.set_system_time((last+3599999)/1000);assert await page.evaluate('spinRouletteWheel();kmRouletteSpin===null')
   await page.clock.set_system_time((last+3600000)/1000);assert await page.evaluate('spinRouletteWheel();kmRouletteSpin!==null')
   await page.clock.run_for(3001);assert await page.evaluate('gameState.roulette.countToday===2');return 'blocked at -1ms, allowed at exactly 1h'
  await test('roulette_exact_hour_boundary',cooldown)
  async def daily(page):
   await page.evaluate('gameState.roulette={countToday:2,lastSpinTime:Date.now()-3600000};');await spin(page)
   await page.clock.set_system_time((await page.evaluate('Date.now()+3600000'))/1000)
   r=await page.evaluate('spinRouletteWheel();({count:gameState.roulette.countToday,busy:!!kmRouletteSpin})');assert r=={'count':3,'busy':False};return r
  await test('roulette_daily_three_limit',daily)
  async def midnight(page):
   t=datetime.datetime(2026,10,14,23,59,58,tzinfo=datetime.timezone.utc);await page.clock.set_system_time(t)
   await page.evaluate('gameState.roulette={countToday:2,lastSpinTime:Date.now()-3600000};');await spin(page)
   r=await page.evaluate('gameState.roulette');assert r['dayKey']=='2026-10-15' and r['countToday']==1;return r
  await test('roulette_completion_crosses_utc_midnight',midnight)
  async def daywait(page):
   await page.clock.set_system_time(datetime.datetime(2026,10,15,0,0,1,tzinfo=datetime.timezone.utc))
   r=await page.evaluate("gameState.roulette={countToday:3,lastSpinTime:Date.now()-2000,dayKey:'2026-10-14'};kmRouletteStatus()")
   assert r['left']==3 and r['wait']==3598000 and r['r']['dayKey']=='2026-10-15';return r
  await test('midnight_resets_count_not_cooldown',daywait)
  async def legacy(page):
   r=await page.evaluate("""()=>{gameState.roulette={countToday:2,lastSpinTime:Date.now()-100};const same={...kmRouletteStatus().r};gameState.roulette={countToday:3,lastSpinTime:Date.now()-86400000};const old={...kmRouletteStatus().r};gameState.roulette={countToday:2,lastSpinTime:0};const zero={...kmRouletteStatus().r};delete gameState.roulette;const missing=kmRouletteStatus();return {same,old,zero,missing}}""")
   assert r['same']['countToday']==2 and r['old']['countToday']==0 and r['zero']['countToday']==2 and r['missing']['left']==3;return r
  await test('legacy_dates_counts_missing_record',legacy)
  async def backwards(page):
   r=await page.evaluate("gameState.roulette={countToday:2,lastSpinTime:Date.now()+86400000,dayKey:'2026-10-15'};kmRouletteStatus()")
   assert r['left']==1 and r['wait']==90000000 and r['r']['dayKey']=='2026-10-15';return r
  await test('clock_backwards_does_not_reset',backwards)
  async def reload(page):
   await spin(page);saved=await page.evaluate('kmLocalReadV204(currentCustomId).state')
   await page.reload(wait_until='domcontentloaded');await page.locator('#login-id').fill('VIRTUAL_A');await page.locator('#login-pw').fill('fake');await page.evaluate('attemptLogin()')
   r=await page.evaluate('({gem:gameState.resources.gem,roulette:gameState.roulette})');assert r['gem']==saved['resources']['gem'] and r['roulette']==saved['roulette'];return r
  await test('roulette_reload_credit_and_limits_together',reload)
  async def savefail(page):
   await page.evaluate("kmLocalWriteV204(currentCustomId);window.oldSet=Storage.prototype.setItem;Storage.prototype.setItem=function(){throw Error('injected failure')};void 0")
   await spin(page)
   r=await page.evaluate('({gem:gameState.resources.gem,count:gameState.roulette.countToday,saved:kmLocalReadV204(currentCustomId).state.resources.gem,busy:!!kmRouletteSpin})');assert r=={'gem':10,'count':0,'saved':10,'busy':False}
   await page.evaluate('Storage.prototype.setItem=window.oldSet;void 0');await spin(page);assert await page.evaluate('gameState.resources.gem===30&&gameState.roulette.countToday===1');return r
  await test('roulette_save_failure_rollback_and_retry',savefail)
  async def owner(page):
   await page.evaluate("openRouletteModal();spinRouletteWheel();window.currentCustomId='VIRTUAL_B';gameState.roulette={countToday:0,lastSpinTime:0}");await page.clock.run_for(3001)
   assert await page.evaluate('gameState.resources.gem===10&&gameState.roulette.countToday===0');return 'stale completion rejected'
  await test('roulette_stale_account_callback',owner)
  for i,reward in enumerate([1,10,20,30,50]):
   async def pointer(page,i=i,reward=reward):
    await spin(page,i);r=await page.evaluate('({gem:gameState.resources.gem,angle:kmRouletteRotation%360,result:document.getElementById("roulette-result-display").textContent})')
    sector=int(((360-r['angle'])%360)//72);assert sector==i and r['gem']==10+reward and ('+'+str(reward)) in r['result'];return r
   await test('roulette_pointer_reward_'+str(reward),pointer)
  async def battlepoor(page):
   r=await page.evaluate("()=>{gameState.towerFloor=5;gameState.selectedSquad=[0];const old=JSON.stringify(gameState.resources);startBattle();return {same:old===JSON.stringify(gameState.resources),pending:kmBattleLaunchPending,battling:gameState.isBattling}}")
   assert r=={'same':True,'pending':False,'battling':False};return r
  await test('boss_insufficient_before_warning',battlepoor)
  async def battledrift(page):
   await page.evaluate("gameState.towerFloor=5;gameState.selectedSquad=[0];Object.assign(gameState.resources,getTowerEntryCosts(5));gameState.resources.ore=1000;startBattle();startHeroUpgrade(0);window.beforeLaunch={...gameState.resources};")
   await page.clock.run_for(2100);r=await page.evaluate('({same:JSON.stringify(beforeLaunch)===JSON.stringify(gameState.resources),food:gameState.resources.food,battle:gameState.isBattling,pending:kmBattleLaunchPending,button:document.getElementById("btn-start-battle").disabled})')
   assert r['same'] and r['food']>=0 and not r['battle'] and not r['pending'];return r
  await test('boss_balance_changes_before_debit',battledrift)
  async def battleonce(page):
   await page.evaluate("gameState.towerFloor=5;gameState.selectedSquad=[0];Object.assign(gameState.resources,{gold:1000,food:1000,herb:1000,magicDust:1000});runBattleV12=async()=>{};for(let i=0;i<10;i++)startBattle();")
   await page.clock.run_for(2100);r=await page.evaluate('({r:gameState.resources,c:getTowerEntryCosts(5),battle:gameState.isBattling,pending:kmBattleLaunchPending})');assert all(r['r'][k]==1000-v for k,v in r['c'].items()) and r['battle'] and not r['pending'];return r
  await test('boss_pending_reentry_single_charge',battleonce)
  async def buildfail(page):
   await page.evaluate("gameState.selectedSquad=[0];gameState.resources.gold=500;gameState.resources.food=500;window.beforeLaunch={...gameState.resources};buildBattleUnits=()=>{throw Error('injected setup failure')};startBattle();")
   assert await page.evaluate('JSON.stringify(beforeLaunch)===JSON.stringify(gameState.resources)&&!kmBattleLaunchPending&&!gameState.isBattling');return 'no debit'
  await test('battle_setup_failure_no_debit',buildfail)
  async def kingdom(page):
   r=await page.evaluate("()=>{for(let l=2;l<=3;l++){Object.values(BUILDINGS).forEach(b=>b.level=l);Object.values(GATHERING_NODES).forEach(b=>b.level=l);checkKingdomLevelUp();}checkKingdomLevelUp();const first=document.getElementById('popup-new-kingdom-level').textContent;closeKingdomLevelUpModal();return {gem:gameState.resources.gem,level:gameState.level,first,second:document.getElementById('popup-new-kingdom-level').textContent,eq:Object.values(ARMY_EQUIPMENT).flatMap(Object.values).reduce((a,b)=>a+b,0)}}")
   assert r=={'gem':110,'level':3,'first':'2','second':'3','eq':2};return r
  await test('kingdom_rewards_and_sequential_notices',kingdom)
  async def cancel(page):
   r=await page.evaluate("()=>{startBuildingUpgrade('farm');startBuildingUpgrade('farm');const paid=gameState.resources.gold;kmAskCancel242('building:farm');kmConfirmCancel242();kmConfirmCancel242();return {paid,gold:gameState.resources.gold,level:BUILDINGS.farm.level,jobs:Object.keys(gameState.upgradesInProgress).length}}")
   assert r=={'paid':50,'gold':75,'level':1,'jobs':0};return r
  await test('duplicate_construction_and_single_half_refund',cancel)
  for kind in ['building','hero']:
   async def accelerate(page,kind=kind):
    r=await page.evaluate("""kind=>{const key=kind==='building'?'building:farm':'hero:0';if(kind==='building')startBuildingUpgrade('farm');else startHeroUpgrade(0);const end=gameState.upgradesInProgress[key].endTime;kmAccelerate247(key);kmAccelerate247(key);return {gem:gameState.resources.gem,job:!!gameState.upgradesInProgress[key],level:kind==='building'?BUILDINGS.farm.level:HEROES[0].level}}""",kind)
    assert r=={'gem':9,'job':False,'level':2};return r
   await test(kind+'_acceleration_completed_no_double_debit',accelerate)
  async def exact720(page):
   r=await page.evaluate("()=>{gameState.upgradesInProgress['building:farm']={type:'building',subKey:'farm',endTime:Date.now()+2000000,totalTime:2000,productionGainV241:2,paidCostsV242:{gold:50}};const end=gameState.upgradesInProgress['building:farm'].endTime;kmAccelerate247('building:farm');const shift=end-gameState.upgradesInProgress['building:farm'].endTime;kmAskCancel242('building:farm');kmConfirmCancel242();return {shift,gem:gameState.resources.gem,gold:gameState.resources.gold}}")
   assert r=={'shift':720000,'gem':9,'gold':125};return r
  await test('720_seconds_and_cancel_no_gem_refund',exact720)
  async def equipment(page):
   r=await page.evaluate("()=>{instantEquipUpgrade('infantry','helmet');instantEquipUpgrade('infantry','helmet');return {level:ARMY_EQUIPMENT.infantry.helmet,pureGold:gameState.resources.pureGold}}")
   assert r=={'level':1,'pureGold':3};return r
  await test('equipment_price_and_click_lock',equipment)
  async def offline(page,duration,event,expected,key='food'):
   r=await page.evaluate("""arg=>{const now=Date.now(),start=now-arg.duration*1000;for(const k of Object.keys(gameState.resources))gameState.resources[k]=0;gameState._kmLastProductionAtV205=start;gameState.upgradesInProgress={};if(arg.event!==null)gameState.upgradesInProgress['building:farm']={type:'building',subKey:'farm',endTime:start+arg.event*1000,totalTime:arg.event,productionGainV241:2};kmApplyOfflineV205(start);const once=gameState.resources.food;kmApplyOfflineV205(start);return {once,twice:gameState.resources.food,level:BUILDINGS.farm.level}}""",{'duration':duration,'event':event})
   assert r['once']==expected and r['twice']==expected;return r
  for name,duration,event,expect in [('offline_1h',3600,None,3600),('offline_24h_cap',86400,None,43200),('offline_3s_event_10s',10,3,24),('offline_1h_event_12h',43200,3600,122400),('offline_after_cap_completion',86400,46800,43200)]:
   async def off(page,duration=duration,event=event,expect=expect):return await offline(page,duration,event,expect)
   await test(name,off)
  async def twoWood(page):
   r=await page.evaluate("()=>{const now=Date.now(),start=now-43200000;gameState.resources.wood=0;gameState._kmLastProductionAtV205=start;gameState.upgradesInProgress={'building:sawmill':{type:'building',subKey:'sawmill',endTime:start+3600000,productionGainV241:2},'gather:wood':{type:'gather',subKey:'wood',endTime:start+7200000,productionGainV241:2}};kmApplyOfflineV205(start);return gameState.resources.wood}");assert r==237600;return r
  await test('offline_two_wood_producers',twoWood)
  async def independent(page):
   r=await page.evaluate("()=>{gameState.resources.gold=1000;gameState.resources.wood=1000;startBuildingUpgrade('farm');startGatherUpgrade('wood');return {keys:Object.keys(gameState.upgradesInProgress),rates:kmProductionRatesV217()}}")
   assert set(r['keys'])=={'building:farm','gather:wood'} and r['rates']['food']==1 and r['rates']['wood']==2;return r
  await test('independent_jobs_produce_old_rates',independent)
  async def balancebad(page):
   r=await page.evaluate("()=>{const out=[];for(const v of [NaN,Infinity,-1,'100']){gameState.resources.gem=v;out.push(!spendResource('gem',1));}return out}");assert all(r);return r
  await test('invalid_existing_balance_rejected',balancebad)
  async def interrupted(page):
   await page.evaluate('kmLocalWriteV204(currentCustomId);openRouletteModal();spinRouletteWheel();')
   await page.clock.run_for(1000);await page.reload(wait_until='domcontentloaded')
   await page.locator('#login-id').fill('VIRTUAL_A');await page.locator('#login-pw').fill('fake');await page.evaluate('attemptLogin()')
   await page.clock.run_for(4000)
   r=await page.evaluate('({gem:gameState.resources.gem,count:gameState.roulette.countToday})');assert r=={'gem':10,'count':0};return r
  await test('reload_before_spin_completion_no_reward',interrupted)
  async def invalidtime(page):
   r=await page.evaluate("gameState.roulette={countToday:1,lastSpinTime:1e100};kmRouletteStatus()")
   assert r['left']==2 and r['wait']==3600000;return r
  await test('legacy_invalid_timestamp_conservative_fallback',invalidtime)
  async def login_isolation(page):
   await page.evaluate("""()=>{gameState.resources.food=54321;BUILDINGS.farm.level=7;HEROES[0].level=9;ARMY_EQUIPMENT.infantry.helmet=4;gameState.productionV241={'building:farm':77};gameState.upgradesInProgress={'gather:wood':{type:'gather',subKey:'wood',endTime:Date.now()+60000,totalTime:60,productionGainV241:3,paidCostsV242:{wood:120}}};kmLocalWriteV204('VIRTUAL_A');window.currentCustomId=null;kmSaveEnabledV204=false;window.originalA=localStorage.getItem(kmLocalKeyV204('VIRTUAL_A'));Storage.prototype.setItem=function(){throw Error('injected login failure')};}""")
   await page.locator('#login-id').fill('VIRTUAL_A');await page.locator('#login-pw').fill('fake')
   async with page.expect_navigation(wait_until='domcontentloaded'):
    await page.evaluate('attemptLogin()')
   await page.locator('#login-id').fill('VIRTUAL_B');await page.locator('#login-pw').fill('fake');await page.evaluate('attemptLogin()')
   r=await page.evaluate("({id:currentCustomId,food:gameState.resources.food,level:BUILDINGS.farm.level,hero:HEROES[0].level,equip:ARMY_EQUIPMENT.infantry.helmet,production:gameState.productionV241||{},jobs:gameState.upgradesInProgress,original:kmLocalReadV204('VIRTUAL_A').state})")
   assert r['id']=='VIRTUAL_B' and r['food']==100 and r['level']==1 and r['hero']==1 and r['equip']==0 and r['production']=={} and r['jobs']=={}
   assert r['original']['resources']['food']==54321 and r['original']['productionV241']['building:farm']==77
   return {'newAccountDefault':True,'oldAccountPreserved':True}
  await test('login_save_failure_restart_new_account_isolation',login_isolation)
  async def retry_a(page):
   await page.evaluate("""()=>{gameState.resources.food=4321;HEROES[0].level=3;ARMY_EQUIPMENT.archer.gloves=2;kmLocalWriteV204('VIRTUAL_A');window.currentCustomId=null;kmSaveEnabledV204=false;Storage.prototype.setItem=function(){throw Error('injected login failure')};}""")
   await page.locator('#login-id').fill('VIRTUAL_A');await page.locator('#login-pw').fill('fake')
   async with page.expect_navigation(wait_until='domcontentloaded'):await page.evaluate('attemptLogin()')
   await page.locator('#login-id').fill('VIRTUAL_A');await page.locator('#login-pw').fill('fake');await page.evaluate('attemptLogin()')
   r=await page.evaluate('({food:gameState.resources.food,hero:HEROES[0].level,equip:ARMY_EQUIPMENT.archer.gloves})');assert r=={'food':4321,'hero':3,'equip':2};return r
  await test('login_save_failure_same_account_retry',retry_a)
  async def victory(page):
   # Start a real encounter before exercising settlement; no guard bypass.
   await page.evaluate("gameState.towerFloor=5;gameState.selectedSquad=[0];Object.assign(gameState.resources,{gold:1000,food:1000,herb:1000,magicDust:1000});runBattleV12=async()=>{};startBattle()")
   await page.clock.run_for(2100)
   r=await page.evaluate("()=>{if(!BATTLE_V12.running||!gameState.isBattling)throw Error('encounter did not start');Math.random=()=>0;const old={...gameState.resources};BATTLE_V12.enemy.hp=0;finishBattleV12(true,BATTLE_V12.enemy);return {deltas:Object.fromEntries(['pureGold','emerald','ruby','sapphire','gem'].map(k=>[k,gameState.resources[k]-old[k]])),floor:gameState.towerFloor}}")
   assert r=={'deltas':{'pureGold':2,'emerald':2,'ruby':2,'sapphire':2,'gem':0},'floor':6};return r
  await test('normal_boss_victory_reward_formula_unchanged',victory)
  (ROOT/'regression-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print('TOTAL',len(results),'PASS',sum(r['status']=='PASS' for r in results),flush=True)
  await browser.close()
asyncio.run(main())
raise SystemExit(1 if any(r['status']!='PASS' for r in results) else 0)
