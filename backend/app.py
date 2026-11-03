import os, re, uuid, shutil, subprocess, threading
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

BASE = Path(__file__).resolve().parent
WEB = BASE.parent / "web"
WORK = BASE / "work"
OUT = BASE / "outputs"
WORK.mkdir(exist_ok=True); OUT.mkdir(exist_ok=True)
app = FastAPI(title="SLING SHORTS AI")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=False, allow_methods=["*"], allow_headers=["*"])
app.mount("/web", StaticFiles(directory=str(WEB)), name="web")
JOBS = {}
MAX_UPLOAD = 2 * 1024 * 1024 * 1024

def run(cmd):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode: raise RuntimeError((p.stderr or p.stdout)[-3000:])
    return p.stdout

def require_tools():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("FFmpeg and ffprobe must be installed and available on PATH.")

def duration(path):
    return max(1.0, float(run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(path)]).strip()))

def download_youtube(url, dest):
    if not re.match(r"^https?://(www\\.)?(youtube\\.com|youtu\\.be)/", url.strip(), re.I):
        raise ValueError("Please enter a standard YouTube video URL.")
    run(["yt-dlp","--no-playlist","-f","bv*[height<=1080]+ba/b[height<=1080]","--merge-output-format","mp4","-o",str(dest),url])
    if not dest.exists():
        candidates = list(dest.parent.glob(dest.stem + ".*"))
        if candidates: return candidates[0]
        raise RuntimeError("YouTube download did not produce a video file.")
    return dest

def transcribe(path):
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(os.getenv("WHISPER_MODEL", "base"), device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(path), vad_filter=True, word_timestamps=True)
        words = []
        for seg in segments:
            if getattr(seg, "words", None):
                for w in seg.words: words.append({"start":float(w.start),"end":float(w.end),"text":w.word.strip()})
            else: words.append({"start":float(seg.start),"end":float(seg.end),"text":seg.text.strip()})
        return words
    except Exception: return []

def score_window(words, start, end):
    text = " ".join(w["text"] for w in words if start <= w["start"] < end).lower()
    hooks = ["secret","shocking","never","best","worst","amazing","insane","why","how","mistake","actually","truth","finally","impossible","crazy","surprising","important","believe"]
    score = sum(2 for h in hooks if h in text.split()) + min(len(text.split())/12,5)
    score += 2 if "?" in text or "!" in text else 0
    return score, text

def find_face_x(path, t, width, height):
    try:
        import cv2
        cap=cv2.VideoCapture(str(path)); cap.set(cv2.CAP_PROP_POS_MSEC,t*1000)
        ok,frame=cap.read(); cap.release()
        if not ok: return width/2
        gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
        cascade=cv2.CascadeClassifier(cv2.data.haarcascades+"haarcascade_frontalface_default.xml")
        faces=cascade.detectMultiScale(gray,1.1,4,minSize=(40,40))
        if len(faces):
            x,y,w,h=max(faces,key=lambda a:a[2]*a[3]); return x+w/2
    except Exception: pass
    return width/2

def video_size(path):
    import json
    data=json.loads(run(["ffprobe","-v","error","-select_streams","v:0","-show_entries","stream=width,height","-of","json",str(path)]))
    s=data["streams"][0]; return int(s["width"]),int(s["height"])

def make_srt(words,start,end,target):
    selected=[w for w in words if w["end"]>start and w["start"]<end and w["text"]]
    lines=[]
    if selected:
        chunks=[selected[i:i+5] for i in range(0,len(selected),5)]
        def stamp(v):
            ms=int(v*1000); h=ms//3600000; ms%=3600000; m=ms//60000; ms%=60000; s=ms//1000; ms%=1000
            return f"{h:02}:{m:02}:{s:02},{ms:03}"
        for i,g in enumerate(chunks,1):
            a=max(0,g[0]["start"]-start); b=max(a+.15,g[-1]["end"]-start)
            lines += [str(i),f"{stamp(a)} --> {stamp(min(b,end-start))}"," ".join(x["text"] for x in g),""]
    target.write_text("\\n".join(lines),encoding="utf-8")
    return bool(selected)

