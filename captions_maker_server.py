from pathlib import Path
import json, os, re, shutil, subprocess, tempfile, threading, time, uuid
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parent
PROJECTS = ROOT / 'caption_projects'; PROJECTS.mkdir(exist_ok=True)
SETTINGS_FILE = ROOT / 'ai_settings.json'
MODEL_SIZE = os.environ.get('WHISPER_MODEL', 'small')
_model = None; _lock = threading.Lock()

class TranscriptionCancelled(Exception):
    pass

def get_model():
    global _model
    with _lock:
        if _model is None:
            from faster_whisper import WhisperModel
            device = os.environ.get('WHISPER_DEVICE', 'cpu')
            compute = os.environ.get('WHISPER_COMPUTE', 'int8' if device == 'cpu' else 'float16')
            print(f'Loading Whisper {MODEL_SIZE} on {device}/{compute}...', flush=True)
            _model = WhisperModel(MODEL_SIZE, device=device, compute_type=compute)
    return _model

def write_progress(target, **fields):
    """target = project folder OR full path to progress.json."""
    try:
        p = target if str(target).endswith('progress.json') else target / 'progress.json'
        p.write_text(json.dumps(fields, ensure_ascii=False), encoding='utf8')
    except OSError:
        pass

def read_progress(target):
    """target = project folder OR full path to progress.json."""
    p = target if str(target).endswith('.json') else target / 'progress.json'
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding='utf8'))
    except Exception:
        return {}

def transcribe(path, language='auto', progress_file=None, cancel_file=None):
    kwargs = dict(beam_size=5, vad_filter=True, word_timestamps=True, condition_on_previous_text=True)
    if language and language != 'auto': kwargs['language'] = language
    if progress_file:
        write_progress(progress_file, stage='loading_model', percent=0, message='Memuat model Whisper…')
    segs, info = get_model().transcribe(str(path), **kwargs)
    result=[]
    total = None
    for si, seg in enumerate(segs):
        if cancel_file and Path(cancel_file).exists():
            raise TranscriptionCancelled('Transcription dibatalkan')
        words=[]
        for w in (seg.words or []):
            text=w.word.strip()
            if text: words.append({'word':text,'start':round(w.start,3),'end':round(w.end,3),'confidence':round(float(w.probability or 0),3)})
        if words:
            result.append({'start':round(seg.start,3),'end':round(seg.end,3),'text':seg.text.strip(),'words':words})
        if progress_file:
            percent = None if total is None else round(100 * (si + 1) / total, 1)
            write_progress(progress_file, stage='transcribing', segments_done=len(result),
                           percent=percent, message=f'Segmen {len(result)}…')
    if progress_file:
        write_progress(progress_file, stage='done', percent=100, message='Selesai')
    return {'language':info.language,'language_probability':round(float(info.language_probability),3),'segments':result,'model':MODEL_SIZE}

def ass_time(s):
    h=int(s//3600); m=int((s%3600)//60); sec=s%60
    return f'{h}:{m:02d}:{sec:05.2f}'

def srt_time(s):
    ms = int(round(s * 1000))
    h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); sec, ms = divmod(ms, 1000)
    return f'{h:02d}:{m:02d}:{sec:02d},{ms:03d}'

def ass_escape(text): return text.replace('\\','\\\\').replace('{','\\{').replace('}','\\}')

def caption_word(text):
    # Keep captions visually clean: remove sentence punctuation before burn-in.
    return re.sub(r'[\\.,!?;:،。！？；：]+', '', str(text)).strip()

def hex_to_ass(hexcolor):
    """Convert '#rrggbb' (or 'rrggbb') to ASS &H00BBGGRR. Pass through ASS-form colors unchanged."""
    if not hexcolor:
        return hexcolor
    h = str(hexcolor).strip()
    if h.startswith('&H') or h.startswith('&h'):
        return h
    if h.startswith('#'):
        h = h[1:]
    h = h.lstrip('#')[:6]
    if len(h) != 6 or not re.fullmatch(r'[0-9a-fA-F]{6}', h):
        return hexcolor
    r, g, b = h[0:2], h[2:4], h[4:6]
    return '&H00' + b.upper() + g.upper() + r.upper()

