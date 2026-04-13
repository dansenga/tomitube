from __future__ import annotations

import os
import re
import shutil
import tempfile
import html
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

import streamlit as st
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError


APP_TITLE = "Tomitube"
TARGET_QUALITIES = [360, 720, 1080]
VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,}$")


class TomitubeError(Exception):
	"""Base exception for all user-facing app errors."""


class InvalidUrlError(TomitubeError):
	"""Raised when URL does not match a supported YouTube pattern."""


class VideoUnavailableError(TomitubeError):
	"""Raised when YouTube reports an unavailable/private/geo-blocked video."""


class NetworkError(TomitubeError):
	"""Raised when connection issues prevent metadata or media retrieval."""


def init_page() -> None:
	st.set_page_config(
		page_title=APP_TITLE,
		page_icon="🎬",
		layout="centered",
		initial_sidebar_state="collapsed",
	)


def inject_styles() -> None:
	st.markdown(
		"""
		<style>
		@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=Syne:wght@600;700;800&display=swap');

		:root {
			--bg: #060606;
			--card: #111111;
			--card-soft: #161616;
			--text: #ffffff;
			--muted: #bfbfbf;
			--line: #2a2a2a;
			--accent: #d9d9d9;
		}

		html, body, [class*="css"], .stApp {
			background: radial-gradient(circle at 15% 5%, #151515 0%, #090909 40%, var(--bg) 100%);
			color: var(--text);
			font-family: 'Space Grotesk', sans-serif;
		}

		.main > div {
			padding-top: 1.5rem;
		}

		.hero {
			border: 1px solid var(--line);
			border-radius: 20px;
			background: linear-gradient(155deg, #111111 0%, #080808 100%);
			padding: 1.3rem 1.4rem;
			margin-bottom: 1rem;
			animation: rise 450ms ease-out;
		}

		.hero h1 {
			font-family: 'Syne', sans-serif;
			font-weight: 800;
			letter-spacing: 0.3px;
			margin: 0;
			line-height: 1.1;
			font-size: 2rem;
		}

		.hero p {
			margin: 0.45rem 0 0;
			color: var(--muted);
			font-size: 0.95rem;
		}

		.pulse {
			display: inline-block;
			width: 8px;
			height: 8px;
			border-radius: 999px;
			background: #d6d6d6;
			margin-right: 8px;
			box-shadow: 0 0 0 rgba(255,255,255,0.35);
			animation: pulse 2s infinite;
		}

		.video-card {
			border: 1px solid var(--line);
			border-radius: 18px;
			background: var(--card);
			padding: 1rem;
			margin: 0.4rem 0 1rem;
			animation: rise 500ms ease-out;
		}

		.meta {
			color: var(--muted);
			font-size: 0.9rem;
			margin-top: 0.4rem;
		}

		.chips {
			margin-top: 0.8rem;
			display: flex;
			flex-wrap: wrap;
			gap: 0.45rem;
		}

		.chip {
			border: 1px solid #373737;
			border-radius: 999px;
			padding: 0.18rem 0.58rem;
			font-size: 0.78rem;
			color: #f2f2f2;
			background: #171717;
		}

		.chip.off {
			color: #6f6f6f;
			border-color: #2a2a2a;
			background: #0f0f0f;
			text-decoration: line-through;
		}

		.stTextInput > div > div > input {
			background: #101010;
			border: 1px solid #333333;
			border-radius: 12px;
			color: white;
			min-height: 46px;
		}

		.stTextInput > div > div > input:focus {
			border-color: #888888;
			box-shadow: 0 0 0 1px #6e6e6e;
		}

		.stButton > button, .stDownloadButton > button {
			background: linear-gradient(180deg, #f3f3f3 0%, #d5d5d5 100%);
			color: #0b0b0b;
			border: 0;
			border-radius: 12px;
			min-height: 44px;
			font-weight: 700;
			transition: all 170ms ease;
		}

		.stButton > button:hover, .stDownloadButton > button:hover {
			transform: translateY(-1px);
			filter: brightness(1.04);
			box-shadow: 0 7px 18px rgba(255,255,255,0.15);
		}

		.stRadio > div {
			background: #0f0f0f;
			border: 1px solid var(--line);
			border-radius: 12px;
			padding: 0.4rem 0.8rem;
		}

		.history-card {
			border: 1px solid var(--line);
			border-radius: 14px;
			background: var(--card-soft);
			padding: 0.8rem 0.9rem;
			margin-bottom: 0.6rem;
		}

		@keyframes rise {
			from { opacity: 0; transform: translateY(8px); }
			to { opacity: 1; transform: translateY(0); }
		}

		@keyframes pulse {
			0% { box-shadow: 0 0 0 0 rgba(255,255,255,0.35); }
			70% { box-shadow: 0 0 0 10px rgba(255,255,255,0); }
			100% { box-shadow: 0 0 0 0 rgba(255,255,255,0); }
		}

		@media (max-width: 768px) {
			.hero h1 {
				font-size: 1.6rem;
			}
			.main > div {
				padding-top: 1rem;
			}
		}
		</style>
		""",
		unsafe_allow_html=True,
	)


