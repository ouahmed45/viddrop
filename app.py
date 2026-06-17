import os
import yt_dlp
import stripe
import requests
from flask import Flask, render_template, request, send_file, flash, make_response, redirect

app = Flask(__name__)
app.secret_key = "viddrop_secure_web_key"

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/premium", methods=["GET"])
def premium_page():
    return render_template("premium.html")

@app.route("/success", methods=["GET"])
def success_page():
    return render_template("success.html")

@app.route("/download", methods=["POST"])
def download_video():
    url = request.form.get("url")
    fmt = request.form.get("format")

    if not url:
        flash("Veuillez fournir un lien valide.")
        return redirect("/")

    url = url.strip()

    # --- API DE SECOURS (Si Render est bloqué) ---
    # Cette API publique convertit et télécharge sans subir les blocages d'IP de Render
    try:
        api_url = f"https://api.cobalt.tools/api/json"
        payload = {
            "url": url,
            "isAudioOnly": True if fmt == "MP3" else False,
            "aFormat": "mp3" if fmt == "MP3" else "best",
            "vQuality": "720"
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        response = requests.post(api_url, json=payload, headers=headers, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if "url" in data:
                # L'API a réussi ! On redirige directement l'utilisateur vers le fichier à télécharger
                return redirect(data["url"])
    except Exception:
        pass # Si l'API échoue ou est hors-ligne, on retombe sur yt-dlp classique ci-dessous

    # --- MÉTHODE CLASSIQUE YT-DLP (En cas d'échec de l'API) ---
    ydl_opts = {
        'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
        'ffmpeg_location': CURRENT_DIR,
        'logtostderr': True,
        'quiet': True,
        'no_color': True,
        'noplaylist': True,
        'restrictfilenames': True,
        'extractor_args': {'youtube': {'player_client': ['ios', 'web_embedded']}},
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'
        }
    }

    if fmt == "MP3":
        mimetype = "audio/mpeg"
        ydl_opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
        })
    else:
        mimetype = "video/mp4"
        ydl_opts.update({
            'format': 'bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]/best[ext=mp4]/best',
            'merge_output_format': 'mp4',
        })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            target_file = ydl.prepare_filename(info)
            base_path = os.path.splitext(target_file)[0]
            if fmt == "MP3": target_file = base_path + ".mp3"
            else: target_file = base_path + ".mp4"

        if not os.path.exists(target_file):
            raise FileNotFoundError()

        filename = os.path.basename(target_file)
        res = make_response(send_file(target_file, as_attachment=True, download_name=filename, mimetype=mimetype))
        
        @res.call_on_close
        def cleanup():
            if os.path.exists(target_file): os.remove(target_file)

        return res

    except Exception:
        flash("⚠️ Erreur : YouTube bloque actuellement ce serveur. Réessaie dans quelques instants ou utilise une autre vidéo.")
        return redirect("/")

if __name__ == "__main__":
    app.run()