def make_srt(data):
    lines=[]
    for i, seg in enumerate(data.get('segments', []), 1):
        start = max(0.0, float(seg.get('start', 0)))
        end = float(seg.get('end', start + 1))
        text = ' '.join(w.get('word','') for w in seg.get('words', [])) or str(seg.get('text','')).strip()
        if not text:
            continue
        lines.append(f'{i}\n{srt_time(start)} --> {srt_time(end)}\n{text}\n')
    return '\n'.join(lines)

def make_ass(data, style):
    font=style.get('font','Impact'); size=int(style.get('size',100))
    color=hex_to_ass(style.get('color','&H0000FFFF')); accent=hex_to_ass(style.get('accent', style.get('color','&H0000FFFF')))
    outline=int(style.get('outline',3)); shadow=int(style.get('shadow',0))
    align=int(style.get('align',5)); margin=int(style.get('margin',80)); y=int(style.get('y',960))
    # Use an explicit fixed anchor on the 1080x1920 canvas. This prevents
    # vertical drift when words/scenes change or glyph heights differ.
    x=540 if align in (5,8,2) else (margin if align in (1,4,7) else 1080-margin)
    anchor=5 if align in (5,8,2) else (4 if align in (1,4,7) else 6)
    header=(f'[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,{font},{size},{color},{color},&H00101010,&H80101010,1,0,0,0,100,100,0,0,1,{outline},{shadow},{anchor},{margin},{margin},{margin},1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n')
    lines=[]
    words_per_caption=max(1,int(style.get('words_per_caption',1)))
    all_words=[]
    for seg in data.get('segments',[]): all_words.extend(seg.get('words',[]))
    # Create short, readable events. Default is exactly one word per caption.
    groups=[]
    for i in range(0,len(all_words),words_per_caption):
        group=all_words[i:i+words_per_caption]
        if group: groups.append(group)
    # Never let adjacent caption events overlap. A small gap gives the eye a
    # clean handoff and prevents the previous word from flashing into the next.
    gap=float(style.get('caption_gap',0.025))
    min_duration=float(style.get('min_caption_duration',0.12))
    for i,group in enumerate(groups):
        start=max(0.0,float(group[0]['start']))
        raw_end=max(start+min_duration,float(group[-1]['end']))
        next_start=float(groups[i+1][0]['start']) if i+1<len(groups) else None
        if next_start is not None:
            end=min(raw_end,next_start-gap)
            if end <= start:
                end=max(start+0.04,next_start-gap)
        else:
            end=raw_end+0.02
        text=' '.join(ass_escape(caption_word(w['word']).upper()) for w in group)
        # Hard cut: no fade-in or fade-out between caption events.
        text='{\\an5\\pos('+str(x)+','+str(y)+')\\1c'+color+'\\2c'+accent+'}'+text
        lines.append(f'Dialogue: 0,{ass_time(start)},{ass_time(end)},Default,,0,0,0,,{text}')
    return header+'\n'.join(lines)+'\n'

def multipart(handler):
    length=int(handler.headers.get('Content-Length','0')); body=handler.rfile.read(length)
    match=re.search(br'name="file"; filename="([^"]*)"',body)
    if not match: raise ValueError('file field missing')
    filename=Path(match.group(1).decode('utf8','ignore')).name or 'video.mp4'
    parts=body.split(b'\r\n\r\n',1)
    if len(parts)!=2: raise ValueError('invalid multipart upload')
    data=parts[1].rsplit(b'\r\n--',1)[0]
    return filename,data

def send_json(h, code, obj):
    raw=json.dumps(obj,ensure_ascii=False).encode(); h.send_response(code); h.send_header('Content-Type','application/json'); h.send_header('Content-Length',str(len(raw))); h.end_headers(); h.wfile.write(raw)

