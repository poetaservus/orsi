"""Independent behavioral oracle for the preserved logo-scroll complaint.

Run inside an owned worker when starting a preview. Reports contain only fixed
check names and numeric observations; source and conversation text stay out.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
import subprocess
import sys
from time import monotonic, sleep

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SNAPSHOT = """() => {
  const hero=document.querySelector('.animation-showcase');
  const stage=document.querySelector('.animation-showcase__stage') || hero;
  const logo=document.querySelector('.animated-logo');
  const next=document.querySelector('.next-section');
  const r=stage.getBoundingClientRect(), s=getComputedStyle(logo);
  return {y:scrollY, viewport:innerHeight, heroHeight:hero.offsetHeight,
    stageHeight:stage.offsetHeight, top:r.top, bottom:r.bottom,
    visible:r.top<innerHeight && r.bottom>0 && s.visibility!=='hidden' && Number(s.opacity)>0,
    nextTop:next.getBoundingClientRect().top,
    phases:['q-fade','q-move','words','subtitle','exit'].map(n=>Number(s.getPropertyValue('--'+n+'-progress'))),
    appearance:['q','bal','gh','subtitle'].map(name=>{
      const e=document.querySelector('.animated-logo__'+name);if(!e)return null;
      const style=getComputedStyle(e);let opacity=1, visible=true;
      for(let p=e;p;p=p.parentElement){const st=getComputedStyle(p);opacity*=Number(st.opacity);visible&&=st.visibility==='visible' && st.display!=='none'}
      return {opacity,visible,transform:style.transform};
    })};
}"""


def check_scroll_behavior(page, capture_directory=None):
    checks, observations = [], []

    def sample():
        page.wait_for_timeout(150)
        value = page.evaluate(SNAPSHOT)
        observations.append(value)
        return value

    def jump(y):
        page.evaluate("y => scrollTo({top:y,behavior:'instant'})", y)
        return sample()

    def check(name, passed):
        checks.append({"name": name, "passed": bool(passed)})

    def capture(label):
        if capture_directory is not None:
            page.screenshot(path=str(capture_directory/f'acceptance-{label}.png'),full_page=False)

    def matches(a, b):
        number = r'[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?'
        def same_piece(x,y):
            if x is None or y is None:
                return False
            return (abs(x['opacity']-y['opacity'])<.01 and x['visible']==y['visible']
                and re.sub(number,'#',x['transform'])==re.sub(number,'#',y['transform'])
                and all(abs(float(v)-float(w))<.01 for v,w in zip(re.findall(number,x['transform']),re.findall(number,y['transform']))))
        return all(same_piece(x,y) for x,y in zip(a['appearance'],b['appearance']))

    start = jump(0)
    capture('initial')
    distance = max(start['heroHeight']-start['stageHeight'], start['viewport'])
    page.mouse.move(30, 30)
    page.mouse.wheel(0, int(distance*.5))
    forward = sample()
    check('hero_visible_during_forward_animation', forward['visible'])
    check('native_scroll_advances_animation', forward['y'] > 0 and not matches(forward,start))
    middle = jump(distance*.5)
    capture('partial')
    check('hero_remains_visible_at_partial_progress', middle['visible'] and abs(middle['top']) < 1)
    complete = jump(distance*.8)
    capture('complete')
    check('logo_assembles_before_exit', all(p and p['visible'] and p['opacity']>.98 for p in complete['appearance']))
    below = jump(start['heroHeight']+100)
    check('next_section_accessible_after_animation', below['nextTop'] < start['viewport'])
    page.mouse.move(30, 30)
    page.mouse.wheel(0, -300)
    reverse = sample()
    check('upward_wheel_moves_page_immediately', reverse['y'] < below['y'])
    returned = jump(distance*.5)
    capture('return')
    check('same_position_restores_same_animation', matches(middle, returned) and returned['visible'])

    for key, direction in [('PageDown', 1), ('PageUp', -1)]:
        before = sample()
        page.keyboard.press(key)
        page.wait_for_timeout(500)
        after = sample()
        # Re-enter from another position to compare native keyboard navigation
        # against the same position reached through scrollbar-style navigation.
        jump(0)
        reference = jump(after['y'])
        check('keyboard_'+key+'_synchronized', (after['y']-before['y'])*direction > 0 and matches(after, reference))

    # Chromium's actual scrollbar track, not wheel emulation or scrollTo.
    jump(0)
    page.mouse.click(page.viewport_size['width']-5, page.viewport_size['height']*.65)
    page.wait_for_timeout(500)
    bar = sample()
    jump(start['heroHeight']+100)
    bar_reference = jump(bar['y'])
    check('scrollbar_navigation_synchronized', bar['y'] > 0 and matches(bar, bar_reference))

    jump(distance*.4)
    before = sample()
    session = page.context.new_cdp_session(page)
    try:
        session.send('Emulation.setTouchEmulationEnabled', {'enabled': True})
        session.send('Input.dispatchTouchEvent', {'type':'touchStart', 'touchPoints':[{'x':100,'y':600}]})
        for y in (570, 530, 480, 420, 350):
            session.send('Input.dispatchTouchEvent', {'type':'touchMove', 'touchPoints':[{'x':100,'y':y}]})
            page.wait_for_timeout(35)
        session.send('Input.dispatchTouchEvent', {'type':'touchEnd', 'touchPoints':[]})
        page.wait_for_timeout(500)
        touch = sample()
        jump(0)
        reference = jump(touch['y'])
        check('touch_navigation_synchronized', touch['y'] > before['y'] and matches(touch, reference))
    finally:
        session.detach()
    timing = page.evaluate("""async () => {
      const intervals=[];let previous=performance.now();const start=previous;
      await new Promise(resolve=> {const frame=now=> {intervals.push(now-previous);previous=now;
        if(now-start>=500 || intervals.length>=120)resolve();else requestAnimationFrame(frame)};requestAnimationFrame(frame)});
      return {intervals_ms:intervals,scope:'Callback timing only; smooth compositor delivery remains unverified.'};
    }""")
    return {'passed': all(c['passed'] for c in checks), 'checks': checks, 'observations': observations,'frame_timing':timing}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', required=True)
    parser.add_argument('--project', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    from app.capabilities.project_verification import local_origin, project_command
    local_origin(args.url)
    os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(ROOT/'state/playwright')
    from playwright.sync_api import sync_playwright, Error
    server = None
    try:
        if args.project:
            server = subprocess.Popen(project_command('npm', ['run','dev','--','--host','127.0.0.1',
                '--port',str(local_origin(args.url)[2])])[0], cwd=args.project,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, ignore_default_args=['--hide-scrollbars'],
                args=['--disable-features=OverlayScrollbar'])
            try:
                page = browser.new_page(viewport={'width':1440,'height':900})
                deadline = monotonic()+20
                while True:
                    try:
                        page.goto(args.url, wait_until='load', timeout=10000)
                        page.wait_for_selector('.animated-logo')
                        break
                    except Error:
                        if monotonic() > deadline:
                            raise
                        sleep(.1)
                report = check_scroll_behavior(page,args.output.parent)
                args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
                print(json.dumps({'passed':report['passed'], 'failed':[c['name'] for c in report['checks'] if not c['passed']]}))
            finally:
                browser.close()
    finally:
        if server is not None:
            server.terminate()


if __name__ == '__main__':
    main()
