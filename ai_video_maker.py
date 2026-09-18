# =========================================================
# AI Video Generator Application - Free & Unlimited
# تطبيق موقك الشخصي لتوليد الفيديوهات بالذكاء الاصطناعي
# =========================================================

import os
import asyncio
import json
import requests
import gradio as gr
import edge_tts
from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_videoclips

# ---------------------------------------------------------
# 1. قائمة الأصوات المتاحة (عربي + إنجليزي)
# ---------------------------------------------------------
VOICES = {
    "عربي - سلمى (مصر)": "ar-EG-SalmaNeural",
    "عربي - شاكر (مصر)": "ar-EG-ShakirNeural",
    "عربي - حمزة (السعودية)": "ar-SA-HammedNeural",
    "عربي - زارينا (الإمارات)": "ar-AE-ZariyahNeural",
    "إنجليزي - أريا (أمريكا)": "en-US-AriaNeural",
    "إنجليزي - جايسون (أمريكا)": "en-US-GuyNeural",
}

# ---------------------------------------------------------
# 2. إنشاء التعليق الصوتي باستخدام Edge TTS (مجاني 100%)
# ---------------------------------------------------------
async def generate_voiceover(text, voice_code, output_path="voiceover.mp3"):
    communicate = edge_tts.Communicate(text, voice_code)
    await communicate.save(output_path)
    return output_path

# ---------------------------------------------------------
# 3. جلب مقاطع خلفية مجانية من Pexels
# ---------------------------------------------------------
def download_pexels_video(query, api_key, output_path="background.mp4"):
    if not api_key:
        return False, "يرجى أدخال مفتاح Pexels API"
        
    headers = {"Authorization": api_key}
    url = f"https://api.pexels.com/videos/search?query={query}&per_page=5&orientation=landscape"
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        data = response.json()
        
        if not data.get("videos"):
            return False, f"لم يتم العثور على مقاطع فيديو للكلمة المفتاحية: {query}"
            
        # اختيار أفضل فيديو HD
        video_files = data["videos"][0]["video_files"]
        download_url = None
        for f in video_files:
            if f.get("width") and f["width"] >= 1280:
                download_url = f["link"]
                break
        if not download_url:
            download_url = video_files[0]["link"]
            
        video_data = requests.get(download_url, timeout=30).content
        with open(output_path, "wb") as f:
            f.write(video_data)
            
        return True, output_path
    except Exception as e:
        return False, f"حدث خطأ أثناء تحميل الفيديو: {str(e)}"

# ---------------------------------------------------------
# 4. بناء وإنتاج الفيديو الكامل
# ---------------------------------------------------------
def create_full_video(script_text, voice_choice, keyword, pexels_key, progress=gr.Progress()):
    if not script_text.strip():
        return None, "❌ يرجى كتابة السكريبت أولاً."
    if not keyword.strip():
        return None, "❌ يرجى كتابة كلمة البحث الخاصة بخلفية الفيديو."
        
    progress(0.1, desc="جاري إنشاء التعليق الصوتي...")
    voice_code = VOICES.get(voice_choice, "ar-EG-SalmaNeural")
    audio_file = "voiceover.mp3"
    
    try:
        asyncio.run(generate_voiceover(script_text, voice_code, audio_file))
    except Exception as e:
        return None, f"❌ خطأ في إنشاء الصوت: {str(e)}"
        
    audio_clip = AudioFileClip(audio_file)
    audio_duration = audio_clip.duration
    
    progress(0.4, desc="جاري جلب فيديو الخلفية...")
    bg_file = "background.mp4"
    success, msg = download_pexels_video(keyword, pexels_key, bg_file)
    
    if not success:
        return None, f"❌ {msg}"
        
    progress(0.7, desc="جاري معالجة وتجميع الفيديو...")
    try:
        bg_clip = VideoFileClip(bg_file)
        
        # تكرار الفيديو ليغطي مدة الصوت الكاملة (سواء 5 دقائق أو أكثر)
        if bg_clip.duration < audio_duration:
            loop_count = int(audio_duration // bg_clip.duration) + 1
            bg_clip = concatenate_videoclips([bg_clip] * loop_count)
            
        bg_clip = bg_clip.subclip(0, audio_duration)
        final_clip = bg_clip.set_audio(audio_clip)
        
        output_video = "ai_generated_video.mp4"
        final_clip.write_videofile(output_video, fps=24, codec="libx264", audio_codec="aac")
        
        progress(1.0, desc="تم الانتهاء بنجاح!")
        return output_video, "✅ تم إنشاء الفيديو بنجاح بدون حدود زمنية!"
        
    except Exception as e:
        return None, f"❌ خطأ أثناء تجميع الفيديو: {str(e)}"

# ---------------------------------------------------------
# 5. واجهة الموقع المحلية (تشتغل على المتصفح بدون كلمة سر)
# ---------------------------------------------------------
custom_theme = gr.themes.Soft(
    primary_hue="indigo",
    secondary_hue="cyan"
)

with gr.Blocks(theme=custom_theme, title="AI Video Studio Pro") as app:
    gr.Markdown(
        """
        # 🎬 موقع إنشاء الفيديوهات بالذكاء الاصطناعي (AI Video Generator)
        ### موقعك الخاص والمجاني تماماً - بدون كلمة سر - بدون حد زمني للمقاطع
        """
    )
    
    with gr.Row():
        with gr.Column(scale=1):
            script_input = gr.Textbox(
                label="📝 السكريبت / نص الفيديو",
                placeholder="اكتب النص هنا.. يمكن أن يكون نصاً طويلاً لأكثر من 5 دقائق...",
                lines=10
            )
            voice_dropdown = gr.Dropdown(
                choices=list(VOICES.keys()),
                value="عربي - سلمى (مصر)",
                label="🗣️ اختيار الصوت"
            )
            keyword_input = gr.Textbox(
                label="🔍 كلمة بحث الخلفية (بالإنجليزي)",
                placeholder="مثال: nature, technology, city, space"
            )
            pexels_api_input = gr.Textbox(
                label="🔑 مفتاح Pexels API المجاني",
                placeholder="أدخل مفتاح Pexels الخاص بك هنا...",
                type="password"
            )
            submit_btn = gr.Button("🚀 بدء إنشاء الفيديو", variant="primary")
            
        with gr.Column(scale=1):
            status_output = gr.Textbox(label="📊 حالة المعالجة", interactive=False)
            video_output = gr.Video(label="🎥 الفيديو النهائي الجاهز للتحميل")
            
    submit_btn.click(
        fn=create_full_video,
        inputs=[script_input, voice_dropdown, keyword_input, pexels_api_input],
        outputs=[video_output, status_output]
    )

if __name__ == "__main__":
    # تشغيل الموقع محلياً بدون كلمة سر أو قيود
    app.launch(share=True)