def public_settings():
    if not SETTINGS_FILE.exists(): return {'provider':'OpenAI-compatible','base_url':'https://api.openai.com/v1','model':'gpt-4o-mini','has_api_key':False,'has_pexels_key':False,'has_pixabay_key':False}
    try:
        data=json.loads(SETTINGS_FILE.read_text(encoding='utf8'))
        return {'provider':data.get('provider','OpenAI-compatible'),'base_url':data.get('base_url',''),'model':data.get('model',''),'has_api_key':bool(data.get('api_key')),'has_pexels_key':bool(data.get('pexels_key')),'has_pixabay_key':bool(data.get('pixabay_key'))}
    except Exception: return {'provider':'OpenAI-compatible','base_url':'','model':'','has_api_key':False}

def relevance_terms(query):
    stop={'surprising','close','up','footage','video','vertical','wildlife','science','explanation','environment','detail','research','call','to','action','stock','image','photo','cinematic','hook','reveal','proof','fact','the','a','an','and','of','for'}
    return [x.lower() for x in re.findall(r'[a-z0-9]+',query.lower()) if x.lower() not in stop and len(x)>2]

def is_relevant(text, query):
    terms=relevance_terms(query)
    hay=' '.join(re.findall(r'[a-z0-9]+',str(text).lower()))
    if not terms: return True, 0
    hits=sum(1 for t in terms if t in hay)
    # Require the main subject token. This prevents generic provider matches.
    return hits >= max(1, min(2, len(terms))), round(hits/max(1,len(terms)),2)

def search_pexels(query, settings):
    key=settings.get('pexels_key','').strip()
    if not key: return {'provider':'pexels','configured':False,'query':query,'results':[]}
    url='https://api.pexels.com/videos/search?query='+quote(query)+'&per_page=12&orientation=portrait'
    req=Request(url,headers={'Authorization':key,'User-Agent':'ShortsStudio/1.0'},method='GET')
    try:
        with urlopen(req,timeout=30) as response: data=json.loads(response.read().decode('utf8'))
    except HTTPError as e:
        return {'provider':'pexels','configured':True,'query':query,'results':[],'error':f'Pexels HTTP {e.code}: periksa key dan permission'}
    except URLError as e:
        return {'provider':'pexels','configured':True,'query':query,'results':[],'error':f'Pexels network error: {e.reason}'}
    results=[]
    rejected=0
    for v in data.get('videos',[]):
        relevant,score=is_relevant(v.get('url','')+' '+v.get('image',''),query)
        if not relevant:
            rejected+=1; continue
        files=sorted(v.get('video_files',[]),key=lambda f:(abs((f.get('width') or 0)/(f.get('height') or 1)-.5625),-(f.get('width') or 0)))
        if files:
            f=files[0]; results.append({'id':v.get('id'),'thumbnail':v.get('image'),'duration':v.get('duration'),'download_url':f.get('link'),'source_url':v.get('url'),'license':'Pexels license; verify before publishing','relevance_score':score})
    return {'provider':'pexels','configured':True,'query':query,'results':results,'rejected_irrelevant':rejected,'strict_filter':True}

def search_pixabay(query, settings):
    key=settings.get('pixabay_key','').strip()
    if not key: return {'provider':'pixabay','configured':False,'query':query,'results':[]}
    url='https://pixabay.com/api/videos/?key='+quote(key)+'&q='+quote(query)+'&per_page=12'
    try:
        with urlopen(url,timeout=30) as response: data=json.loads(response.read().decode('utf8'))
    except HTTPError as e:
        return {'provider':'pixabay','configured':True,'query':query,'results':[],'error':f'Pixabay HTTP {e.code}: periksa key dan permission'}
    except URLError as e:
        return {'provider':'pixabay','configured':True,'query':query,'results':[],'error':f'Pixabay network error: {e.reason}'}
    results=[]
    for v in data.get('hits',[]):
        f=v.get('videos',{}).get('medium') or v.get('videos',{}).get('small')
        if f: results.append({'id':v.get('id'),'thumbnail':v.get('userImageURL'),'duration':v.get('duration'),'download_url':f.get('url'),'source_url':'https://pixabay.com/videos/id-'+str(v.get('id'))+'/','license':'Pixabay Content License; verify before publishing'})
    return {'provider':'pixabay','configured':True,'query':query,'results':results}

