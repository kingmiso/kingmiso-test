"""Audited P1 functions/assertions copied verbatim; guarded runtime supplies paths."""
import ast,asyncio,collections,datetime,hashlib,json,os,pathlib,re,socket,subprocess,sys,traceback
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from safety.runtime import require_active
from safety.config import PACKAGE, HEADERS
_job=require_active()
REPO=pathlib.Path(_job['repo'])
ROOT=pathlib.Path(_job['output'])
BASE='http://economy-audit.invalid/'
T0=1792292400000
ERRORS=[]

def sha(raw): return hashlib.sha256(raw).hexdigest()

def write(name, value): (ROOT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

def source(): return (REPO / 'index.html').read_bytes().replace(b'\r\n', b'\n')

def stamp(ms): return datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc)

def near(actual, expected): return abs(actual - expected) < 1e-6

STATE = """() => ({now:Date.now(),resources:{...gameState.resources},level:BUILDINGS.farm.level,rate:kmFacilityRate241('building','farm'),jobs:JSON.parse(JSON.stringify(gameState.upgradesInProgress)),production:JSON.parse(JSON.stringify(gameState.productionV241||{})),lastTick:kmLastResourceTickV202,save:kmLocalReadV204(currentCustomId),hud:{food:document.getElementById('res-food').textContent,gold:document.getElementById('res-gold').textContent},woodLevel:GATHERING_NODES.wood.level,oreLevel:GATHERING_NODES.ore.level,magicLevel:GATHERING_NODES.magic.level})"""

async def prepare(page, ms):
    await page.clock.install(time=stamp(ms))
    await page.clock.pause_at(stamp(ms))
    page.on('dialog', lambda d: d.accept())
    page.on('pageerror', lambda e: ERRORS.append(str(e)[:300]))
    await page.goto(BASE, wait_until='load')
    await offline_only(page)

async def offline_only(page):
    assert await page.evaluate("typeof __firebase_config==='undefined' && typeof __initial_auth_token==='undefined' && typeof kmCloudReadyV204==='undefined' && typeof cloudLoadGame==='undefined'")
    await page.evaluate("window.cloudSaveGame=()=>kmSaveLocalV204();playSfx=()=>{};isMuted=true;")

async def login(page, name='FAKE_TIMER_ONLY'):
    await page.locator('#login-id').fill(name)
    await page.locator('#login-pw').fill('synthetic-only')
    await page.evaluate('attemptLogin()')
    assert await page.evaluate('window.currentCustomId') == name

async def setup(browser, ms=T0, login_enabled=True):
    ctx = await browser.new_context(service_workers='block', bypass_csp=False, ignore_https_errors=False, timezone_id='Asia/Seoul', locale='ko-KR', viewport={'width':393, 'height':852})
    async def route(r):
        if r.request.url == BASE and r.request.method == 'GET':
            await r.fulfill(status=200, content_type='text/html', body=source(), headers=HEADERS)
        else: await r.abort()
    await ctx.route('**/*', route)
    page = await ctx.new_page()
    await prepare(page, ms)
    if login_enabled: await login(page)
    return ctx, page

async def start(page):
    await page.evaluate("openV15Build('building','farm');for(let i=0;i<10;i++)document.getElementById('v15-build-go').click()")
    state = await page.evaluate(STATE)
    assert state['resources']['gold'] == 50
    assert state['jobs']['building:farm']['endTime'] == T0 + 3000
    assert state['rate'] == 1 and state['level'] == 1
    return state

async def advance(page, ms, callback='productionTickV201()'):
    await page.clock.set_system_time(stamp(T0 + ms))
    if callback: await page.evaluate(callback)
    return await page.evaluate(STATE)

async def reopen(ctx, page, ms, reload=False):
    if reload:
        await page.reload(wait_until='load')
        await page.clock.set_system_time(stamp(T0 + ms))
        await offline_only(page)
    else:
        await page.close()
        page = await ctx.new_page()
        await prepare(page, T0 + ms)
    await login(page)
    return page, await page.evaluate(STATE)

async def delayed(browser, ms=10000, first='fast_forward'):
    ctx, page = await setup(browser)
    try:
        before = await start(page)
        if first == 'fast_forward': await page.clock.fast_forward(ms)
        else: await advance(page, ms, first)
        after = await page.evaluate(STATE)
        expected = 3 + (ms / 1000 - 3) * 3
        checks = {'splitAccrual': near(after['resources']['food'] - before['resources']['food'], expected), 'oneCompletion': after['level'] == 2 and after['rate'] == 3 and not after['jobs'], 'oneDebit': near(after['resources']['gold'], 50 + ms/1000), 'hudMatches': int(after['hud']['food'].replace(',','')) == int(after['resources']['food'])}
        return {'checks': checks, 'expectedFoodGain': expected, 'actualFoodGain': after['resources']['food'] - before['resources']['food'], 'before': before, 'after': after}
    finally: await ctx.close()

