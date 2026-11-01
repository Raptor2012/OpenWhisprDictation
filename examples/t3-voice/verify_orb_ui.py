"""Opt-in WebView2 UI checks. Uses an isolated demo, no microphone, input simulation or T3 sends.

Run with the example's venv. Evidence stays in runtime/orb-ui-qa beneath this file.
"""
import json
import os
from pathlib import Path
import threading
import time

os.environ['WEBVIEW2_DEFAULT_BACKGROUND_COLOR'] = '00000000'
import webview

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'runtime/orb-ui-qa'
OUT.mkdir(parents=True, exist_ok=True)
window = webview.create_window('Orb UI verification', url=str(ROOT/'ui/orb.html')+'?demo=ready&static=1',
                               width=340, height=456, frameless=True, focus=False,
                               resizable=False, min_size=(100,48))
report = {'cases': [], 'failures': []}


def run():
    import ctypes
    from System.Drawing import Size
    from System.Windows.Forms import MethodInvoker
    from System.IO import FileStream, FileMode
    from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat
    user32 = ctypes.WinDLL('user32')

    def resize(width, height):
        done = threading.Event()
        def apply():
            scale = user32.GetDpiForWindow(window.native.Handle.ToInt32())/96
            window.native.ClientSize = Size(round(width*scale), round(height*scale))
            done.set()
        window.native.BeginInvoke(MethodInvoker(apply))
        if not done.wait(5):
            raise RuntimeError('Resize did not complete')

    def capture(name):
        done, saved = threading.Event(), {}
        def apply():
            saved['stream'] = FileStream(str(OUT/(name+'.png')), FileMode.Create)
            saved['task'] = window.native.browser.webview.CoreWebView2.CapturePreviewAsync(
                CoreWebView2CapturePreviewImageFormat.Png, saved['stream'])
            done.set()
        window.native.BeginInvoke(MethodInvoker(apply))
        if not done.wait(5):
            raise RuntimeError('Capture did not start')
        if not saved['task'].Wait(5000):
            raise RuntimeError('Capture did not finish')
        saved['stream'].Dispose()

    try:
        window.evaluate_js('''window.qaErrors=[];window.addEventListener('error',e=>qaErrors.push(e.message));
          window.qaCalls=[];api=(name,...args)=>{qaCalls.push({name,args});
            if(name==='set_expanded')S.expanded=args[0];
            if(name==='confirm_review')S.review.sending=true;};
          document.body.style.background='#202329';''')
        states = ['loading','ready','hearing','transcribing','sending','waiting','speaking','reading','off','error','dictating','processing','done','failed']
        cases = [(state, dock, '') for dock in (False,True) for state in states]
        cases += [('ready',dock,panel) for dock in (False,True) for panel in ('card','menu','list','bubble','live','processing-preview','review','failed-review')]
        for state, dock, panel in cases:
            width, height = ((200,48) if dock else (180,150))
            if panel in ('card','menu','list'):
                width,height = (320,236 if dock else 336)
                if panel=='list':height+=120
            elif panel:
                width,height = (340,214 if dock else 300)
            resize(width,height)
            window.evaluate_js('''(()=>{
              const [state,dock,panel]=%s;
              S=Object.assign(S,{state,dock,expanded:['card','menu','list'].includes(panel),visible:true,
                mic:.25,out:.25,micMuted:false,maeveMuted:false,review:null,bubble:null});
              hovering=true;document.body.classList.add('hover');
              document.getElementById('menu').classList.toggle('open',panel==='menu');
              document.getElementById('list').classList.toggle('open',panel==='list');
              if(panel==='bubble')S.bubble={id:Date.now(),who:'you',text:'A longer reply '.repeat(50)};
              if(panel==='live'||panel==='processing-preview'){
                S.state=panel==='live'?'dictating':'processing';
                S.bubble={id:'live-preview',who:'you',live:panel==='live',processing:panel==='processing-preview',
                  text:'The words I am saying appear above the orb while I hold the button.'};
              }
              if(['review','failed-review'].includes(panel))S.review={id:Date.now(),text:'Please check the Windows build and fix the cause.',
                title:'Selected thread',sending:false,error:panel==='failed-review'?'Temporary failure':''};
              render();
            })()''' % json.dumps([state,dock,panel]))
            time.sleep(.6 if panel else .25)
            ids = (['bar','barOrb','wave','barMic','barMaeve','barExpand'] if dock else ['muteMic','muteMaeve','toBar'])
            ids += {'card':['card','delivery','fQuit'], 'menu':['card','menu'], 'list':['card','list'],
                    'bubble':['bubble'], 'live':['bubble'], 'processing-preview':['bubble'],
                    'review':['review','reviewSend'], 'failed-review':['review','reviewSend']}.get(panel,[])
            result = window.evaluate_js('''(()=>{
              const bad=[];for(const id of %s){const r=document.getElementById(id).getBoundingClientRect();
                if(!r.width||!r.height||r.left<-.5||r.top<-.5||r.right>innerWidth+.5||r.bottom>innerHeight+.5)bad.push({id,rect:r.toJSON()});}
              return {width:innerWidth,height:innerHeight,bad,errors:qaErrors.slice()};
            })()''' % json.dumps(ids))
            result.update(state=state,dock=dock,panel=panel)
            report['cases'].append(result)
            if result['bad'] or result['errors']:report['failures'].append(result)
            if panel in ('review','menu','live','processing-preview') or state=='dictating':
                capture(('bar' if dock else 'orb')+'-'+(panel or state))
        preview = window.evaluate_js('''(()=>{
          S.review=null;S.bubble={id:'revision-test',who:'you',live:true,text:'Open the wrong file'};tickBubble(.1);
          S.bubble.text='Open the right file';tickBubble(.1);
          const revised=btext.textContent==='Open the right file';
          const liveLabel=whoEl.textContent==='You · live';
          S.bubble={...S.bubble,live:false,processing:true};tickBubble(.1);
          const processingLabel=whoEl.textContent==='You · transcribing';
          S.bubble={...S.bubble,processing:false,text:'Final cleaned words.'};tickBubble(.1);
          return {revised,liveLabel,processingLabel,finalText:btext.textContent,errors:qaErrors.slice()};
        })()''')
        report['preview'] = preview
        if (not all(preview[key] for key in ('revised','liveLabel','processingLabel'))
                or preview['finalText']!='Final cleaned words.' or preview['errors']):
            report['failures'].append({'preview':preview})
        window.evaluate_js('''(()=>{
          S.review=null;S.expanded=true;applyExpanded(true);render();
          window.qaOldSnapshot={...S,expanded:true};window.qaOldGeneration=typeof settingsGeneration==='number'?settingsGeneration:0;
          const writes=[];api=(name,...args)=>{if(name==='set_expanded')writes.push(args[0]);return Promise.resolve();};
          setExpanded(false);
          // An already-running poll can still contain the previous open state.
          S.expanded=true;render();setHover(false);
          const staysClosed=!expanded&&!card.classList.contains('open');
          setExpanded(true);setExpanded(false);S.expanded=true;render();
          const latestClickWins=!expanded&&!card.classList.contains('open');
          window.qaTransitions={staysClosed,latestClickWins,writes,errors:qaErrors.slice()};
        })()''')
        time.sleep(.05)
        window.evaluate_js('''(()=>{
          acceptSnapshot({...qaOldSnapshot},qaOldGeneration,false);
          qaTransitions.oldPollAfterAckStaysClosed=!expanded;
          acceptSnapshot({...qaOldSnapshot},settingsGeneration,true);
          qaTransitions.pollDuringWriteStaysClosed=!expanded;
          S.expanded=true;applyExpanded(true);
          window.qaOriginalMatches=document.documentElement.matches;
          document.documentElement.matches=function(selector){return selector===':hover'?false:qaOriginalMatches.call(this,selector);};
          choosingDelivery=false;dismissAfterLeave();
        })()''')
        time.sleep(.5)
        window.evaluate_js('''qaTransitions.pointerLeaveCloses=!expanded&&!card.classList.contains('open');
          document.documentElement.matches=qaOriginalMatches;qaTransitions.errors=qaErrors.slice();''')
        transitions = window.evaluate_js('qaTransitions')
        window.evaluate_js('S.expanded=false;render();')
        report['transitions'] = transitions
        if (not transitions['staysClosed'] or not transitions['latestClickWins']
                or transitions['writes'] != [False,True,False,False]
                or not all(transitions[key] for key in ('oldPollAfterAckStaysClosed','pollDuringWriteStaysClosed','pointerLeaveCloses'))
                or transitions['errors']):
            report['failures'].append({'transitions':transitions})
        window.evaluate_js('''api=(name,...args)=>{qaCalls.push({name,args});
            if(name==='set_expanded')S.expanded=args[0];
            if(name==='confirm_review')S.review.sending=true;};''')
        actions = window.evaluate_js('''(()=>{
          S.expanded=false;S.review=null;render();qaCalls=[];
          toggleMicMute();toggleMaeveMute();toggleDock();
          for(const id of ['pVoice','pStop','fTest','mFollow','mCleanup','mStartup','fQuit'])document.getElementById(id).onclick();
          S.review={id:123,text:'Editable preview',title:'Destination'};render();
          reviewText.value='Edited preview';sendReview();sendReview();render();
          const confirms=qaCalls.filter(c=>c.name==='confirm_review');
          const result={calls:qaCalls.slice(),confirms:confirms.length,edited:confirms[0]?.args[1],
            disabled:document.getElementById('reviewSend').disabled,
            muteAria:document.getElementById('muteMic').getAttribute('aria-pressed'),
            missingRoles:[...document.querySelectorAll('.ctl,.bbtn,.pill')].filter(el=>el.tabIndex<0||el.getAttribute('role')!=='button').map(el=>el.id),
            legacyPillToggle:!!document.getElementById('mPill'),errors:qaErrors.slice()};
          result.legacyHandsfreeControl=typeof document.getElementById('pMode').onclick==='function';
          return result;
        })()''')
        report['actions'] = actions
        expected={'toggle_mic_mute','toggle_maeve_mute','toggle_dock','toggle_voice','stop','test_voice','toggle_follow_active','toggle_cleanup','toggle_startup','quit'}
        if (not expected.issubset({c['name'] for c in actions['calls']}) or actions['confirms']!=1
                or actions['edited']!='Edited preview' or not actions['disabled'] or actions['missingRoles']
                or actions['legacyPillToggle'] or actions['legacyHandsfreeControl'] or actions['errors']):
            report['failures'].append({'actions':actions})
    except Exception as exc:
        report['failures'].append({'error':repr(exc)})
    finally:
        (OUT/'results.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print('UI cases:',len(report['cases']),'Failures:',len(report['failures']),flush=True)
        window.destroy()


window.events.loaded += lambda: threading.Thread(target=run,daemon=True).start()
if __name__ == '__main__':
    webview.start(gui='edgechromium',private_mode=True)
    raise SystemExit(1 if report['failures'] else 0)