def call_ai(prompt, settings):
    key=settings.get('api_key','').strip(); base=settings.get('base_url','').rstrip('/')
    if not key: raise ValueError('API key belum disimpan di Settings API')
    if not base: raise ValueError('Base URL belum diisi')
    body=json.dumps({'model':settings.get('model','gpt-4o-mini'),'messages':[{'role':'user','content':prompt}],'temperature':0.3}).encode()
    req=Request(base+'/chat/completions',data=body,headers={'Content-Type':'application/json','Authorization':'Bearer '+key},method='POST')
    try:
        with urlopen(req,timeout=120) as response:
            raw=response.read().decode('utf8')
            try:
                result=json.loads(raw)
            except json.JSONDecodeError as e:
                if e.msg == 'Extra data':
                    for i in range(len(raw), max(0, e.pos-50), -1):
                        try:
                            result=json.loads(raw[:i])
                            break
                        except json.JSONDecodeError:
                            continue
                    else:
                        raise ValueError('Failed to parse AI response')
                else:
                    raise
        if 'choices' not in result or not result['choices']:
            raise ValueError(f'AI response empty: {result.get("error",{}).get("message","unknown error") if "error" in result else str(result)[:200]}')
        content=result['choices'][0]['message']['content']
        content=content.replace('```json\n','').replace('```\n','').replace('```','').strip()
        start=content.find('{')
        if start==-1:
            raise ValueError('No JSON found in AI response')
        brace_count = 0
        in_string = False
        escape = False
        json_end = None
        for i, c in enumerate(content[start:], start):
            if escape:
                escape = False
                continue
            if c == '\\':
                escape = True
                continue
            if c == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == '{':
                brace_count += 1
            elif c == '}':
                brace_count -= 1
                if brace_count == 0:
                    json_end = i + 1
                    break
        if json_end:
            candidate = content[start:json_end]
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                pass
        raise ValueError(f'AI returned invalid JSON structure: {content[:300]}...')
    except HTTPError as e:
        error_body=e.read().decode('utf8') if e.fp else ''
        raise ValueError(f'API HTTP {e.code}: {error_body[:300]}')
    except URLError as e:
        raise ValueError(f'Network error: {e.reason}')
    except json.JSONDecodeError as e:
        raise ValueError(f'Invalid JSON from API: {e.msg}')
    except Exception as e:
        raise ValueError(f'AI call failed: {str(e)}')

def source_video(folder):
    """Find the source video in a project folder (excludes old renders)."""
    exclude={folder/'captioned_output.mp4'}
    for ext in ['*.mp4','*.mkv','*.avi','*.mov','*.webm']:
        videos=[f for f in folder.glob(ext) if f not in exclude]
        if videos:
            return max(videos, key=lambda f: f.stat().st_mtime)
    return None

def probe_duration(video):
    try:
        cmd=['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(video)]
        out=subprocess.run(cmd,capture_output=True,text=True,timeout=30).stdout.strip()
        return float(out) if out else None
    except Exception:
        return None

def render_worker(pid, style, data):
    folder = PROJECTS / pid
    try:
        video = source_video(folder)
        if video is None:
            raise RuntimeError('No video file found in project folder')
        (folder/'transcript_reviewed.json').write_text(json.dumps(data,ensure_ascii=False),encoding='utf8')
        ass=folder/'captions.ass'
        ass.write_text(make_ass(data,style),encoding='utf8')
        output=folder/'captioned_output.mp4'
        if output.exists():
            output.unlink()
        probe_cmd=['ffprobe','-v','error','-select_streams','a','-show_entries','stream=index','-of','csv=p=0',str(video)]
        probe=subprocess.run(probe_cmd,capture_output=True,text=True,timeout=30,cwd=str(folder))
        has_audio=probe.returncode==0 and probe.stdout.strip()!=''
        duration=probe_duration(video)
        write_progress(folder/'render_progress.json', stage='rendering', percent=0, message='Menjalankan FFmpeg…')
        cmd=['ffmpeg','-y','-i',str(video),'-vf','ass=captions.ass','-c:v','libx264','-preset','veryfast','-crf','20','-progress','pipe:1','-nostats','-loglevel','error']
        if has_audio:
            cmd.extend(['-c:a','aac','-b:a','128k'])
        cmd.extend(['-movflags','+faststart',str(output)])
        proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,cwd=str(folder))
        last_pct=0
        for line in proc.stdout:
            line=line.strip()
            if line.startswith('out_time_us='):
                try:
                    us=int(line.split('=',1)[1])
                    if duration:
                        last_pct=min(99,round(100*us/1e6/duration))
                        write_progress(folder/'render_progress.json', stage='rendering', percent=last_pct, message=f'Render {last_pct}%…')
                except ValueError:
                    pass
            if (folder/'render_cancel.txt').exists():
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                write_progress(folder/'render_progress.json', stage='cancelled', percent=0, message='Render dibatalkan')
                return
        proc.wait(timeout=30)
        if proc.returncode:
            err=proc.stderr.read()
            raise RuntimeError(err[-3000:] if err else 'FFmpeg error')
        write_progress(folder/'render_progress.json', stage='done', percent=100, message='Selesai')
    except Exception as exc:
        try:
            write_progress(folder/'render_progress.json', stage='error', percent=0, message=str(exc))
        except OSError:
            pass

