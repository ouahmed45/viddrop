import os
import yt_dlp
import stripe
from flask import Flask, render_template, request, send_file, flash, make_response, redirect

app = Flask(__name__)
app.secret_key = "viddrop_secure_web_key"

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")

# MODIFICATION RENDER : Utilisation du dossier /tmp sous Linux pour avoir les droits d'écriture
DOWNLOAD_DIR = "/tmp/viddrop_downloads"
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

    # --- SÉCURISATION & RECONSTITUTION DES COOKIES POUR RENDER ---
    chemin_cookies = os.path.join(DOWNLOAD_DIR, "cookies_render.txt")
    contenu_cookies = os.getenv("YT_COOKIES_CONTENT")
    
    if not contenu_cookies:
        flash("Erreur de configuration : Les cookies d'authentification YouTube sont absents sur le serveur.")
        return redirect("/")
    
    # On écrit temporairement les cookies dans /tmp
    with open(chemin_cookies, "w", encoding="utf-8") as f:
        f.write(contenu_cookies)

    # Configuration de base de yt-dlp (on y injecte notre fichier de cookies)
    ydl_opts = {
        'cookiefile': chemin_cookies, # <--- Ajout des cookies ici
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
                print(f"Erreur nettoyage vidéo : {e}")

        return response

    except Exception as e:
        flash(f"Erreur lors du traitement : {str(e)}")
        return redirect("/")

    finally:
        # NETTOYAGE CRUCIAL : On supprime TOUJOURS le fichier cookies dès que yt-dlp a fini
        if os.path.exists(chemin_cookies):
            try:
                os.remove(chemin_cookies)
            except Exception as e:
                print(f"Erreur nettoyage cookies : {e}")

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
