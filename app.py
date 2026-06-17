import os
import yt_dlp
import stripe
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

    ydl_opts = {
        'outtmpl': os.path.join(DOWNLOAD_DIR, '%(title)s.%(ext)s'),
        'logtostderr': True,
        'quiet': True,
        'no_color': True,
        'noplaylist': True,
        'restrictfilenames': True,
        'extractor_args': {'youtube': {'player_client': ['web']}},
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        }
    }

    if fmt == "MP3":
        mimetype = "audio/mpeg"
        ydl_opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '128'}],
        })
    elif fmt == "WEBM":
        mimetype = "video/webm"
        ydl_opts.update({
            'format': 'best[ext=webm]/best',
        })
    else:
        mimetype = "video/mp4"
        ydl_opts.update({
            'format': 'best[ext=mp4]/best',
        })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            target_file = ydl.prepare_filename(info)
            
            base_path = os.path.splitext(target_file)[0]
            if fmt == "MP3" and not target_file.endswith('.mp3'): 
                target_file = base_path + ".mp3"

        if not os.path.exists(target_file):
            raise FileNotFoundError("Échec de création du conteneur.")

        filename = os.path.basename(target_file)
        response = make_response(send_file(target_file, as_attachment=True, download_name=filename, mimetype=mimetype))
        response.headers["Content-Disposition"] = f"attachment; filename=\"{filename}\""

        @response.call_on_close
        def cleanup():
            try:
                if os.path.exists(target_file):
                    os.remove(target_file)
            except Exception as e:
                print(f"Erreur nettoyage : {e}")

        return response
