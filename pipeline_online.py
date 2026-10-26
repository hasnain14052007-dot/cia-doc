"""
Full pipeline (needs internet). UNTESTED in my sandbox, which has no network.
  pip install edge-tts "moviepy==1.0.3" pillow requests numpy
  (also needs ffmpeg and ImageMagick for TextClip)
  optional: export PEXELS_API_KEY=...
Run:  python pipeline_online.py   -> final.mp4, voiceover.mp3
"""
import asyncio, os, re, io, requests, numpy as np, subprocess
import edge_tts
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import *
from scenes import S

W,H,FPS=1920,1080,24
D="work"; os.makedirs(D,exist_ok=True)
UA={"User-Agent":"DocStudio/1.0 (educational documentary project)"}
FONT="Poppins-Bold"

# ---------- 1. VOICEOVER (per scene so timing is exact) ----------
async def tts(text,path):
    await edge_tts.Communicate(text,"en-US-GuyNeural",rate="-10%").save(path)
async def all_tts():
    for i,(ch,t,q,dl) in enumerate(S):
        p=f"{D}/vo{i:03d}.mp3"
        if not os.path.exists(p):
            try: await tts(t,p)
            except Exception as e: print("tts fail",i,e)
asyncio.run(all_tts())

# ---------- 2. IMAGES: Wikimedia Commons, then Pexels, then text fallback ----------
def commons(q):
    try:
        r=requests.get("https://commons.wikimedia.org/w/api.php",headers=UA,timeout=20,params=dict(
            action="query",format="json",generator="search",gsrsearch=q,gsrnamespace=6,gsrlimit=8,
            prop="imageinfo",iiprop="url|mime",iiurlwidth=1920))
        for p in r.json().get("query",{}).get("pages",{}).values():
            ii=p["imageinfo"][0]
            if ii["mime"] in("image/jpeg","image/png"):
                b=requests.get(ii.get("thumburl") or ii["url"],headers=UA,timeout=30).content
                return Image.open(io.BytesIO(b)).convert("RGB")
    except Exception as e: print("commons fail",q,e)
def pexels(q):
    k=os.environ.get("PEXELS_API_KEY")
    if not k: return None
    try:
        r=requests.get("https://api.pexels.com/v1/search",headers={"Authorization":k},params=dict(query=q,per_page=1,orientation="landscape"),timeout=20).json()
        return Image.open(io.BytesIO(requests.get(r["photos"][0]["src"]["large2x"],timeout=30).content)).convert("RGB")
    except Exception as e: print("pexels fail",q,e)
def fallback(text):
    im=Image.new("RGB",(W,H),(8,8,12)); d=ImageDraw.Draw(im)
    f=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",70)
    d.text((120,H//2-60),text[:40],font=f,fill=(220,220,220)); return im
def cover(im):
    s=max(W*1.15/im.width,H*1.15/im.height); im=im.resize((int(im.width*s),int(im.height*s)))
    return im
def darken(im,a=0.55):
    from PIL import ImageEnhance; return ImageEnhance.Brightness(im).enhance(a)

def date_card(label):
    im=Image.new("RGBA",(W,H),(0,0,0,0)); d=ImageDraw.Draw(im)
    f=ImageFont.truetype("/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf",120)
    d.rectangle([80,70,80+int(d.textlength(label,font=f))+60,230],fill=(0,0,0,170))
    d.text((110,80),label,font=f,fill=(255,214,0,255)); return np.array(im)

# ---------- 3. SFX + MUSIC ----------
def whoosh(path):
    sr=44100; n=int(sr*0.7); x=np.random.randn(n)*np.hanning(n)
    k=np.ones(60)/60; x=np.convolve(x,k,"same")*np.linspace(0.2,1,n)**2
    import wave; w=wave.open(path,"wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
    w.writeframes((x/np.abs(x).max()*20000).astype(np.int16).tobytes()); w.close()
def music(path):
    # Replace URL with any royalty-free cinematic track you have the rights to (e.g. Kevin MacLeod / incompetech, CC-BY - credit required).
    url=os.environ.get("MUSIC_URL")
    try:
        if url: open(path,"wb").write(requests.get(url,headers=UA,timeout=60).content); return
    except Exception as e: print("music download failed",e)
    subprocess.run(["ffmpeg","-y","-loglevel","error","-f","lavfi","-i","sine=f=55:d=700","-f","lavfi","-i","sine=f=82.4:d=700",
        "-filter_complex","amix=inputs=2,lowpass=f=300,volume=0.8",path])
whoosh(f"{D}/whoosh.wav"); 
if not os.path.exists(f"{D}/music.mp3"): music(f"{D}/music.mp3")

# ---------- 4. EDIT ----------
def subtitles(text,dur):
    words=text.split(); tot=sum(len(w) for w in words); t=0; clips=[]
    for w in words:
        d=dur*len(w)/tot
        try:
            c=TextClip(w.upper(),fontsize=120,color="yellow",font=FONT,stroke_color="black",stroke_width=4).set_start(t).set_duration(d).set_position(("center",H*0.72))
            clips.append(c)
        except Exception as e: print("textclip fail",e); break
        t+=d
    return clips
scenes=[];voices=[];t=0
for i,(ch,text,q,dl) in enumerate(S):
    vp=f"{D}/vo{i:03d}.mp3"
    try: a=AudioFileClip(vp); dur=a.duration+0.5
    except Exception: a=None; dur=max(5,len(text.split())/2.4)
    im=commons(q) or pexels(q) or fallback(q)
    base=np.array(darken(cover(im)))
    zin=i%2==0
    bg=ImageClip(base).set_duration(dur)
    bg=bg.resize(lambda tt: 1+0.08*(tt/dur) if zin else 1.08-0.08*(tt/dur)).set_position("center")
    layers=[ColorClip((W,H),(0,0,0)).set_duration(dur),bg]
    if dl: layers.append(ImageClip(date_card(dl),ismask=False).set_duration(dur))
    layers+=subtitles(text,dur-0.5)
    sc=CompositeVideoClip(layers,size=(W,H)).set_duration(dur).crossfadein(0.5)
    scenes.append(sc)
    if a: voices.append(a.set_start(t))
    t+=dur-0.5   # overlap for crossfade
video=concatenate_videoclips(scenes,padding=-0.5,method="compose")
vo=CompositeAudioClip(voices); vo.write_audiofile("voiceover.mp3",fps=44100)   # (for upload)
mus=afx.audio_loop(AudioFileClip(f"{D}/music.mp3"),duration=video.duration).volumex(0.15)
wh=AudioFileClip(f"{D}/whoosh.wav").volumex(0.5)
sfx=[wh.set_start(max(0,s*0+tt)) for tt in np.cumsum([0]+[sc.duration-0.5 for sc in scenes[:-1]])]
video=video.set_audio(CompositeAudioClip([mus,vo]+sfx))
video.write_videofile("final.mp4",fps=FPS,codec="libx264",audio_codec="aac",preset="medium",threads=4)
