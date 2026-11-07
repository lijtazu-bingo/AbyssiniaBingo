import os
from gtts import gTTS

# ፎልደሩ ከሌለ ይፍጠር
folder_name = "public/bingo_audio"
if not os.path.exists(folder_name):
    os.makedirs(folder_name)

print("Downloading 75 audio files... Please wait.")

for num in range(1, 76):
    if num <= 15: prefix = 'B'
    elif num <= 30: prefix = 'I'
    elif num <= 45: prefix = 'N'
    elif num <= 60: prefix = 'G'
    else: prefix = 'O'
    
    text = f"{prefix} {num}"
    filename = f"{folder_name}/{prefix}_{num}.mp3"
    
    if not os.path.exists(filename):
        try:
            tts = gTTS(text=text, lang='en', slow=False)
            tts.save(filename)
            print(f"✅ Downloaded: {filename}")
        except Exception as e:
            print(f"❌ Failed: {filename} - {e}")
    else:
        print(f"⏭️ Skipped (exists): {filename}")

print("🎉 All 75 files are ready!")