def init_state() -> None:
	defaults: dict[str, Any] = {
		"video_info": None,
		"analyzed_url": "",
		"download_ready": None,
		"download_history": [],
	}
	for key, value in defaults.items():
		if key not in st.session_state:
			st.session_state[key] = value


def is_valid_youtube_url(url: str) -> bool:
	clean_url = url.strip()
	if not clean_url:
		return False

	if not clean_url.startswith(("http://", "https://")):
		clean_url = f"https://{clean_url}"

	try:
		parsed = urlparse(clean_url)
	except Exception:
		return False

	host = parsed.netloc.lower().split(":")[0]
	if host.startswith("www."):
		host = host[4:]

	video_id = ""

	if host == "youtu.be":
		video_id = parsed.path.strip("/").split("/")[0]
	elif host.endswith("youtube.com"):
		path_parts = [part for part in parsed.path.split("/") if part]

		if parsed.path == "/watch":
			video_id = parse_qs(parsed.query).get("v", [""])[0]
		elif len(path_parts) >= 2 and path_parts[0] in {"shorts", "embed", "live"}:
			video_id = path_parts[1]

	return bool(VIDEO_ID_RE.match(video_id))


def format_duration(seconds: int | None) -> str:
	if not seconds:
		return "Inconnue"
	hours, remainder = divmod(seconds, 3600)
	minutes, secs = divmod(remainder, 60)
	if hours:
		return f"{hours:02d}:{minutes:02d}:{secs:02d}"
	return f"{minutes:02d}:{secs:02d}"


def classify_download_error(error: Exception) -> TomitubeError:
	message = str(error)
	lower = message.lower()

	if "unsupported url" in lower or "invalid url" in lower:
		return InvalidUrlError("URL YouTube invalide. Vérifie le lien et réessaie.")

	if any(token in lower for token in ["video unavailable", "private video", "is unavailable", "not available"]):
		return VideoUnavailableError("Cette vidéo n'est pas disponible (privée, supprimée ou restreinte).")

	if any(
		token in lower
		for token in [
			"timed out",
			"unable to download webpage",
			"temporary failure in name resolution",
			"connection",
		]
	):
		return NetworkError("Problème de connexion. Vérifie internet puis réessaie.")

	if "ffmpeg is not installed" in lower:
		return TomitubeError("FFmpeg est requis pour assembler la vidéo/audio et convertir en MP3.")

	if "403" in lower or "forbidden" in lower:
		return TomitubeError(
			"YouTube bloque ce téléchargement depuis le serveur. Réessaie avec une autre qualité ou une autre vidéo."
		)

	return TomitubeError(f"Échec du téléchargement: {message}")


