# -*- coding: utf-8 -*-
"""
🎬 AI Video Studio Pro — مجاني 100% وبلا حدود زمنية
========================================================
المواصفات:
  ✔ تتكلم مع الموقع (مايكروفون ← Whisper مجاني) أو تكتب أو تطلب من المساعد يكتب لك السكريبت
  ✔ صوت عربي/إنجليزي طبيعي (Edge TTS مجاني وبلا حدود)
  ✔ صور AI مجانية (Pollinations — بدون مفتاح) مع تأثير Ken Burns سينمائي
  ✔ أو مقاطع فيديو جاهزة من Pexels (مفتاح مجاني اختياري)
  ✔ ترجمة عربية محروقة داخل الفيديو تلقائياً (من توقيتات الكلمات الحقيقية)
  ✔ لا يوجد أي حد زمني — ساعة كاملة ينتجها عادي
  ✔ بدون كلمة سر، يشتغل محلي على المتصفح

التثبيت:
  pip install gradio moviepy edge-tts requests faster-whisper
  + ثبّت ffmpeg على نظامك (لازم للترميز والترجمة)

التشغيل:
  python ai_video_studio_pro.py
"""

import os
import random
import asyncio
import subprocess
import tempfile
from pathlib import Path

import requests
import gradio as gr
import edge_tts
from moviepy import ImageClip, VideoFileClip, AudioFileClip, concatenate_videoclips

OUT_DIR = Path("outputs")
OUT_DIR.mkdir(exist_ok=True)

W, H = 1280, 720  # دقة الفيديو

# ---------------------------------------------------------
# الأصوات المجانية (Edge TTS — بلا حدود نهائياً)
# ---------------------------------------------------------
VOICES = {
    "عربي - سلمى (مصر) 🇪🇬": "ar-EG-SalmaNeural",
    "عربي - شاكر (مصر) 🇪🇬": "ar-EG-ShakirNeural",
    "عربي - لطيفة (الجزائر) 🇩🇿": "ar-DZ-LatifaNeural",
    "عربي - حمزة (السعودية) 🇸🇦": "ar-SA-HammedNeural",
    "عربي - زارينا (الإمارات) 🇦🇪": "ar-AE-ZariyahNeural",
    "إنجليزي - أريا (أمريكا) 🇺🇸": "en-US-AriaNeural",
    "إنجليزي - جاي (أمريكا) 🇺🇸": "en-US-GuyNeural",
}

# أساليب الصور المولدة
IMAGE_STYLES = {
    "سينمائي واقعي 🎬": "cinematic realistic photography, dramatic lighting, film still, 8k, ultra detailed",
    "أنمي ✨": "beautiful anime style illustration, vibrant colors, detailed artwork",
    "خيال ملحمي 🐉": "epic fantasy digital art, magical atmosphere, concept art, stunning",
    "ثلاثي الأبعاد 🧊": "3d render, pixar style, octane render, soft lighting, high quality",
    "وثائقي 🌍": "documentary photography, national geographic style, natural light, sharp focus",
}

# ---------------------------------------------------------
# 1) النصوص من الذكاء الاصطناعي (Pollinations — مجاني بدون مفتاح)
# ---------------------------------------------------------
def ai_text(prompt: str, system: str = None) -> str:
    url = "https://text.pollinations.ai/" + requests.utils.quote(prompt)
    params = {"model": "openai"}
    if system:
        params["system"] = system
    r = requests.get(url, params=params, timeout=120)
    r.raise_for_status()
    return r.text.strip()

def ai_image(prompt: str, path: Path, seed: int = None):
    seed = seed if seed is not None else random.randint(1, 999_999)
    url = (f"https://image.pollinations.ai/prompt/{requests.utils.quote(prompt)}"
           f"?width={W}&height={H}&seed={seed}&nologo=true&enhance=true")
    r = requests.get(url, timeout=240)
    r.raise_for_status()
    if len(r.content) < 10_000:
        raise RuntimeError("الصورة المولدة فارغة، حاول مرة أخرى")
    path.write_bytes(r.content)

