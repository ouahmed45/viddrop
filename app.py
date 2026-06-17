import os
import yt_dlp
import stripe
from flask import Flask, render_template, request, send_file, flash, make_response, redirect

app = Flask(__name__)
app.secret_key = "viddrop_secure_web_key"

# Récupère proprement la clé secrète Stripe depuis Render
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads")
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIES_FILE = os.path.join(CURRENT_DIR, "cookies.txt")

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

    # Configuration STRICTEMENT identique au comportement d'un client natif/logiciel
    ydl_opts = {
        'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
        'ffmpeg_location': CURRENT_DIR,
        'logtostderr': True,
        'quiet': True,
        'no_color': True,
        'noplaylist': True,
        'restrictfilenames': True,
        # On force yt-dlp à utiliser les clients iOS et Web embedded qui contournent la détection des serveurs
        'extractor_args': {
            'youtube': {
                'player_client': ['ios', 'web_embedded'],
            }
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'no-cache',
        }
    }

    # Si jamais tu as mis le fichier cookies.txt, il l'utilise en priorité absolue
    if os.path.exists(COOKIES_FILE):
        ydl_opts['cookiefile'] = COOKIES_FILE

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
            except Exception as e:
                print(f"Erreur nettoyage : {e}")

        return response

    except Exception as e:
        error_msg = str(e)
        if "Sign in to confirm you’re not a bot" in error_msg:
            flash("⚠️ Le serveur Render est bloqué par YouTube. Pour télécharger sans aucune limite comme sur ton logiciel PC, glisse simplement un fichier 'cookies.txt' sur ton GitHub.")
        else:
            flash(f"Erreur lors du traitement : {error_msg}")
        return redirect("/")

if __name__ == "__main__":
    app.run()