def get_video_info(url: str) -> dict[str, Any]:
	if not is_valid_youtube_url(url):
		raise InvalidUrlError("URL YouTube invalide. Utilise un lien youtube.com ou youtu.be.")

	options: dict[str, Any] = {
		"quiet": True,
		"no_warnings": True,
		"skip_download": True,
		"noplaylist": True,
		"socket_timeout": 15,
	}

	try:
		with YoutubeDL(options) as ydl:
			info = ydl.extract_info(url, download=False)
	except DownloadError as exc:
		raise classify_download_error(exc) from exc
	except Exception as exc:  # pragma: no cover - defensive fallback
		raise TomitubeError(f"Impossible d'analyser la vidéo: {exc}") from exc

	formats = info.get("formats", []) or []
	quality_presence: dict[int, bool] = {}
	for quality in TARGET_QUALITIES:
		quality_presence[quality] = any(
			fmt.get("vcodec") != "none" and fmt.get("height") == quality for fmt in formats
		)

	available_quality_list = [q for q, is_available in quality_presence.items() if is_available]

	return {
		"title": info.get("title", "Titre inconnu"),
		"duration": format_duration(info.get("duration")),
		"thumbnail": info.get("thumbnail"),
		"qualities": quality_presence,
		"quality_options": available_quality_list,
		"webpage_url": info.get("webpage_url", url),
	}


def video_format_selector(quality: int) -> str:
	# Fallback chain: prefer mp4 video + m4a audio, then any audio-backed progressive stream.
	return (
		f"bestvideo[ext=mp4][height<={quality}]+bestaudio[ext=m4a]/"
		f"bestvideo[height<={quality}]+bestaudio/"
		f"best[ext=mp4][height<={quality}][acodec!=none]/"
		f"best[height<={quality}][acodec!=none]"
	)


def video_format_selector_progressive(quality: int) -> str:
	# Prefer progressive (non-fragmented) streams first; often more reliable on cloud IPs.
	return (
		f"best[ext=mp4][height<={quality}][acodec!=none][protocol!*=m3u8][protocol!*=dash]/"
		f"best[height<={quality}][acodec!=none][protocol!*=m3u8][protocol!*=dash]"
	)


def audio_format_selector_progressive() -> str:
	return "bestaudio[protocol!*=m3u8][protocol!*=dash]/bestaudio/best"


class ProgressReporter:
	def __init__(self, bar: Any, text_box: Any):
		self.bar = bar
		self.text_box = text_box

	def __call__(self, progress: dict[str, Any]) -> None:
		status = progress.get("status")

		if status == "downloading":
			downloaded = progress.get("downloaded_bytes", 0)
			total = progress.get("total_bytes") or progress.get("total_bytes_estimate")
			speed = progress.get("speed")
			eta = progress.get("eta")

			if total:
				ratio = min(downloaded / total, 1.0)
				self.bar.progress(ratio)
				speed_text = f" | {speed / 1_048_576:.2f} MB/s" if speed else ""
				eta_text = f" | ETA: {eta}s" if eta is not None else ""
				self.text_box.info(f"Téléchargement: {ratio * 100:.1f}%{speed_text}{eta_text}")
			else:
				self.text_box.info("Téléchargement en cours...")

		elif status == "finished":
			self.bar.progress(1.0)
			self.text_box.info("Téléchargement terminé. Finalisation...")


def _pick_latest_file(folder: str) -> str:
	files = [
		os.path.join(folder, file_name)
		for file_name in os.listdir(folder)
		if os.path.isfile(os.path.join(folder, file_name))
	]
	if not files:
		raise TomitubeError("Aucun fichier généré. Réessaie avec une autre qualité.")
	return max(files, key=os.path.getmtime)