# ---------------------------------------------------------
# 2) التعرف على الكلام من المايك (Whisper محلي — مجاني)
# ---------------------------------------------------------
_whisper = None
def get_whisper():
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel
        _whisper = WhisperModel("small", device="cpu", compute_type="int8")
    return _whisper

def transcribe_audio(audio_path: str, lang: str = "ar") -> str:
    model = get_whisper()
    segments, _ = model.transcribe(audio_path, language=lang, beam_size=5)
    return " ".join(seg.text for seg in segments).strip()

# ---------------------------------------------------------
# 3) التعليق الصوتي + توقيتات الكلمات الحقيقية للترجمة
# ---------------------------------------------------------
async def tts_with_timing(text: str, voice: str, out_path: str):
    communicate = edge_tts.Communicate(text, voice)
    bounds = []
    with open(out_path, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                bounds.append({
                    "start": chunk["offset"] / 10_000_000,
                    "end": (chunk["offset"] + chunk["duration"]) / 10_000_000,
                    "word": chunk["text"],
                })
    if not os.path.exists(out_path) or os.path.getsize(out_path) < 2000:
        raise RuntimeError("فشل إنشاء الصوت — تحقق من اتصال الإنترنت")
    return bounds

def bounds_to_srt(bounds, max_words=6, max_dur=4.0) -> str:
    lines, cur, start = [], [], None
    for b in bounds:
        if start is None:
            start = b["start"]
        cur.append(b)
        if len(cur) >= max_words or (b["end"] - start) >= max_dur:
            lines.append((start, cur[-1]["end"], " ".join(w["word"] for w in cur)))
            cur, start = [], None
    if cur:
        lines.append((start, cur[-1]["end"], " ".join(w["word"] for w in cur)))

    def fmt(t):
        h, m = int(t // 3600), int((t % 3600) // 60)
        return f"{h:02d}:{m:02d}:{t % 60:06.3f}".replace(".", ",")

    return "".join(f"{i}\n{fmt(a)} --> {fmt(b)}\n{txt}\n\n"
                   for i, (a, b, txt) in enumerate(lines, 1))

# ---------------------------------------------------------
# 4) تحميل فيديو خلفية من Pexels (مفتاح مجاني اختياري)
# ---------------------------------------------------------
def download_pexels_video(query: str, api_key: str, out_path: str):
    headers = {"Authorization": api_key}
    url = f"https://api.pexels.com/videos/search?query={requests.utils.quote(query)}&per_page=8&orientation=landscape"
    r = requests.get(url, headers=headers, timeout=20)
    data = r.json()
    if not data.get("videos"):
        raise RuntimeError(f"لا توجد مقاطع فيديو بالكلمة: {query}")
    files = sorted(data["videos"][0]["video_files"], key=lambda f: -(f.get("width") or 0))
    link = next((f["link"] for f in files if (f.get("width") or 0) >= 1280), files[0]["link"])
    with requests.get(link, timeout=120, stream=True) as resp:
        resp.raise_for_status()
        with open(out_path, "wb") as f:
            for c in resp.iter_content(1024 * 1024):
                f.write(c)

# ---------------------------------------------------------
# 5) تأثير Ken Burns سينمائي على الصور
# ---------------------------------------------------------
def ken_burns(image_path: str, duration: float, pan: str) -> ImageClip:
    clip = ImageClip(image_path).with_duration(duration)
    w, h = clip.size
    scale = max(W / w, H / h) * 1.18
    clip = clip.resized(scale)
    w2, h2 = clip.size
    mx, my = w2 - W, h2 - H
    def x1(t):
        p = t / duration
        return int(mx * (1 - p)) if pan == "in" else int(mx * p)
    def y1(t):
        p = t / duration
        return int(my * (1 - p)) if pan == "in" else int(my * p)
    return clip.cropped(x1=x1, y1=y1, width=W, height=H)

# ---------------------------------------------------------
# 6) حرق الترجمة داخل الفيديو بـ ffmpeg
# ---------------------------------------------------------
def burn_subtitles(video_in: str, srt_path: str, video_out: str):
    style = ("FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H80000000,"
             "BorderStyle=3,BackColour=&H64000000,Alignment=2,MarginV=35")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", video_in,
             "-vf", f"subtitles={srt_path}:force_style='{style}'",
             "-c:a", "copy", video_out],
            check=True, capture_output=True)
    except subprocess.CalledProcessError:
        # احتياطي: ترجمة ناعمة (تشتغل بالمشغلات الحديثة)
        subprocess.run(
            ["ffmpeg", "-y", "-i", video_in, "-i", srt_path,
             "-c:v", "copy", "-c:a", "copy", "-c:s", "mov_text", video_out],
            check=True, capture_output=True)

