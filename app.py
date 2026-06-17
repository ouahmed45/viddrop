import os
import base64
import tempfile
import yt_dlp
import stripe
from flask import Flask, render_template, request, send_file, flash, make_response, redirect

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "viddrop_secure_web_key")

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

def get_cookies_file():
    """Crée un fichier cookies temporaire depuis la variable d'env base64."""
    b64 = os.getenv("YOUTUBE_COOKIES_B64")
    if not b64:
        return None
    try:
        decoded = base64.b64decode(b64).decode("utf-8")
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
        tmp.write(decoded)
        tmp.flush()
        tmp.close()
        return tmp.name
    except Exception as e:
        print(f"Erreur décodage cookies : {e}")
        return None

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

@app.route("/create-checkout-session", methods=["POST"])
def create_checkout_session():
    try:
        if not stripe.api_key:
            return redirect("/success")

        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'eur',
                    'product_data': {
                        'name': 'ViddRop Professionnel (Logiciel PC)',
                        'description': 'Licence définitive — Vitesse illimitée sans publicité.',
                    },
                    'unit_amount': 1999,
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url='https://viddrop.onrender.com/success',
            cancel_url='https://viddrop.onrender.com/premium',
        )
        return redirect(checkout_session.url, code=303)
    except Exception as e:
        return str(e), 400

@app.route("/download", methods=["POST"])
def download_video():
    url = request.form.get("url")
    fmt = request.form.get("format")

    if not url:
        flash("Veuillez fournir un lien valide.")
        return redirect("/")

    url = url.strip()

    cookies_path = get_cookies_file()

    ydl_opts = {
        'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
        'ffmpeg_location': CURRENT_DIR,
        'logtostderr': True,
        'quiet': True,
        'no_color': True,
        'noplaylist': True,
        'restrictfilenames': True,
        'cookiefile': cookies_path,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        },
        'extractor_args': {
            'youtube': {
                'player_client': ['web', 'android'],
                'player_skip': ['webpage', 'config'],
            }
        },
        'sleep_interval': 1,
        'max_sleep_interval': 3,
    }

    if fmt == "MP3":
        filename_ext = "mp3"
        mimetype = "audio/mpeg"
        ydl_opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
        })
    elif fmt == "WEBM":
        filename_ext = "webm"
        mimetype = "video/webm"
        ydl_opts.update({'format': 'bestvideo+bestaudio/best', 'merge_output_format': 'webm'})
    else:
        filename_ext = "mp4"
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
            elif fmt == "MP4": target_file = base_path + ".mp4"
            elif fmt == "WEBM": target_file = base_path + ".webm"

        if not os.path.exists(target_file):
            raise FileNotFoundError("Erreur de conversion.")

        filename = os.path.basename(target_file)
        response = make_response(send_file(target_file, as_attachment=True, download_name=filename, mimetype=mimetype))
        response.headers["Content-Disposition"] = f"attachment; filename=\"{filename}\""
        response.headers["X-Content-Type-Options"] = "nosniff"

        @response.call_on_close
        def cleanup():
            try:
                if os.path.exists(target_file):
                    os.remove(target_file)
                if cookies_path and os.path.exists(cookies_path):
                    os.remove(cookies_path)
            except Exception as e:
                print(f"Erreur nettoyage : {e}")

        return response

    except Exception as e:
        flash(f"Erreur lors du traitement : {str(e)}")
        return redirect("/")

if __name__ == "__main__":
    app.run()