def download_media(
	url: str,
	mode: str,
	quality: int | None,
	progress_bar: Any,
	status_box: Any,
) -> dict[str, Any]:
	tmp_dir = tempfile.mkdtemp(prefix="tomitube_")
	output_template = os.path.join(tmp_dir, "%(title).80s-%(id)s.%(ext)s")

	base_options: dict[str, Any] = {
		"outtmpl": output_template,
		"noplaylist": True,
		"quiet": True,
		"no_warnings": True,
		"merge_output_format": "mp4",
		"retries": 3,
		"fragment_retries": 2,
		"abort_on_unavailable_fragments": True,
		"socket_timeout": 15,
		"force_ipv4": True,
		"geo_bypass": True,
		"concurrent_fragment_downloads": 1,
		"http_headers": {
			"User-Agent": (
				"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
				"(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
			),
			"Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
		},
		"progress_hooks": [ProgressReporter(progress_bar, status_box)],
	}

	if mode == "video" and quality is None:
		raise TomitubeError("Aucune qualité vidéo sélectionnée.")

	format_candidates: list[str]
	if mode == "video":
		format_candidates = [
			video_format_selector_progressive(quality),
			video_format_selector(quality),
		]
	else:
		format_candidates = [
			audio_format_selector_progressive(),
			"bestaudio/best",
		]

	client_profiles = [
		["android"],
		["web", "android"],
	]

	last_error: Exception | None = None

	for clients in client_profiles:
		for fmt in format_candidates:
			options = dict(base_options)
			options["format"] = fmt
			options["extractor_args"] = {"youtube": {"player_client": clients}}

			if mode == "audio":
				options["postprocessors"] = [
					{
						"key": "FFmpegExtractAudio",
						"preferredcodec": "mp3",
						"preferredquality": "192",
					}
				]

			try:
				with YoutubeDL(options) as ydl:
					ydl.extract_info(url, download=True)

				file_path = _pick_latest_file(tmp_dir)
				with open(file_path, "rb") as media_file:
					data = media_file.read()

				file_name = os.path.basename(file_path)
				mime = "video/mp4" if mode == "video" else "audio/mpeg"

				return {
					"filename": file_name,
					"mime": mime,
					"bytes": data,
					"size_mb": len(data) / (1024 * 1024),
				}
			except DownloadError as exc:
				last_error = exc
				continue

	try:
		if last_error is not None:
			raise classify_download_error(last_error) from last_error
		raise TomitubeError("Échec du téléchargement sans détail yt-dlp exploitable.")
	except Exception as exc:  # pragma: no cover - defensive fallback
		raise TomitubeError(f"Échec inattendu: {exc}") from exc
	finally:
		shutil.rmtree(tmp_dir, ignore_errors=True)


def render_header() -> None:
	st.markdown(
		"""
		<div class="hero">
			<h1><span class="pulse"></span>Tomitube</h1>
			<p>Téléchargeur YouTube.</p>
		</div>
		""",
		unsafe_allow_html=True,
	)


def render_video_card(video_info: dict[str, Any]) -> None:
	chips = []
	for q in TARGET_QUALITIES:
		css_class = "chip" if video_info["qualities"].get(q) else "chip off"
		status = "disponible" if video_info["qualities"].get(q) else "indisponible"
		chips.append(f'<span class="{css_class}">{q}p {status}</span>')

	chip_html = "".join(chips)
	title = html.escape(video_info["title"])
	duration = video_info["duration"]

	st.markdown(
		f"""
		<div class="video-card">
			<h3 style="margin:0;">{title}</h3>
			<div class="meta">Durée: {duration}</div>
			<div class="chips">{chip_html}</div>
		</div>
		""",
		unsafe_allow_html=True,
	)


def render_thumbnail(thumbnail_url: str) -> None:
	# Compatibility fallback for older Streamlit builds without use_container_width.
	try:
		st.image(thumbnail_url, use_container_width=True)
	except TypeError:
		st.image(thumbnail_url, use_column_width=True)