# ---------------------------------------------------------
# 7) الإنتاج الكامل — بلا حد زمني نهائياً
# ---------------------------------------------------------
def split_script(text: str, parts: int):
    sentences = [s.strip() for s in text.replace("!", ".").replace("؟", "?").split(".") if s.strip()]
    if not sentences:
        return [text]
    n = max(1, len(sentences) // parts)
    return [". ".join(sentences[i:i + n]) for i in range(0, len(sentences), n)] or [text]

def create_video(script, voice_choice, mode, img_style, img_prompt, scenes,
                 pexels_key, bg_keyword, add_subs, progress=gr.Progress()):
    if not script or not script.strip():
        return None, "❌ اكتب السكريبت أولاً (أو استخدم المساعد/المايكروفون)"
    voice = VOICES.get(voice_choice, "ar-EG-SalmaNeural")

    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            audio_path = tmp / "voice.mp3"
            raw_video = tmp / "raw.mp4"
            srt_path = tmp / "subs.srt"
            final_path = OUT_DIR / f"video_{random.randint(10000,99999)}.mp4"

            # --- الصوت + توقيتات الترجمة ---
            progress(0.05, desc="🎙️ جاري توليد الصوت...")
            bounds = asyncio.run(tts_with_timing(script.strip(), voice, str(audio_path)))
            audio = AudioFileClip(str(audio_path))
            dur = audio.duration  # أي مدة: ٥ دقائق أو ساعة — بلا حدود

            progress(0.25, desc=f"🎬 المدة: {int(dur//60)}:{int(dur%60):02d} — جاري تجهيز المشاهد...")

            if mode == "صور AI مجانية 🎨":
                segs = split_script(script, scenes)
                images = []
                for i, seg in enumerate(segs):
                    prompt = f"{seg[:220]}. {IMAGE_STYLES[img_style]}"
                    progress(0.25 + 0.4 * (i / len(segs)),
                             desc=f"🖼️ توليد الصورة {i+1}/{len(segs)}...")
                    p = tmp / f"img_{i}.jpg"
                    ai_image(prompt, p)
                    images.append(p)
                # توزيع المدة + تكرار الصور لو المدة طويلة
                slide_d = max(6.0, dur / len(images))
                clips, t, i = [], 0.0, 0
                while t < dur - 0.2:
                    clips.append(ken_burns(str(images[i % len(images)]), slide_d, "in" if i % 2 == 0 else "out"))
                    t += slide_d
                    i += 1
            else:
                # وضع Pexels: فيديو خلفية يتكرر حتى نهاية الصوت
                if not pexels_key or not pexels_key.strip():
                    audio.close()
                    return None, "❌ أدخل مفتاح Pexels API أو اختر وضع صور AI"
                bg = tmp / "bg.mp4"
                progress(0.35, desc="📥 جاري تحميل خلفية Pexels...")
                download_pexels_video(bg_keyword.strip(), pexels_key.strip(), str(bg))
                bgc = VideoFileClip(str(bg))
                if bgc.duration < dur:
                    bgc = concatenate_videoclips([bgc] * (int(dur // bgc.duration) + 1))
                clips = [bgc.subclipped(0, dur)]

            progress(0.75, desc="⚙️ جاري تجميع الفيديو...")
            video = concatenate_videoclips(clips).with_audio(audio)
            video.write_videofile(str(raw_video), fps=24, codec="libx264",
                                  audio_codec="aac", preset="medium", threads=4)
            video.close()
            for c in clips:
                try: c.close()
                except Exception: pass
            audio.close()

            # --- الترجمة ---
            if add_subs:
                progress(0.9, desc="📝 جاري حرق الترجمة...")
                srt_path.write_text(bounds_to_srt(bounds), encoding="utf-8")
                burn_subtitles(str(raw_video), str(srt_path), str(final_path))
            else:
                final_path.write_bytes(raw_video.read_bytes())

            progress(1.0, desc="✅ تم الإنتاج بنجاح!")
            return str(final_path), f"✅ جاهز! المدة {int(dur//60)}:{int(dur%60):02d} — بدون حدود 🚀"

    except Exception as e:
        return None, f"❌ خطأ: {e}"

# ---------------------------------------------------------
# 8) المساعد الذكي — تتكلم معه ويكتب لك السكريبت
# ---------------------------------------------------------
ASSISTANT_SYSTEM = ("أنت مساعد متخصص بكتابة سكريبتات فيديوهات يوتيوب عربية جذابة للتعليق الصوتي. "
                    "اكتب سكريبتات سلسة ومشوقة بدون عناوين أو رموز تنسيق — فقط النص المرتب للقراءة بصوت عالٍ.")

def assistant_chat(message, history):
    if not message or not message.strip():
        return history, history
    try:
        reply = ai_text(message, system=ASSISTANT_SYSTEM)
    except Exception as e:
        reply = f"⚠️ تعذر الاتصال بالمساعد: {e}"
    history = history + [[message, reply]]
    return history, history

def use_last_script(history):
    if history and history[-1][1]:
        return gr.update(value=history[-1][1]), "✅ تم نقل السكريبت إلى صفحة الإنتاج"
    return gr.update(), "❌ لا يوجد رد سابق"

# ---------------------------------------------------------
# 9) الواجهة — تصميم أسطوري
# ---------------------------------------------------------
theme = gr.themes.Soft(primary_hue="indigo", secondary_hue="cyan")

with gr.Blocks(theme=theme, title="AI Video Studio Pro 🎬") as app:
    gr.Markdown("""
    # 🎬 AI Video Studio Pro
    ### موقعك الأسطوري لصناعة الفيديو بالذكاء الاصطناعي — مجاني 100% • بلا حدود زمنية • تتكلم معاه وينتج لك فيديو
    """)

    with gr.Tabs():
        # ---------------- تبويب الإنتاج ----------------
        with gr.Tab("🎥 إنتاج الفيديو"):
            with gr.Row():
                with gr.Column(scale=1):
                    script = gr.Textbox(label="📝 السكريبت (اكتب / نسخ من المساعد / من المايك)",
                                        lines=9, placeholder="اكتب نص الفيديو هنا... طوّل براحتك، ٥ دقائق أو أكثر عادي")
                    with gr.Row():
                        mic = gr.Audio(label="🎤 سجل صوتك وهيتحول لنص", sources=["microphone"], type="filepath")
                        mic_lang = gr.Dropdown(choices=[("عربي", "ar"), ("English", "en")], value="ar", label="اللغة")
                    mic_btn = gr.Button("🎙️ تحويل التسجيل لنص", size="sm")
                    mic_status = gr.Markdown("")
                    voice = gr.Dropdown(choices=list(VOICES.keys()), value=list(VOICES.keys())[0], label="🗣️ الصوت")
                    mode = gr.Radio(choices=["صور AI مجانية 🎨", "فيديو خلفية Pexels 🎞️"], value="صور AI مجانية 🎨", label="نوع الخلفية")
                    with gr.Group(visible=True) as img_group:
                        style = gr.Dropdown(choices=list(IMAGE_STYLES.keys()), value=list(IMAGE_STYLES.keys())[0], label="🎨 ستايل الصور")
                        scenes = gr.Slider(4, 20, value=8, step=1, label="عدد المشاهد (صور)")
                    with gr.Group(visible=False) as px_group:
                        pexels_key = gr.Textbox(label="🔑 مفتاح Pexels API (مجاني من pexels.com/api)", type="password")
                        bg_kw = gr.Textbox(label="🔍 كلمة البحث (بالإنجليزي)", placeholder="nature, space, city...")
                    subs = gr.Checkbox(label="📝 ترجمة عربية محروقة داخل الفيديو", value=True)
                    go = gr.Button("🚀 ابدأ الإنتاج", variant="primary", size="lg")
                with gr.Column(scale=1):
                    status = gr.Textbox(label="📊 الحالة", interactive=False, lines=2)
                    out = gr.Video(label="🎬 الفيديو النهائي")

            mic_btn.click(fn=lambda a, l: (transcribe_audio(a, l), "✅ تم التحويل") if a else ("", "❌ سجل صوت أولاً"),
                          inputs=[mic, mic_lang], outputs=[script, mic_status])

            def toggle_mode(m):
                return gr.update(visible=(m == "صور AI مجانية 🎨")), gr.update(visible=(m == "فيديو خلفية Pexels 🎞️"))
            mode.change(toggle_mode, mode, [img_group, px_group])

            go.click(create_video, [script, voice, mode, style, gr.State(""), scenes,
                                    pexels_key, bg_kw, subs], [out, status])

        # ---------------- تبويب المساعد ----------------
        with gr.Tab("🤖 المساعد الذكي — كلّمه"):
            gr.Markdown("### اطلب منه موضوع الفيديو وهو يكتب لك سكريبت جاهز، وبعدين انقله بزر واحد")
            chat = gr.Chatbot(label="المحادثة", height=420)
            msg = gr.Textbox(label="اكتب رسالتك", placeholder="مثال: اكتبلي سكريبت عن أسرار الفضاء مدته ٥ دقائق")
            with gr.Row():
                send = gr.Button("📩 إرسال", variant="primary")
                use_it = gr.Button("📋 استخدام آخر رد كسكريبت")

            chat_state = gr.State([])
            send.click(assistant_chat, [msg, chat_state], [chat, chat_state]).then(
                lambda: gr.update(value=""), None, [msg])
            use_it.click(use_last_script, chat_state, [script, mic_status])

        # ---------------- تبويب الشرح ----------------
        with gr.Tab("ℹ️ الشرح"):
            gr.Markdown("""
            ### كيف يشتغل الموقع؟ (كله مجاني ولا نهائي)
            | الميزة | المصدر | التكلفة |
            |---|---|---|
            | الصوت العربي الطبيعي | Edge TTS | مجاني وبلا حدود |
            | تدوين المايكروفون | Whisper (محلي على جهازك) | مجاني |
            | كتابة السكريبت | Pollinations AI | مجاني بدون مفتاح |
            | توليد الصور | Pollinations AI | مجاني بدون مفتاح |
            | فيديوهات الخلفية | Pexels API | مجاني (مفتاح مجاني) |
            | ترجمة محروقة بتوقيت الكلمات الحقيقي | Edge TTS + ffmpeg | مجاني |

            1. كلّم المساعد واطلب سكريبت، أو سجل صوتك، أو اكتب بنفسك
            2. اختر الصوت ونوع الخلفية
            3. اضغط 🚀 — الفيديو يطلع بأي مدة، ٥ دقائق أو ٣٠ دقيقة، بدون سقف
            4. الملفات تتحفظ في مجلد `outputs` جنب السكريبت

            **ملاحظات:**
            - أول مرة تستخدم المايكروفون بينزل نموذج Whisper (~500MB) مرة واحدة بس
            - لازم ffmpeg يكون مثبت: على ويندوز حمّله من ffmpeg.org وضيفه للـ PATH
            - الفيديوهات الطويلة تاخد وقت رندر حسب قوة جهازك (طبيعي)
            """)

if __name__ == "__main__":
    app.launch(share=True)  # share=True يعطيك رابط عام تشاركه مع الناس
