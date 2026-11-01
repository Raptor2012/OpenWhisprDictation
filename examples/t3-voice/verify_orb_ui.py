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

def mirrored_peak_ok(heights, band):
    """Mirrored layout: band b is drawn at u = 0.5 -/+ b/20. Pass if a column at either mirror
    position (+/-1) reaches the tallest height (within one pixel)."""
    top = max(heights)
    columns = {min(10, max(0, int((0.5 + sign * band / 20) * 11))) for sign in (-1, 1)}
    near = [heights[c + k] for c in columns for k in (-1, 0, 1) if 0 <= c + k < len(heights)]
    return max(heights) - min(heights) >= 3 and max(near) >= top - 1



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
        window.evaluate_js('S.viewportTarget=%s;' % json.dumps([width,height]))

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
        import numpy as np
        from t3_voice_core import audio_feedback
        feedback=[]
        # A quiet microphone (like the user's) and Maeve's real playback loudness.
        for frequency,rate,amplitude in ((400,16000,.003),(1600,24000,.08)):
            pcm=(np.sin(2*np.pi*frequency*np.arange(rate//50)/rate)*amplitude*32767).astype('<i2').tobytes()
            level,bands=audio_feedback(pcm,rate)
            feedback.append({'level':level,'bands':bands,'dominant':int(np.argmax(bands))})
        window.evaluate_js('window.qaMicFeedback=%s;window.qaOutputFeedback=%s;' % tuple(json.dumps(item) for item in feedback))
        window.evaluate_js('''window.qaErrors=[];window.addEventListener('error',e=>qaErrors.push(e.message));
          window.qaCalls=[];api=(name,...args)=>{qaCalls.push({name,args});
            if(name==='set_expanded')S.expanded=args[0];
            if(name==='confirm_review')S.review.sending=true;};
          document.body.style.background='#202329';''')
        states = ['loading','ready','hearing','transcribing','sending','waiting','speaking','reading','off','error','dictating','processing','done','failed']
        cases = [(state, dock, '') for dock in (False,True) for state in states]
        cases += [('ready',dock,panel) for dock in (False,True) for panel in ('card','menu','list','bubble','live','processing-preview','placeholder','review','failed-review')]
        for state, dock, panel in cases:
            width, height = ((200,48) if dock else (180,150))
            if panel in ('card','menu','list'):
                width,height = (320,270 if dock else 360)
                if panel=='list':height+=120
            elif panel:
                width,height = (340,214 if dock else 300)
            resize(width,height)
            window.evaluate_js('''(()=>{
              const [state,dock,panel]=%s;
              S=Object.assign(S,{state,dock,speaking:state==='speaking',expanded:['card','menu','list'].includes(panel),visible:true,
                mic:qaMicFeedback.level,out:qaOutputFeedback.level,micBands:qaMicFeedback.bands,outBands:qaOutputFeedback.bands,
                micMuted:false,maeveMuted:false,review:null,bubble:null});
              hovering=true;document.body.classList.add('hover');
              document.getElementById('menu').classList.toggle('open',panel==='menu');
              document.getElementById('list').classList.toggle('open',panel==='list');
              if(panel==='bubble')S.bubble={id:Date.now(),who:'you',text:'A longer reply '.repeat(50)};
              if(['live','processing-preview','placeholder'].includes(panel)){
                S.state=panel==='live'?'dictating':'processing';
                S.bubble={id:'live-preview',who:'you',live:panel==='live',processing:panel!=='live',
                  text:panel==='placeholder'?'Transcribing…':'The words I am saying appear above the orb while I hold the button.'};
              }
              if(['review','failed-review'].includes(panel))S.review={id:Date.now(),text:'Please check the Windows build and fix the cause.',
                title:'Selected thread',sending:false,error:panel==='failed-review'?'Temporary failure':''};
              render();
            })()''' % json.dumps([state,dock,panel]))
            time.sleep(.6 if panel else .25)
            ids = (['bar','barOrb','wave','barMic','barMaeve','barExpand'] if dock else ['muteMic','muteMaeve','toBar','orbWave'])
            ids += {'card':['card','delivery','fQuit'], 'menu':['card','menu'], 'list':['card','list'],
                    'bubble':['bubble'], 'live':['bubble'], 'processing-preview':['bubble'], 'placeholder':['bubble','btext'],
                    'review':['review','reviewSend'], 'failed-review':['review','reviewSend']}.get(panel,[])
            result = window.evaluate_js('''(()=>{
              const bad=[];for(const id of %s){const r=document.getElementById(id).getBoundingClientRect();
                if(!r.width||!r.height||r.left<-.5||r.top<-.5||r.right>innerWidth+.5||r.bottom>innerHeight+.5)bad.push({id,rect:r.toJSON()});}
              return {width:innerWidth,height:innerHeight,bad,errors:qaErrors.slice()};
            })()''' % json.dumps(ids))
            result.update(state=state,dock=dock,panel=panel)
            report['cases'].append(result)
            if result['bad'] or result['errors']:report['failures'].append(result)
            if panel in ('review','menu','live','processing-preview','placeholder') or state=='dictating':
                capture(('bar' if dock else 'orb')+'-'+(panel or state))
        # Exercise the devices overlay in both card sizes without native input or audio.
        for dock in (False, True):
            resize(320,270 if dock else 360)
            window.evaluate_js("S.review=null;S.bubble=null;S.dock=%s;S.expanded=true;render();" % json.dumps(dock))
            window.evaluate_js("""window.qaDeviceApi=api;
              api=async(name,...args)=>name==='audio_devices'?{
                inputs:[{name:'mic',label:'Microphone (USB Condenser Microphone)'}],
                outputs:[{name:'speaker',label:'Headphones (ULT WEAR)'}],mic:'mic',speaker:''}:qaDeviceApi(name,...args);
              openDevices();""")
            time.sleep(.6)
            device = window.evaluate_js("""(()=>{
              const ids=['devices','spkSel','micSel','devDone'],bad=[];
              for(const id of ids){const r=document.getElementById(id).getBoundingClientRect();
                if(!r.width||!r.height||r.left<0||r.top<0||r.right>innerWidth||r.bottom>innerHeight)bad.push(id);}
              const panel=devicesEl.getBoundingClientRect();
              for(const el of devicesEl.children){const r=el.getBoundingClientRect();if(r.bottom>panel.bottom||r.top<panel.top)bad.push(el.className);}
              return {bad,defaults:[spkSel,micSel].every(s=>s.options[0].value===''&&s.options[0].text==='System default'),
                selected:micSel.value==='mic'&&spkSel.value==='',errors:qaErrors.slice()};
            })()""")
            capture(('bar' if dock else 'orb')+'-devices')
            window.evaluate_js("applyExpanded(false);api=qaDeviceApi;")
            device['closesWithCard'] = window.evaluate_js("!devicesEl.classList.contains('open')")
            report.setdefault('devices',[]).append(device)
            if device['bad'] or device['errors'] or not all(device[k] for k in ('defaults','selected','closesWithCard')):
                report['failures'].append({'devices':device})
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
        mask = window.evaluate_js('''(()=>{
          S.review=null;render();
          S.bubble={id:'top-line-mask',who:'you',processing:true,text:'Transcribing…'};tickBubble(.01);
          const shortMask=getComputedStyle(btext).maskImage;
          S.bubble.text='Every line should remain readable, with no dark fade at the top. '.repeat(25);tickBubble(.01);
          return {shortMask,mask:getComputedStyle(btext).maskImage,webkitMask:getComputedStyle(btext).webkitMaskImage};
        })()''')
        report['textMask']=mask
        if mask['shortMask']!='none' or mask['mask']=='none' or mask['webkitMask']=='none':report['failures'].append({'textMask':mask})
        words = window.evaluate_js('''(()=>{
          S.bubble={id:'animated-words',who:'you',live:true,text:'Please inspect this'};tickBubble(.1);
          const first=btext.querySelector('.word');
          S.bubble.text='Please inspect this issue';tickBubble(.1);
          const appended=btext.querySelector('.word:last-of-type');
          const stablePrefix=!!first&&first===btext.querySelector('.word');
          S.bubble.text='Please inspect that issue';tickBubble(.1);
          return {stablePrefix,animated:!!appended&&getComputedStyle(appended).animationName==='ink',
            revised:btext.textContent==='Please inspect that issue',errors:qaErrors.slice()};
        })()''')
        report['words']=words
        if not all(words[key] for key in ('stablePrefix','animated','revised')) or words['errors']:
            report['failures'].append({'words':words})
        resize(340,300)
        window.evaluate_js('''S.review=null;S.expanded=false;applyExpanded(false);S.dock=false;S.state='speaking';render();
          window.qaLayoutTick=tickBubble;tickBubble=()=>{};
          S.bubble={id:'stable-word-layout',who:'maeve',text:'These words stay fixed while the next words appear in the speech bubble.'};
          qaLayoutTick(1);''')
        time.sleep(.7)
        window.evaluate_js('''window.qaTextPositions=[];window.qaTextPosition=()=>{
          qaTextPositions.push({word:btext.querySelector('.word').getBoundingClientRect().top,
            panel:bubbleEl.getBoundingClientRect().top,scroll:btext.scrollTop});
          };qaTextPosition();qaLayoutTick(.34);qaTextPosition();''')
        time.sleep(.15)
        window.evaluate_js('qaTextPosition();')
        time.sleep(.4)
        window.evaluate_js('''qaTextPosition();for(let i=0;i<7;i++){qaLayoutTick(.34);qaTextPosition();}''')
        time.sleep(.65)
        layout = window.evaluate_js('''(()=>{qaTextPosition();tickBubble=qaLayoutTick;
          return {positions:qaTextPositions,errors:qaErrors.slice()};})()''')
        report['textLayout']=layout
        if (max(p['word'] for p in layout['positions'])-min(p['word'] for p in layout['positions'])>.75
                or max(p['panel'] for p in layout['positions'])-min(p['panel'] for p in layout['positions'])>.75
                or layout['errors']):
            report['failures'].append({'textLayout':layout})
        window.evaluate_js('''S.review=null;S.expanded=false;applyExpanded(false);S.dock=false;S.state='dictating';S.mic=0;S.micBands=Array(11).fill(0);render();''')
        resize(340,300)
        window.evaluate_js('''window.qaWaveHeight=()=>{
          const canvas=document.getElementById('orbWave');if(!canvas)return 0;
          const pixels=canvas.getContext('2d').getImageData(0,0,canvas.width,canvas.height).data;
          let top=canvas.height,bottom=-1;
          for(let y=0;y<canvas.height;y++)for(let x=0;x<canvas.width;x++)if(pixels[(y*canvas.width+x)*4+3]>20){top=Math.min(top,y);bottom=Math.max(bottom,y);}
          return Math.max(0,bottom-top+1);
        };''')
        time.sleep(1.1)
        window.evaluate_js('''window.qaBandHeights=()=>{
          const canvas=document.getElementById('orbWave'),ctx=canvas.getContext('2d');
          return Array.from({length:11},(_,i)=>{
            const x0=Math.floor(i*canvas.width/11),x1=Math.floor((i+1)*canvas.width/11);
            const pixels=ctx.getImageData(x0,0,Math.max(1,x1-x0),canvas.height).data,w=Math.max(1,x1-x0);
            let best=0;for(let x=0;x<w;x++){let top=canvas.height,bottom=-1;
              for(let y=0;y<canvas.height;y++)if(pixels[(y*w+x)*4+3]>20){top=Math.min(top,y);bottom=Math.max(bottom,y);}
              best=Math.max(best,bottom-top+1);}
            return Math.max(0,best);
          });
        };
        window.qaBandPeaks=()=>new Promise(done=>{let best=new Array(11).fill(0),n=0;
          const step=()=>{qaBandHeights().forEach((h,i)=>best[i]=Math.max(best[i],h));if(++n<14)setTimeout(step,35);else done(best);};step();});
          window.qaQuietRadius=gl.getUniform(prog,U.uR);window.qaQuietWave=qaWaveHeight();
          S.mic=qaMicFeedback.level;S.micBands=qaMicFeedback.bands;render();''')
        time.sleep(.8)
        window.evaluate_js("qaBandPeaks().then(p=>{window.qaPeaks=p;})")
        time.sleep(.7)
        audio = window.evaluate_js('''(()=>{
          const wave=document.getElementById('orbWave');
          return {radiusRatio:gl.getUniform(prog,U.uR)/qaQuietRadius,
            waveform:!!wave&&getComputedStyle(wave).opacity==='1',
            quietWave:qaQuietWave,voiceWave:qaWaveHeight(),bandHeights:window.qaPeaks,
            expectedBand:qaMicFeedback.dominant,errors:qaErrors.slice()};
        })()''')
        report['audio']=audio
        if (audio['radiusRatio']<1.04 or not audio['waveform'] or audio['voiceWave']<=audio['quietWave']
                or not mirrored_peak_ok(audio['bandHeights'], audio['expectedBand']) or audio['errors']):
            report['failures'].append({'audio':audio})
        window.evaluate_js('''S.bubble={id:'motion-capture',who:'you',live:true,text:'Your voice moves the orb. New words rise gently into view.'};tickBubble(.01);''')
        time.sleep(.1)
        capture('orb-words-in')
        time.sleep(.55)
        capture('orb-words-settled')
        window.evaluate_js('S.mic=.08;render();')
        time.sleep(.35)
        alpha = window.evaluate_js('''(()=>{
          const pixels=new Uint8Array(cv.width*cv.height*4);gl.readPixels(0,0,cv.width,cv.height,gl.RGBA,gl.UNSIGNED_BYTE,pixels);
          let invalid=0;for(let i=0;i<pixels.length;i+=4)if(Math.max(pixels[i],pixels[i+1],pixels[i+2])>pixels[i+3]+1)invalid++;
          return {invalid,error:gl.getError()};
        })()''')
        report['alpha']=alpha
        if alpha['invalid'] or alpha['error']:report['failures'].append({'alpha':alpha})
        window.evaluate_js('''S.state='ready';S.speaking=false;S.mic=0;S.out=0;S.bubble=null;render();''')
        time.sleep(1.1)
        window.evaluate_js('''window.qaPlaybackQuiet=gl.getUniform(prog,U.uR);
          S.state='done';S.speaking=true;S.out=qaOutputFeedback.level;S.outBands=qaOutputFeedback.bands;
          S.bubble={id:'playback-end',who:'maeve',text:'These final words remain steady as the spoken reply finishes.'};render();tickBubble(1);
          window.qaBeforeFinish=shown;S.speaking=false;S.state='ready';tickBubble(.2);
          window.qaFinishAdvance=shown-qaBeforeFinish;
          S.speaking=true;S.state='done';render();''')
        time.sleep(.7)
        window.evaluate_js("qaBandPeaks().then(p=>{window.qaPeaks=p;})")
        time.sleep(.7)
        playback = window.evaluate_js('''({waveform:getComputedStyle(orbWave).opacity==='1',
          radiusRatio:gl.getUniform(prog,U.uR)/qaPlaybackQuiet,
          bandHeights:window.qaPeaks,expectedBand:qaOutputFeedback.dominant,
          finishAdvance:qaFinishAdvance,errors:qaErrors.slice()})''')
        report['playback']=playback
        if (not playback['waveform'] or playback['radiusRatio']<1.04 or playback['finishAdvance']>.61
                or not mirrored_peak_ok(playback['bandHeights'], playback['expectedBand']) or playback['errors']):
            report['failures'].append({'playback':playback})
        window.evaluate_js('''S.speaking=false;S.state='ready';S.out=0;render();tickBubble(10);S.bubble=null;tickBubble(0);''')
        exit_opacity=[]
        for delay in (.04,.08,.12):
            time.sleep(delay)
            exit_opacity.append(window.evaluate_js("Number(getComputedStyle(bubbleEl).opacity)"))
        report['exitOpacity']=exit_opacity
        if any(later>earlier+.01 for earlier,later in zip(exit_opacity,exit_opacity[1:])) or exit_opacity[-1]>.01:
            report['failures'].append({'exitOpacity':exit_opacity})
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
        window.evaluate_js('''qaTransitions.pointerLeaveStaysOpen=expanded;
          document.documentElement.matches=qaOriginalMatches;qaTransitions.errors=qaErrors.slice();''')
        transitions = window.evaluate_js('qaTransitions')
        window.evaluate_js('S.expanded=false;render();')
        report['transitions'] = transitions
        if (not transitions['staysClosed'] or not transitions['latestClickWins']
                or transitions['writes'] != [False,True,False]
                or not all(transitions[key] for key in ('oldPollAfterAckStaysClosed','pollDuringWriteStaysClosed','pointerLeaveStaysOpen'))
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
          reviewText.value='Edited preview';reviewTextChanged();sendReview();sendReview();render();
          const confirms=qaCalls.filter(c=>c.name==='confirm_review');
          const editedDraft=qaCalls.some(c=>c.name==='update_review_text'&&c.args[1]==='Edited preview');
          const result={editedDraft,calls:qaCalls.slice(),confirms:confirms.length,edited:confirms[0]?.args[1],
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
                or not actions['editedDraft'] or actions['edited']!='Edited preview' or not actions['disabled'] or actions['missingRoles']
                or actions['legacyPillToggle'] or actions['legacyHandsfreeControl'] or actions['errors']):
            report['failures'].append({'actions':actions})
        # Native resizing may take much longer than 90 ms; never paint a card in orb space.
        resize(180,150)
        window.evaluate_js("""S.review=null;S.dock=false;S.expanded=false;applyExpanded(false);render();
          window.qaSavedResizeApi=api;
          api=async(name,...args)=>name==='set_expanded'?{expanded:args[0],size:[320,360]}:qaSavedResizeApi(name,...args);
          setExpanded(true);""")
        time.sleep(.25)
        resizeRace=window.evaluate_js("({hiddenUntilResize:!card.classList.contains('open'),stillWanted:wantExpanded})")
        resize(320,360)
        time.sleep(.25)
        resizeRace['opensAfterResize']=window.evaluate_js("card.classList.contains('open')")
        window.evaluate_js("""window.qaExitWrites=[];window.qaExitStarted=performance.now();
          api=async(name,...args)=>{
            if(name==='set_expanded'){qaExitWrites.push({expanded:args[0],elapsed:performance.now()-qaExitStarted,opacity:Number(getComputedStyle(card).opacity)});return {expanded:args[0],size:[320,360]};}
            return qaSavedResizeApi(name,...args);
          };setExpanded(false);""")
        time.sleep(.04)
        exitAnimation=window.evaluate_js("({fading:getComputedStyle(card).visibility==='visible'&&Number(getComputedStyle(card).opacity)>0,heldSize:qaExitWrites.length===0,opacity:Number(getComputedStyle(card).opacity)})")
        time.sleep(.20)
        exitAnimation.update(window.evaluate_js("({hidden:getComputedStyle(card).visibility==='hidden',closedAfterFade:qaExitWrites.some(w=>!w.expanded&&w.elapsed>=100&&w.opacity<=.01)})"))
        report['settingsExit']=exitAnimation
        if not all(exitAnimation[k] for k in ('fading','heldSize','hidden','closedAfterFade')):report['failures'].append({'settingsExit':exitAnimation})
        rapid=window.evaluate_js("""(()=>{
          if(typeof toggleSettings!=='function')return false;
          toggleSettings();toggleSettings();return !wantExpanded&&!card.classList.contains('open');
        })()""")
        time.sleep(.2)
        resizeRace['doubleTapCancels']=rapid and window.evaluate_js("!expanded&&!card.classList.contains('open')")
        resizeRace['noClosingGhost']=window.evaluate_js("getComputedStyle(card).visibility==='hidden'")
        resizeRace['singleCanvasActivation']=window.evaluate_js("""(()=>{
          if(typeof handleOrbClick!=='function')return false;
          let stopped=false;dragStart=null;
          handleOrbClick({screenX:0,screenY:0,stopPropagation:()=>{stopped=true;}});
          const once=wantExpanded;toggleSettings();return stopped&&once&&!wantExpanded;
        })()""")
        resizeRace['preciseHover']=window.evaluate_js("""(()=>{
          const r=cv.getBoundingClientRect();
          return pointerOverControls(r.left+CX,r.top+CY)&&!pointerOverControls(r.left+2,r.top+2);
        })()""")
        resizeRace['staleHoverPoll']=window.evaluate_js("""(()=>{
          setHover(true);const old=hoverGeneration;setHover(false);
          acceptSnapshot({...S,hovered:true},settingsGeneration,false,appearanceGeneration,false,old,false);
          return !hovering&&!document.body.classList.contains('hover');
        })()""")

        resizeRace['lateOpenCannotUndoClose']=window.evaluate_js("""(()=>{
          acceptSnapshot({...S,expanded:true},settingsGeneration,false);
          const closed=!expanded&&!wantExpanded&&!card.classList.contains('open');
          if(!closed)setExpanded(false);
          return closed;
        })()""")
        window.evaluate_js('setExpanded(true);')
        time.sleep(.28)
        window.evaluate_js('qaExitWrites=[];setExpanded(false);')
        time.sleep(.04)
        window.evaluate_js('setExpanded(true);')
        time.sleep(.12)
        reversal=window.evaluate_js("({reversedInPlace:wantExpanded&&expanded&&card.classList.contains('open')&&Number(getComputedStyle(card).opacity)>.1,noShrink:!qaExitWrites.some(w=>!w.expanded)})")
        report['exitReversal']=reversal
        if not all(reversal.values()):report['failures'].append({'exitReversal':reversal})
        window.evaluate_js('setExpanded(false);')
        time.sleep(.22)
        window.evaluate_js('S.reducedMotion=true;render();setExpanded(true);')
        time.sleep(.06)
        window.evaluate_js('qaExitWrites=[];qaExitStarted=performance.now();setExpanded(false);')
        time.sleep(.05)
        instant=window.evaluate_js("getComputedStyle(card).visibility==='hidden'&&qaExitWrites.some(w=>!w.expanded&&w.elapsed<80)")
        report['reducedMotionExit']=instant
        if not instant:report['failures'].append({'reducedMotionExit':instant})
        window.evaluate_js('S.reducedMotion=false;render();')
        window.evaluate_js('setExpanded(true);')
        time.sleep(.28)
        window.evaluate_js("qaExitWrites=[];acceptSnapshot({...S,expanded:true,settingsCloseRequest:99},settingsGeneration,false);")
        time.sleep(.04)
        nativeExit=window.evaluate_js("({fading:card.classList.contains('closing')&&Number(getComputedStyle(card).opacity)>0,held:!qaExitWrites.some(w=>!w.expanded)})")
        time.sleep(.22)
        nativeExit['closedAfterFade']=window.evaluate_js("getComputedStyle(card).visibility==='hidden'&&qaExitWrites.some(w=>!w.expanded&&w.opacity<=.01)")
        report['nativeSettingsExit']=nativeExit
        if not all(nativeExit.values()):report['failures'].append({'nativeSettingsExit':nativeExit})
        window.evaluate_js('api=qaSavedResizeApi;')
        report['resizeRace']=resizeRace
        if not all(resizeRace.values()):report['failures'].append({'resizeRace':resizeRace})
        gestures=window.evaluate_js("""(()=>{
          if(typeof beginOrbGesture!=='function')return {supported:false};
          window.qaGestureApi=api;window.qaGestureCalls=[];
          api=(name,...args)=>{qaGestureCalls.push({name,args});return Promise.resolve();};
          const event=(x,y)=>({button:0,pointerId:7,screenX:x,screenY:y,currentTarget:{setPointerCapture:()=>{}},stopPropagation:()=>{}});
          beginOrbGesture(event(100,100));moveOrbGesture(event(103,102));endOrbGesture(event(103,102));
          const tapDoesNotMove=!qaGestureCalls.some(c=>c.name==='drag_window');
          beginOrbGesture(event(100,100));moveOrbGesture(event(112,108));endOrbGesture(event(112,108));
          const before=wantExpanded;handleOrbClick(event(112,108));
          const dragDoesNotToggle=wantExpanded===before;
          api=qaGestureApi;
          return {supported:true,tapDoesNotMove,dragDoesNotToggle};
        })()""")
        report['dragGestures']=gestures
        if not all(gestures.values()):report['failures'].append({'dragGestures':gestures})
        # An old poll must not undo a just-clicked appearance preference.
        appearanceRace=window.evaluate_js("""(()=>{
          const savedApi=api;api=()=>new Promise(()=>{});
          document.getElementById('contrastSel').checked=true;
          document.getElementById('motionSel').checked=true;
          const oldAppearanceGeneration=typeof appearanceGeneration==='number'?appearanceGeneration:0;
          saveAppearance();
          const before={...S};
          acceptSnapshot({...S,highContrast:false,reducedMotion:false},settingsGeneration,false,oldAppearanceGeneration);
          const preserved=S.highContrast&&S.reducedMotion;
          // End the synthetic pending write without any external preference mutation.
          api=savedApi;appearanceWrites=Promise.resolve();
          if(typeof appearancePending==='number')appearancePending=0;
          S=before;S.highContrast=false;S.reducedMotion=false;render();
          return {preserved};
        })()""")
        report['appearanceRace']=appearanceRace
        if not appearanceRace['preserved']:report['failures'].append({'appearanceRace':appearanceRace})
        resize(340,300)
        window.evaluate_js("S.review=null;S.expanded=false;S.dock=false;S.speaking=false;S.state='ready';S.bubble=null;S.agent={activity:'thinking',producing:false};render();")
        time.sleep(.7)
        features = window.evaluate_js("""(()=>{
          if(typeof effectState!=='function'||typeof threadAccent!=='function')return {missing:'visual effects',ok:false};
          const thinking=visualState()==='thinking'&&effectState(1000).thinking;
          S.speaking=true;
          const playbackOverlap=['processing','transcribing','sending'].every(state=>{S.state=state;return visualState()==='speaking';});
          S.speaking=false;S.state='ready';
          S.agent={activity:'approval',approval:true};render();
          const approval=visualState()==='approval'&&cap.textContent.toLowerCase().includes('approval');
          S.agent={activity:'input',needsInput:true};render();
          const question=visualState()==='input';
          const accentStable=JSON.stringify(threadAccent('thread-a'))===JSON.stringify(threadAccent('thread-a'));
          const accentDistinct=JSON.stringify(threadAccent('thread-a'))!==JSON.stringify(threadAccent('thread-b'));
          S.visualEvents={sent:1,interrupt:0};effectState(1000);S.visualEvents.sent=2;
          const ripple=effectState(1100).ripple>0;effectState(1200);
          const noRetrigger=effectState(2500).ripple===0;
          S.visualEvents.interrupt=1;const contraction=effectState(2600).contraction>0;
          S.reducedMotion=true;S.highContrast=true;render();
          const calm=effectState(3000);
          const motionStops=calm.time===0&&calm.ripple===0&&calm.contraction===0&&calm.trail===0;
          const contrast=document.body.classList.contains('high-contrast')&&getComputedStyle(document.body).getPropertyValue('--muted').trim()==='#e0e6ef';
          const reduced=document.body.classList.contains('reduced-motion');
          S.bubble={id:'calm-words',who:'you',live:true,text:'Words stay readable'};tickBubble(.1);
          const calmWords=getComputedStyle(btext.querySelector('.word')).animationName==='none';
          S.reducedMotion=false;S.highContrast=false;S.agent={activity:'idle'};render();
          return {thinking,playbackOverlap,approval,question,accentStable,accentDistinct,ripple,noRetrigger,contraction,motionStops,contrast,reduced,calmWords,errors:qaErrors.slice()};
        })()""")
        report['visualFeatures']=features
        if not all(v for k,v in features.items() if k!='errors') or features.get('errors'):
            report['failures'].append({'visualFeatures':features})
        window.evaluate_js("S.state='ready';S.speaking=false;S.agent={activity:'thinking',producing:true};S.bubble=null;S.visible=true;hovering=false;document.body.classList.remove('hover');render();")
        time.sleep(.6)
        capture('orb-thinking-trail')
        shader = window.evaluate_js("({thinking:gl.getUniform(prog,U.uThinking),trail:gl.getUniform(prog,U.uBusy),particles:[...pctx.getImageData(0,0,parts.width,parts.height).data].filter((v,i)=>i%4===3&&v>35).length,linked:gl.getProgramParameter(prog,gl.LINK_STATUS),error:gl.getError()})")
        glow=window.evaluate_js("""(()=>{
          const blue=gl.getUniform(prog,U.uB),center=gl.getUniform(prog,U.uCenter),radius=gl.getUniform(prog,U.uR),pixel=new Uint8Array(4);
          gl.drawArrays(gl.TRIANGLE_STRIP,0,4);
          gl.readPixels(Math.floor(center[0]+radius*1.12),Math.floor(center[1]),1,1,gl.RGBA,gl.UNSIGNED_BYTE,pixel);
          return {blue:blue[2]>.9&&blue[1]>.5&&blue[0]<.3,halo:pixel[3]>10};
        })()""")
        report['thinkingBlueGlow']=glow
        if not all(glow.values()):report['failures'].append({'thinkingBlueGlow':glow})
        window.evaluate_js("S.agent={activity:'approval',approval:true};render();")
        time.sleep(.5)
        capture('orb-approval-glow')
        shader['approval'] = window.evaluate_js('gl.getUniform(prog,U.uApproval)>0')
        window.evaluate_js("S.reducedMotion=true;S.highContrast=true;render();")
        time.sleep(.5)
        capture('orb-high-contrast-calm')
        calm = window.evaluate_js("""(()=>{
          const rgba=pctx.getImageData(0,0,parts.width,parts.height).data;
          return {time:gl.getUniform(prog,U.uTime),flow:gl.getUniform(prog,U.uFlow),trail:gl.getUniform(prog,U.uBusy),
            particlesClear:!rgba.some((v,i)=>i%4===3&&v>0),radius:gl.getUniform(prog,U.uR)};
        })()""")
        time.sleep(.4)
        calm['stableRadius'] = window.evaluate_js('gl.getUniform(prog,U.uR)')==calm['radius']
        report['shaderVisuals']={'shader':shader,'calm':calm}
        if (shader['thinking']!=1 or shader['trail']!=0 or shader['particles']<20 or not shader['linked'] or not shader['approval'] or shader['error']
                or any(calm[k]!=0 for k in ('time','flow','trail')) or not calm['particlesClear'] or not calm['stableRadius']):
            report['failures'].append({'shaderVisuals':report['shaderVisuals']})
        resize(340,214)
        window.evaluate_js("S.reducedMotion=false;S.highContrast=false;S.agent={activity:'idle'};S.dock=true;S.speaking=true;S.out=qaOutputFeedback.level;S.outBands=qaOutputFeedback.bands;S.playback={active:true,fraction:.45};render();")
        time.sleep(.5)
        capture('bar-gradient-playback')
        progress = window.evaluate_js("({value:document.getElementById('playbackTrack').getAttribute('aria-valuenow'),active:document.getElementById('playbackTrack').classList.contains('active')})")
        window.evaluate_js("S.playback.fraction=null;render();")
        progress['indeterminate'] = window.evaluate_js("document.getElementById('playbackTrack').classList.contains('indeterminate')&&!document.getElementById('playbackTrack').hasAttribute('aria-valuenow')")
        report['playbackProgress']=progress
        if progress['value']!='45' or not progress['active'] or not progress['indeterminate']:
            report['failures'].append({'playbackProgress':progress})
        resize(340,300)
        window.evaluate_js("S.dock=false;S.speaking=false;S.state='ready';S.playback=null;S.agent={activity:'idle'};S.bubble={id:'scroll-reading',who:'you',live:true,text:'Read this long message at your own pace. '.repeat(70)};render();tickBubble(.1);btext.scrollTop=0;")
        time.sleep(.3)
        window.evaluate_js("S.bubble.text+=' A new final sentence.';tickBubble(.1);")
        scrolling=window.evaluate_js("({atTop:btext.scrollTop===0,firstLineReadable:getComputedStyle(btext).maskImage==='none',capped:bubbleText.clientHeight===113})")
        window.evaluate_js('btext.scrollTop=btext.scrollHeight;')
        time.sleep(.3)
        scrolling['fadeAfterScroll']=window.evaluate_js("getComputedStyle(btext).maskImage!=='none'")
        window.evaluate_js('S.bubble.live=false;tickBubble(.1);')
        scrolling['settles']=window.evaluate_js("bubbleEl.classList.contains('settled')")
        capture('orb-final-text-scroll')
        report['bubbleScrolling']=scrolling
        if not all(scrolling.values()):report['failures'].append({'bubbleScrolling':scrolling})
        # Appearance overlay fits the same native cards as the audio device overlay.
        for dock in (False,True):
            resize(320,270 if dock else 360)
            window.evaluate_js("S.dock=%s;S.bubble=null;S.expanded=true;render();if(typeof openAppearance==='function')openAppearance();" % json.dumps(dock))
            time.sleep(.5)
            appearance = window.evaluate_js("""(()=>{
              const panel=document.getElementById('appearance');if(!panel)return {missing:true};
              const bad=[];for(const el of [panel,...panel.querySelectorAll('button,input,label')]){
                const r=el.getBoundingClientRect();if(!r.width||!r.height||r.top<0||r.bottom>innerHeight||r.left<0||r.right>innerWidth)bad.push(el.id||el.tagName);}
              return {bad,open:panel.classList.contains('open'),named:[...panel.querySelectorAll('input')].every(el=>!!el.labels?.length)};
            })()""")
            report.setdefault('appearance',[]).append(appearance)
            capture(('bar' if dock else 'orb')+'-appearance')
            window.evaluate_js('applyExpanded(false);')
            if appearance.get('missing') or appearance.get('bad') or not appearance.get('open') or not appearance.get('named'):
                report['failures'].append({'appearance':appearance})
        # A light desktop exposes any shadow abruptly clipped at a transparent window edge.
        resize(340,300)
        window.evaluate_js("""S.dock=false;S.expanded=false;S.review=null;S.highContrast=false;S.reducedMotion=false;
          S.agent={activity:'idle'};S.state='ready';S.speaking=false;S.micMuted=false;S.maeveMuted=false;
          S.bubble={id:'light-shadow',who:'maeve',text:'A readable glass bubble with a soft shadow that vanishes before the window ends.'};
          document.body.style.background='#e6e6e6';render();tickBubble(10);""")
        time.sleep(.7)
        capture('orb-shadow-light')
        from PIL import Image
        with Image.open(OUT/'orb-shadow-light.png') as shot:
            pixels=shot.convert('RGB')
            edge_deviation=max(abs(channel-230) for x in (0,pixels.width-1) for y in range(pixels.height) for channel in pixels.getpixel((x,y)))
        report['windowShadow']={'edgeDeviation':edge_deviation}
        if edge_deviation>1:report['failures'].append({'windowShadow':report['windowShadow']})
        # Exercise the real native placement code on this isolated QA window, without input.
        from t3_voice import Engine,MONITORINFO,CARD,COMPACT
        native=Engine.__new__(Engine)
        native.hwnd=window.native.Handle.ToInt32();native.size=None;native.orb_anchor=None
        area=MONITORINFO();area.size=ctypes.sizeof(area)
        user32.MonitorFromWindow.argtypes=[ctypes.wintypes.HWND,ctypes.c_uint]
        user32.MonitorFromWindow.restype=ctypes.wintypes.HMONITOR
        user32.GetMonitorInfoW.argtypes=[ctypes.wintypes.HMONITOR,ctypes.POINTER(MONITORINFO)]
        monitor=user32.MonitorFromWindow(native.hwnd,2)
        if not user32.GetMonitorInfoW(monitor,ctypes.byref(area)):raise RuntimeError('Monitor work area unavailable')
        scale=native.scale()
        native.place(COMPACT,anchor=(area.work.right-round(120*scale),area.work.bottom-8))
        positions=[]
        for i in range(20):
            for size in (CARD,COMPACT):
                native.place(size)
                rect=ctypes.wintypes.RECT();user32.GetWindowRect(native.hwnd,ctypes.byref(rect))
                positions.append(((rect.left+rect.right)/2,rect.bottom))
        nativeGeometry={'centreDrift':max(p[0] for p in positions)-min(p[0] for p in positions),
                        'bottomDrift':max(p[1] for p in positions)-min(p[1] for p in positions),'resizes':len(positions)}
        report['nativeGeometry']=nativeGeometry
        if nativeGeometry['centreDrift']>.5 or nativeGeometry['bottomDrift']>0:
            report['failures'].append({'nativeGeometry':nativeGeometry})
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