def process_one(src,jobid,index,clip_count,clip_len):
    require_tools(); total=duration(src); words=transcribe(src)
    win=min(clip_len,total); starts=[]; step=max(12,win*.65); t=0.0
    while t<total:
        starts.append(min(t,max(0,total-win))); t+=step
        if len(starts)>250: break
    ranked=[]
    for s in sorted(set(starts)):
        sc,txt=score_window(words,s,min(total,s+win)); ranked.append((sc,s,txt))
    ranked.sort(reverse=True); chosen=[]
    for sc,s,txt in ranked:
        if all(abs(s-x[1])>win*.65 for x in chosen): chosen.append((sc,s,txt))
        if len(chosen)>=clip_count: break
    if not chosen: chosen=[(0,0,"")]
    w,h=video_size(src)
    for n,(sc,start,txt) in enumerate(chosen,1):
        end=min(total,start+win); face_x=find_face_x(src,start+min(2,win/2),w,h)
        crop_w=min(w,int(h*9/16)); x=max(0,min(w-crop_w,int(face_x-crop_w/2)))
        srt=WORK/f"{jobid}_{index}_{n}.srt"; has_sub=make_srt(words,start,end,srt)
        output=OUT/f"{jobid}_video{index+1}_short{n}.mp4"
        vf=f"crop={crop_w}:{h}:{x}:0,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
        if has_sub:
            safe=str(srt).replace("\\\\","/").replace(":","\\\\:")
            vf+=f",subtitles='{safe}':force_style='FontName=Arial,FontSize=19,PrimaryColour=&H00FFFFFF,OutlineColour=&H00101010,BorderStyle=1,Outline=3,Shadow=1,Alignment=2,MarginV=170'"
        run(["ffmpeg","-y","-ss",str(start),"-i",str(src),"-t",str(end-start),"-vf",vf,"-c:v","libx264","-preset","veryfast","-crf","23","-c:a","aac","-b:a","128k","-movflags","+faststart",str(output)])
        JOBS[jobid]["results"].append({"name":output.name,"url":f"/download/{output.name}","score":round(sc,1),"duration":round(end-start,1),"source":src.name})

def worker(jobid,sources,clips,clip_len):
    try:
        JOBS[jobid]["status"]="processing"
        for i,src in enumerate(sources):
            process_one(src,jobid,i,clips,clip_len); JOBS[jobid]["progress"]=round((i+1)/len(sources)*100)
        JOBS[jobid]["status"]="completed"
    except Exception as e:
        JOBS[jobid]["status"]="error"; JOBS[jobid]["error"]=str(e)

@app.get("/",response_class=HTMLResponse)
def home(): return (WEB/"index.html").read_text(encoding="utf-8")

@app.get("/api/status")
def status(): return {"service":"SLING SHORTS AI","status":"ready"}

@app.post("/api/process")
async def process(files:list[UploadFile]=File(default=[]),youtube_url:str=Form(default=""),clips:int=Form(default=3),clip_len:int=Form(default=35)):
    if not files and not youtube_url.strip(): raise HTTPException(400,"Upload at least one video or enter a YouTube URL.")
    clips=max(1,min(10,clips)); clip_len=max(15,min(90,clip_len))
    jobid=uuid.uuid4().hex[:10]; folder=WORK/jobid; folder.mkdir(exist_ok=True); sources=[]
    try:
        if youtube_url.strip(): sources.append(download_youtube(youtube_url.strip(),folder/"youtube_source.mp4"))
        for i,f in enumerate(files):
            suffix=Path(f.filename or "video.mp4").suffix.lower()
            if suffix not in [".mp4",".mov",".mkv",".webm",".m4v"]: raise ValueError("Unsupported file type: "+suffix)
            dest=folder/f"upload_{i}{suffix}"; size=0
            with dest.open("wb") as out:
                while True:
                    chunk=await f.read(1024*1024)
                    if not chunk: break
                    size+=len(chunk)
                    if size>MAX_UPLOAD: raise ValueError("Each upload must be under 2 GB.")
                    out.write(chunk)
            sources.append(dest)
        JOBS[jobid]={"status":"queued","progress":0,"results":[],"error":None}
        threading.Thread(target=worker,args=(jobid,sources,clips,clip_len),daemon=True).start()
        return {"job_id":jobid,"status":"queued"}
    except Exception as e: raise HTTPException(400,str(e))

@app.get("/api/jobs/{jobid}")
def job(jobid:str):
    if jobid not in JOBS: raise HTTPException(404,"Job not found")
    return JOBS[jobid]

@app.get("/download/{filename}")
def download(filename:str):
    if Path(filename).name!=filename: raise HTTPException(400,"Invalid filename")
    path=OUT/filename
    if not path.exists(): raise HTTPException(404,"File not found")
    return FileResponse(path,media_type="video/mp4",filename=filename)

if __name__=="__main__":
    import uvicorn
    uvicorn.run("app:app",host=os.getenv("HOST","127.0.0.1"),port=int(os.getenv("PORT","8000")))