def render_history() -> None:
	history = st.session_state.download_history
	if not history:
		return

	st.markdown("### Historique de session")
	for entry in history[:8]:
		st.markdown(
			f"""
			<div class="history-card">
				<strong>{entry['title']}</strong><br/>
				<span style="color:#bdbdbd; font-size:0.85rem;">
					{entry['mode']} | {entry['quality']} | {entry['size']} | {entry['timestamp']}
				</span>
			</div>
			""",
			unsafe_allow_html=True,
		)


def analyze_if_needed(url: str, force: bool) -> None:
	clean_url = url.strip()
	if not clean_url:
		return

	should_run = force or clean_url != st.session_state.analyzed_url
	if not should_run:
		return

	# Auto-analysis should stay silent until URL looks valid.
	if not is_valid_youtube_url(clean_url):
		st.session_state.video_info = None
		st.session_state.analyzed_url = clean_url
		if force:
			st.error("URL YouTube invalide. Utilise un lien youtube.com ou youtu.be.")
		return

	try:
		with st.spinner("Analyse de la vidéo..."):
			info = get_video_info(clean_url)
		st.session_state.video_info = info
		st.session_state.analyzed_url = clean_url
		st.session_state.download_ready = None
	except TomitubeError as exc:
		st.session_state.video_info = None
		st.session_state.analyzed_url = clean_url
		st.error(str(exc))


def render_download_section(url: str, video_info: dict[str, Any]) -> None:
	mode_label = st.radio(
		"Type de téléchargement",
		options=["Vidéo MP4 (avec audio)", "Audio MP3 uniquement"],
		horizontal=True,
	)
	mode = "video" if mode_label.startswith("Vidéo") else "audio"

	selected_quality = None
	if mode == "video":
		options = video_info.get("quality_options", [])
		if not options:
			st.warning("Aucune qualité vidéo MP4 exploitable parmi 360p/720p/1080p.")
			return
		selected_quality = st.selectbox(
			"Qualité vidéo",
			options=options,
			format_func=lambda q: f"{q}p",
		)

	if st.button("Lancer le téléchargement", use_container_width=True):
		progress_bar = st.progress(0)
		status_box = st.empty()

		try:
			payload = download_media(
				url=video_info["webpage_url"],
				mode=mode,
				quality=selected_quality,
				progress_bar=progress_bar,
				status_box=status_box,
			)
			status_box.success("Fichier prêt.")

			mode_text = "MP4 vidéo" if mode == "video" else "MP3 audio"
			quality_text = f"{selected_quality}p" if selected_quality else "Audio"
			now = datetime.now().strftime("%d/%m/%Y %H:%M")

			st.session_state.download_ready = payload
			st.session_state.download_history.insert(
				0,
				{
					"title": video_info["title"],
					"mode": mode_text,
					"quality": quality_text,
					"size": f"{payload['size_mb']:.2f} MB",
					"timestamp": now,
				},
			)
		except TomitubeError as exc:
			status_box.error(str(exc))

	if st.session_state.download_ready:
		payload = st.session_state.download_ready
		st.download_button(
			label="Télécharger le fichier",
			data=payload["bytes"],
			file_name=payload["filename"],
			mime=payload["mime"],
			use_container_width=True,
		)


def main() -> None:
	init_page()
	inject_styles()
	init_state()
	render_header()

	col1, col2 = st.columns([4, 1])
	with col1:
		input_url = st.text_input(
			"URL YouTube",
			placeholder="https://www.youtube.com/watch?v=...",
			label_visibility="visible",
		)
	with col2:
		force_analyze = st.button("Analyser")

	analyze_if_needed(input_url, force=force_analyze)

	video_info = st.session_state.video_info
	if not input_url.strip():
		st.info("Colle une URL YouTube pour démarrer.")
		render_history()
		return

	if video_info:
		if video_info.get("thumbnail"):
			render_thumbnail(video_info["thumbnail"])
		render_video_card(video_info)

		with st.expander("Prévisualisation vidéo", expanded=True):
			st.video(video_info["webpage_url"])

		render_download_section(input_url, video_info)

	render_history()


if __name__ == "__main__":
	main()