async def boundary(browser):
    ctx, page = await setup(browser)
    try:
        await start(page)
        before = await advance(page, 2999)
        exact = await advance(page, 3000)
        after = await advance(page, 3001)
        return {'checks': {'before': before['level']==1 and near(before['resources']['food'],102.999), 'exact': exact['level']==2 and near(exact['resources']['food'],103), 'after': after['rate']==3 and near(after['resources']['food'],103.003)}, 'before':before,'exact':exact,'after':after}
    finally: await ctx.close()

async def multiple(browser, staggered):
    ctx, page = await setup(browser)
    try:
        await page.evaluate("gameState.resources.gold=10000;gameState.resources.wood=10000;gameState.resources.ore=10000;startBuildingUpgrade('farm');startGatherUpgrade('wood')")
        if staggered: await advance(page, 1000, '')
        await page.evaluate("startGatherUpgrade('ore');startGatherUpgrade('magic')")
        paid = await page.evaluate(STATE)
        after = await advance(page, 10000)
        # Fixed fixture: initial food1/s, ore2/s (forge + gather), magic1/s; gain2/s.
        food = after['resources']['food'] - paid['resources']['food']
        ore = after['resources']['ore'] - paid['resources']['ore']
        magic = after['resources']['magicDust'] - paid['resources']['magicDust']
        return {'checks': {'food24':near(food,24),'ore':near(ore,32 if staggered else 34),'magic':near(magic,22 if staggered else 24),'fourCompletions':after['level']==after['woodLevel']==after['oreLevel']==after['magicLevel']==2 and not after['jobs'],'noExtraDebit':near(after['resources']['gold']-paid['resources']['gold'],10)}, 'paid':paid,'after':after,'gains':{'food':food,'ore':ore,'magicDust':magic}}
    finally: await ctx.close()

async def duplicate(browser):
    ctx, page = await setup(browser)
    try:
        await start(page)
        first = await advance(page, 10000, "finishUpgradeV16('building:farm')")
        await page.evaluate("for(let i=0;i<10;i++){productionTickV201();upgradeTimerTickV201();finishUpgradeV16('building:farm');kmSaveLocalV204()}")
        repeat = await page.evaluate(STATE)
        next_tick = await advance(page, 11000)
        return {'checks': {'first24':near(first['resources']['food'],124),'idempotent':first['resources']==repeat['resources'] and repeat['level']==2 and repeat['rate']==3,'next3':near(next_tick['resources']['food'],127)},'first':first,'repeat':repeat,'next':next_tick}
    finally: await ctx.close()

async def save_path(browser, kind):
    ctx, page = await setup(browser)
    try:
        await start(page)
        if kind == 'midway':
            await advance(page, 1000)
            await page.evaluate('kmSaveLocalV204()')
            page, restored = await reopen(ctx,page,1000,True)
            after = await advance(page,10000)
        elif kind == 'save_before':
            await advance(page,10000,'kmSaveLocalV204()')
            page, restored = await reopen(ctx,page,10000,True)
            after = restored
        elif kind == 'save_after':
            await advance(page,10000,'productionTickV201();kmSaveLocalV204()')
            page, restored = await reopen(ctx,page,10000,True)
            after = restored
        else:
            page, restored = await reopen(ctx,page,10000)
            after = restored
        await page.evaluate('kmSaveLocalV204()')
        page, repeat = await reopen(ctx,page,10000,True)
        page, later = await reopen(ctx,page,20000)
        return {'checks': {'food24':near(after['resources']['food'],124),'completed':after['level']==2 and after['rate']==3 and not after['jobs'],'noRepeatAward':repeat['resources']==after['resources'],'completedReconnect30':near(later['resources']['food'],154),'oneCost':near(later['resources']['gold'],70),'pendingRestored':kind!='midway' or (restored['level']==1 and restored['jobs']['building:farm']['endTime']==T0+3000)},'restored':restored,'after':after,'repeat':repeat,'later':later}
    finally: await ctx.close()