class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin','*'); self.send_header('Cache-Control','no-store'); super().end_headers()
    def do_POST(self):
        try:
            route=urlparse(self.path).path
            if route=='/api/settings':
                length=int(self.headers.get('Content-Length','0')); payload=json.loads(self.rfile.read(length))
                current=json.loads(SETTINGS_FILE.read_text(encoding='utf8')) if SETTINGS_FILE.exists() else {}
                for field in ('provider','base_url','model','pexels_key','pixabay_key'):
                    if field in payload: current[field]=str(payload[field]).strip()
                if payload.get('api_key','').strip(): current['api_key']=payload['api_key'].strip()
                SETTINGS_FILE.write_text(json.dumps(current,ensure_ascii=False,indent=2),encoding='utf8')
                send_json(self,200,public_settings()); return
            if route=='/api/assets/search':
                length=int(self.headers.get('Content-Length','0')); payload=json.loads(self.rfile.read(length)); settings=json.loads(SETTINGS_FILE.read_text(encoding='utf8')) if SETTINGS_FILE.exists() else {}; query=str(payload.get('query','')).strip()
                provider=payload.get('provider','all'); results=[]
                if provider in ('all','pexels'): results.append(search_pexels(query,settings))
                if provider in ('all','pixabay'): results.append(search_pixabay(query,settings))
                send_json(self,200,{'query':query,'sources':results}); return
            if route=='/api/ai-generate':
                length=int(self.headers.get('Content-Length','0')); payload=json.loads(self.rfile.read(length))
                settings=json.loads(SETTINGS_FILE.read_text(encoding='utf8')) if SETTINGS_FILE.exists() else {}
                prompt=payload.get('prompt','')
                send_json(self,200,{'content':call_ai(prompt,settings)}); return
            if route=='/api/shutdown':
                deleted=0
                for project in PROJECTS.iterdir():
                    if project.is_dir():
                        shutil.rmtree(project, ignore_errors=True)
                        deleted += 1
                    elif project.is_file():
                        try:
                            project.unlink()
                        except OSError:
                            pass
                PROJECTS.mkdir(exist_ok=True)
                send_json(self,200,{'status':'shutting_down','deleted_projects':deleted})
                threading.Thread(target=self.server.shutdown,daemon=True).start()
                return
            if route=='/api/transcribe':
                filename,data=multipart(self); pid=uuid.uuid4().hex[:12]; folder=PROJECTS/pid; folder.mkdir(); video=folder/filename; video.write_bytes(data)
                language=self.headers.get('X-Language','auto')
                def work():
                    try:
                        result=transcribe(video,language,progress_file=folder/'progress.json',cancel_file=folder/'cancel.txt')
                        (folder/'transcript.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf8')
                        write_progress(folder, stage='done', percent=100, message='Selesai')
                    except TranscriptionCancelled:
                        write_progress(folder, stage='cancelled', percent=0, message='Dibatalkan')
                        shutil.rmtree(folder, ignore_errors=True)
                    except Exception as exc:
                        print(f'[transcribe] error: {exc}', flush=True)
                        write_progress(folder, stage='error', percent=0, message=str(exc))
                threading.Thread(target=work,daemon=True).start()
                send_json(self,200,{'project_id':pid,'status':'transcribing','filename':filename}); return
            if route=='/api/cancel_transcribe':
                length=int(self.headers.get('Content-Length','0')); payload=json.loads(self.rfile.read(length))
                folder=PROJECTS/payload.get('project_id','')
                if folder.is_dir():
                    (folder/'cancel.txt').write_text('1')
                send_json(self,200,{'status':'cancelling'}); return
            if route=='/api/render':
                length=int(self.headers.get('Content-Length','0')); payload=json.loads(self.rfile.read(length))
                pid=payload.get('project_id',''); folder=PROJECTS/pid
                if not folder.is_dir():
                    raise RuntimeError('Project tidak ditemukan')
                data=payload.get('transcript') or json.loads((folder/'transcript.json').read_text(encoding='utf8'))
                style=payload.get('style',{})
                (folder/'render_cancel.txt').unlink(missing_ok=True)
                (folder/'render_progress.json').unlink(missing_ok=True)
                threading.Thread(target=render_worker,args=(pid,style,data),daemon=True).start()
                send_json(self,200,{'project_id':pid,'status':'rendering'}); return
            if route=='/api/delete_project':
                length=int(self.headers.get('Content-Length','0')); payload=json.loads(self.rfile.read(length))
                folder=PROJECTS/payload.get('project_id','')
                if folder.is_dir():
                    shutil.rmtree(folder, ignore_errors=True)
                send_json(self,200,{'status':'deleted'}); return
            if route=='/api/cancel_render':
                length=int(self.headers.get('Content-Length','0')); payload=json.loads(self.rfile.read(length))
                folder=PROJECTS/payload.get('project_id','')
                if folder.is_dir():
                    (folder/'render_cancel.txt').write_text('1')
                send_json(self,200,{'status':'cancelling'}); return
            self.send_error(404)
        except Exception as e: send_json(self,500,{'error':str(e)})
    def do_GET(self):
        route=urlparse(self.path).path
        qs=parse_qs(urlparse(self.path).query)
        if route=='/api/settings':
            send_json(self,200,public_settings()); return
        if route=='/api/transcript':
            pid=qs.get('project_id',[''])[0]; folder=PROJECTS/pid
            if not folder.is_dir():
                send_json(self,404,{'status':'not_found','error':'Project tidak ditemukan (mungkin dibatalkan)'}); return
            tfile=folder/'transcript.json'
            if tfile.exists():
                data=json.loads(tfile.read_text(encoding='utf8')); data['project_id']=pid
                data['filename']=(source_video(folder).name if source_video(folder) else 'video.mp4')
                send_json(self,200,data); return
            send_json(self,200,{'status':'pending','progress':read_progress(folder)}); return
        if route=='/api/transcribe_progress':
            pid=qs.get('project_id',[''])[0]; folder=PROJECTS/pid
            if not folder.is_dir():
                send_json(self,404,{'status':'not_found','error':'Project tidak ditemukan'}); return
            if (folder/'transcript.json').exists():
                send_json(self,200,{'stage':'done','percent':100,'message':'Selesai'}); return
            send_json(self,200,read_progress(folder)); return
        if route=='/api/render_progress':
            pid=qs.get('project_id',[''])[0]; folder=PROJECTS/pid
            if not folder.is_dir():
                send_json(self,404,{'status':'not_found','error':'Project tidak ditemukan'}); return
            send_json(self,200,read_progress(folder/'render_progress.json')); return
        if route=='/api/projects':
            items=[]
            for folder in sorted(PROJECTS.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True):
                if not folder.is_dir(): continue
                video=source_video(folder)
                tfile=folder/'transcript.json'
                rfile=folder/'transcript_reviewed.json'
                try:
                    data=json.loads((rfile if rfile.exists() else tfile).read_text(encoding='utf8'))
                    segs=data.get('segments',[])
                    items.append({'id':folder.name,'filename':video.name if video else 'video.mp4',
                                  'created':folder.stat().st_mtime,'segments':len(segs),
                                  'words':sum(len(s.get('words',[])) for s in segs),
                                  'language':data.get('language',''),'reviewed':rfile.exists()})
                except Exception:
                    items.append({'id':folder.name,'filename':video.name if video else 'video.mp4',
                                  'created':folder.stat().st_mtime,'segments':0,'words':0,'reviewed':False})
            send_json(self,200,{'projects':items}); return
        if route.startswith('/api/project/'):
            pid=route.rsplit('/',1)[-1]; folder=PROJECTS/pid
            if not folder.is_dir(): self.send_error(404); return
            tfile=folder/'transcript.json'; rfile=folder/'transcript_reviewed.json'
            if not tfile.exists(): self.send_error(404); return
            data=json.loads((rfile if rfile.exists() else tfile).read_text(encoding='utf8'))
            data['project_id']=pid
            data['filename']=source_video(folder).name if source_video(folder) else 'video.mp4'
            send_json(self,200,data); return
        if route.startswith('/api/video/'):
            pid=route.rsplit('/',1)[-1]; folder=PROJECTS/pid
            video=source_video(folder) if folder.is_dir() else None
            if video is None or not video.is_file(): self.send_error(404); return
            size=video.stat().st_size
            ext=video.suffix.lower()
            ctype={'mp4':'video/mp4','mkv':'video/x-matroska','mov':'video/quicktime','webm':'video/webm','avi':'video/x-msvideo'}.get(ext,'application/octet-stream')
            start=0; end=size-1; status=200
            rng=self.headers.get('Range')
            if rng:
                m=re.match(r'bytes=(\d*)-(\d*)',rng)
                if m:
                    start=int(m.group(1)) if m.group(1) else 0
                    end=int(m.group(2)) if m.group(2) else size-1
                    end=min(end,size-1)
                    status=206
            self.send_response(status)
            self.send_header('Content-Type',ctype)
            self.send_header('Accept-Ranges','bytes')
            if status==206:
                self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
                self.send_header('Content-Length',str(end-start+1))
            else:
                self.send_header('Content-Length',str(size))
            self.end_headers()
            with video.open('rb') as f:
                f.seek(start)
                remaining=end-start+1
                while remaining>0:
                    chunk=f.read(min(65536,remaining))
                    if not chunk: break
                    self.wfile.write(chunk); remaining-=len(chunk)
            return
        if route.startswith('/api/srt/'):
            pid=route.rsplit('/',1)[-1]; folder=PROJECTS/pid
            if not folder.is_dir(): self.send_error(404); return
            tfile=folder/'transcript.json'; rfile=folder/'transcript_reviewed.json'
            if not tfile.exists(): self.send_error(404); return
            data=json.loads((rfile if rfile.exists() else tfile).read_text(encoding='utf8'))
            srt=make_srt(data)
            raw=srt.encode('utf8')
            self.send_response(200); self.send_header('Content-Type','text/plain; charset=utf-8')
            self.send_header('Content-Length',str(len(raw)))
            self.send_header('Content-Disposition','attachment; filename="captions.srt"')
            self.end_headers(); self.wfile.write(raw); return
        if route.startswith('/api/download/'):
            pid=route.rsplit('/',1)[-1]; output=PROJECTS/pid/'captioned_output.mp4'
            if not output.exists(): self.send_error(404); return
            self.send_response(200); self.send_header('Content-Type','video/mp4'); self.send_header('Content-Length',str(output.stat().st_size)); self.send_header('Content-Disposition','attachment; filename="captioned-video.mp4"'); self.end_headers();
            with output.open('rb') as f: shutil.copyfileobj(f,self.wfile)
            return
        return super().do_GET()
    def log_message(self,fmt,*args): print(fmt%args,flush=True)

if __name__=='__main__':
    os.chdir(ROOT); print(f'Captions Maker: http://127.0.0.1:8770/captions-maker.html | model={MODEL_SIZE}',flush=True); ThreadingHTTPServer(('127.0.0.1',8770),Handler).serve_forever()