async def accelerate(browser):
    ctx, page = await setup(browser)
    try:
        await start(page)
        before = await advance(page,2000,"kmAccelerate247('building:farm')")
        after = await advance(page,10000)
        return {'checks': {'noRetroactiveBonus':near(before['resources']['food'],102),'afterAcceleration':near(after['resources']['food'],126),'completedOnce':after['level']==2 and after['rate']==3},'accelerated':before,'after':after}
    finally: await ctx.close()

async def cap(browser, late):
    ctx, page = await setup(browser)
    try:
        await start(page)
        if late: await page.evaluate(f"gameState.upgradesInProgress['building:farm'].endTime={T0+14*3600000}")
        fixture = await page.evaluate('kmSnapshotV204()')
        online = await advance(page,24*3600000)
        await page.evaluate('(s)=>{kmRestoreV204(s);kmApplyOfflineV205(s._kmLastProductionAtV205)}',fixture)
        offline = await page.evaluate(STATE)
        expected = 43200 if late else 3+43197*3
        return {'checks': {'cappedAward':near(online['resources']['food']-100,expected),'offlineUnchanged':online['resources']==offline['resources'],'completedOutsideCap':online['level']==2 and online['rate']==3 and not online['jobs']},'expectedFoodGain':expected,'online':online,'offline':offline}
    finally: await ctx.close()

async def legacy_save(browser):
    ctx, page = await setup(browser)
    try:
        await start(page)
        await page.evaluate("delete gameState.productionV241;delete gameState.upgradesInProgress['building:farm'].productionGainV241;delete gameState.upgradesInProgress['building:farm'].paidCostsV242;kmSaveLocalV204()")
        page, restored = await reopen(ctx,page,0,True)
        after = await advance(page,10000)
        return {'checks':{'legacyLoaded':restored['level']==1 and restored['rate']==1,'gain24':near(after['resources']['food'],124),'newRatePersisted':after['save']['state']['productionV241']['building:farm']==3},'restored':restored,'after':after}
    finally: await ctx.close()

async def original_battle_drift(browser):
    # Recheck only the failed original case, without rerunning its other 43 cases.
    # Compile the exact original function body and assertions; never rewrite them.
    original = (PACKAGE/'tests/regression.py').read_text(encoding='utf-8')
    tree = ast.parse(original)
    node = next(n for n in ast.walk(tree) if isinstance(n,ast.AsyncFunctionDef) and n.name=='battledrift')
    namespace = {}
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(PACKAGE/'tests/regression.py'),'exec'),namespace)
    ms = int(datetime.datetime(2026,10,14,1,tzinfo=datetime.timezone.utc).timestamp()*1000)
    ctx,page = await setup(browser,ms,login_enabled=False)
    try:
        await page.evaluate("window.currentCustomId='VIRTUAL_A';kmSaveEnabledV204=true;window.cloudSaveGame=()=>kmSaveLocalV204();playSfx=()=>{};")
        detail = await namespace['battledrift'](page)
        return {'checks':{'originalAssertionsPassed':True},'originalResult':detail,'originalFunctionSHA256':sha(ast.get_source_segment(original,node).encode('utf-8'))}
    finally: await ctx.close()

async def overdue_cursor(browser):
    ctx, page = await setup(browser)
    try:
        await start(page)
        await page.evaluate(f'kmLastResourceTickV202={T0+5000}')
        after = await advance(page,10000)
        return {'checks':{'noAwardBeforeCursor':near(after['resources']['food'],115),'completedOnce':after['level']==2 and after['rate']==3},'after':after}
    finally: await ctx.close()

def tests(browser):
    return [
        ('suspended_10s',lambda:delayed(browser)),
        ('suspended_65s',lambda:delayed(browser,65000)),
        ('completion_callback_first',lambda:delayed(browser,10000,"finishUpgradeV16('building:farm')")),
        ('production_callback_first',lambda:delayed(browser,10000,'productionTickV201()')),
        ('completion_boundary_1ms',lambda:boundary(browser)),
        ('simultaneous_four_completions',lambda:multiple(browser,False)),
        ('staggered_completions',lambda:multiple(browser,True)),
        ('duplicate_callbacks',lambda:duplicate(browser)),
        *[(f'storage_{kind}',lambda k=kind:save_path(browser,k)) for kind in ('midway','save_before','save_after','offline')],
        ('acceleration_no_retroactive_gain',lambda:accelerate(browser)),
        ('cap_completion_inside',lambda:cap(browser,False)),
        ('cap_completion_outside',lambda:cap(browser,True)),
        ('legacy_save_without_new_fields',lambda:legacy_save(browser)),
        ('overdue_before_cursor',lambda:overdue_cursor(browser)),
        ('original_boss_balance_changes_before_debit',lambda:original_battle_drift(browser))]
