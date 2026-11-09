import json
import re
import shutil
import subprocess
import time
import webbrowser
import winsound

from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

import whisper
from openai import OpenAI
from pycaw.pycaw import AudioUtilities
import psutil

# =========================================================
# GRUNDEINSTELLUNGEN
# =========================================================

JARVIS_NAME = "Jarvis"

LM_STUDIO_URL = "http://localhost:1235/v1"

BEVORZUGTES_MODELL = "google/gemma-4-e2b"

WHISPER_MODELL = "base"

AUFNAHME_SEKUNDEN = 7

MIKROFON = (
    "Microphone Array "
    "(Intel® Smart Sound Technology for Digital Microphones)"
)

AKTIVIERUNGSWOERTER = [
    "jarvis",
    "djarvis",
    "tschavis",
    "service",
    "servus",
]


# =========================================================
# DATEIEN UND ORDNER
# =========================================================

BASIS_ORDNER = Path(__file__).resolve().parent

EINGABE_WAV = BASIS_ORDNER / "jarvis_input.wav"

AUSGABE_WAV = BASIS_ORDNER / "jarvis_output.wav"

NOTIZEN_DATEI = BASIS_ORDNER / "jarvis_notizen.json"

PIPER_ORDNER = (
    BASIS_ORDNER
    / "piper_windows_amd64"
    / "piper"
)

PIPER_EXE = PIPER_ORDNER / "piper.exe"

PIPER_MODELL = (
    BASIS_ORDNER
    / "de_DE-thorsten-medium.onnx"
)

PIPER_CONFIG = (
    BASIS_ORDNER
    / "de_DE-thorsten-medium.onnx.json"
)


# =========================================================
# HILFSFUNKTIONEN
# =========================================================

def text_normalisieren(text):

    text = text.lower().strip()

    text = (
        text.replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )

    text = re.sub(r"\s+", " ", text)

    return text


def dateien_pruefen():

    fehlende_dateien = []

    dateien = [
        PIPER_EXE,
        PIPER_MODELL,
        PIPER_CONFIG,
    ]

    for datei in dateien:

        if not datei.exists():

            fehlende_dateien.append(str(datei))

    if fehlende_dateien:

        print()
        print("Diese Piper-Dateien fehlen:")

        for datei in fehlende_dateien:

            print(" -", datei)

        return False

    return True


def ffmpeg_finden():

    ffmpeg = shutil.which("ffmpeg")

    if ffmpeg:

        return ffmpeg

    winget_ordner = (
        Path.home()
        / "AppData"
        / "Local"
        / "Microsoft"
        / "WinGet"
        / "Packages"
    )

    if winget_ordner.exists():

        treffer = list(
            winget_ordner.rglob("ffmpeg.exe")
        )

        if treffer:

            return str(treffer[0])

    return None


# =========================================================
# NOTIZEN
# =========================================================

def notizen_laden():

    if not NOTIZEN_DATEI.exists():

        return []

    try:

        with NOTIZEN_DATEI.open(
            "r",
            encoding="utf-8",
        ) as datei:

            daten = json.load(datei)

        if isinstance(daten, list):

            return daten

    except Exception as fehler:

        print(
            "Notizen konnten nicht geladen werden:",
            fehler,
        )

    return []


def notizen_speichern():

    try:

        with NOTIZEN_DATEI.open(
            "w",
            encoding="utf-8",
        ) as datei:

            json.dump(
                notizen,
                datei,
                ensure_ascii=False,
                indent=2,
            )

    except Exception as fehler:

        print(
            "Notizen konnten nicht gespeichert werden:",
            fehler,
        )


notizen = notizen_laden()


# =========================================================
# FFMPEG SUCHEN
# =========================================================

FFMPEG_EXE = ffmpeg_finden()


# =========================================================
# WHISPER LADEN
# =========================================================

print()
print("Whisper wird geladen...")

try:

    whisper_modell = whisper.load_model(
        WHISPER_MODELL
    )

except Exception as fehler:

    print(
        "Whisper konnte nicht geladen werden:",
        fehler,
    )

    raise SystemExit(1)

print("Whisper ist bereit.")


# =========================================================
# LM STUDIO
# =========================================================

client = OpenAI(
    base_url=LM_STUDIO_URL,
    api_key="lm-studio",
)


def lm_modell_finden():

    try:

        modelle = client.models.list()

        modellnamen = [
            modell.id
            for modell in modelle.data
        ]

        if not modellnamen:

            return None

        if BEVORZUGTES_MODELL in modellnamen:

            return BEVORZUGTES_MODELL

        print()
        print(
            "Bevorzugtes Modell wurde nicht gefunden."
        )

        print(
            "Jarvis verwendet stattdessen:",
            modellnamen[0],
        )

        return modellnamen[0]

    except Exception as fehler:

        print()
        print(
            "LM Studio ist momentan nicht erreichbar."
        )

        print("Adresse:", LM_STUDIO_URL)

        print("Fehler:", fehler)

        return None


LM_MODELL = lm_modell_finden()


# =========================================================
# GESPRÄCHSHISTORIE
# =========================================================

gespraech = [
    {
        "role": "system",
        "content": (
           "Du bist Jarvis, Daniels persönlicher deutschsprachiger Sprachassistent. "
"Sprich Daniel immer mit du an und nenne ihn Daniel. "
"Verwende niemals Sie, Ihnen oder Ihr als Anrede. "
"Sprich natürlich, locker, freundlich und direkt. "
"Antworte meistens kurz und verständlich in höchstens vier Sätzen. "
"Deine Antworten werden laut vorgelesen, deshalb verwende keine Tabellen "
"und keine Markdown-Formatierung. "
"Behaupte niemals, eine Aktion ausgeführt zu haben, wenn das Programm "
"diese Aktion nicht tatsächlich ausgeführt hat."

        ),
    }
]


def verlauf_begrenzen():

    global gespraech

    systemnachricht = gespraech[0]

    letzte_nachrichten = gespraech[1:][-12:]

    gespraech = [
        systemnachricht
    ] + letzte_nachrichten


# =========================================================
# MIKROFONAUFNAHME
# =========================================================

def aufnehmen():
    if not FFMPEG_EXE:
        raise FileNotFoundError(
            "FFmpeg wurde nicht gefunden."
        )

    print()
    print("Ich höre zu...")

    befehl = [
        FFMPEG_EXE,
        "-y",
        "-f", "dshow",
        "-rtbufsize", "100M",
        "-i", f"audio={MIKROFON}",
        "-af", "silencedetect=noise=-40dB:d=1.5",
        "-t", "30",
        "-ac", "1",
        "-ar", "16000",
        str(EINGABE_WAV)
    ]

    prozess = subprocess.Popen(
        befehl,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="ignore"
    )

    for zeile in prozess.stderr:
        if "silence_start:" in zeile:
            try:
                wert = zeile.split(
                    "silence_start:"
                )[1].strip()

                start = float(wert)

                # Stille direkt am Anfang ignorieren
                if start > 0.5:
                    print("Sprechpause erkannt.")

                    prozess.stdin.write("q\n")
                    prozess.stdin.flush()
                    break

            except ValueError:
                pass

    prozess.wait()

    if not EINGABE_WAV.exists():
        raise RuntimeError(
            "Die Mikrofonaufnahme ist fehlgeschlagen."
        )

    print("Aufnahme beendet.")

# =========================================================
# WHISPER SPRACHERKENNUNG
# =========================================================

def verstehen():

    print(
        "Whisper verarbeitet die Aufnahme..."
    )

    ergebnis = whisper_modell.transcribe(
        str(EINGABE_WAV),
        language="de",
        fp16=False,
        condition_on_previous_text=False,
    initial_prompt="Jarvis. Jarvis, wie spät ist es? Jarvis, kannst du mich hören?",

    )

    text = ergebnis.get(
        "text",
        "",
    ).strip()

    if text:

        print("Gehört:", text)

    else:

        print("Keine Sprache erkannt.")

    return text


# =========================================================
# AKTIVIERUNGSWORT
# =========================================================

def aktivierungswort_entfernen(text):

    text_klein = text.lower()

    for aktivierungswort in AKTIVIERUNGSWOERTER:

        position = text_klein.find(
            aktivierungswort
        )

        if position >= 0:

            frage = text[
                position + len(aktivierungswort):
            ]

            frage = frage.strip(
                " ,.!?:;-"
            )

            return True, frage

    return False, text


# =========================================================
# PIPER SPRACHAUSGABE
# =========================================================

def sprechen(text):

    text = str(text).strip()

    if not text:

        return

    print()
    print("Jarvis:", text)
    print("Jarvis spricht...")

    if AUSGABE_WAV.exists():

        try:

            AUSGABE_WAV.unlink()

        except PermissionError:

            time.sleep(0.2)

    befehl = [
        str(PIPER_EXE),
        "--model",
        str(PIPER_MODELL),
        "--config",
        str(PIPER_CONFIG),
        "--output_file",
        str(AUSGABE_WAV),
        "--length_scale",
        "1.05",
        "--sentence_silence",
        "0.25",
    ]

    ergebnis = subprocess.run(
        befehl,
        input=text,
        text=True,
        encoding="utf-8",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    if ergebnis.returncode != 0:

        fehlermeldung = (
            ergebnis.stderr.strip()
            if ergebnis.stderr
            else "Unbekannter Piper-Fehler"
        )

        raise RuntimeError(
            "Piper-Fehler: "
            + fehlermeldung
        )

    if not AUSGABE_WAV.exists():

        raise FileNotFoundError(
            "Piper hat keine Audiodatei erzeugt."
        )

    winsound.PlaySound(
        str(AUSGABE_WAV),
        winsound.SND_FILENAME,
    )


# =========================================================
# LOKALE FUNKTIONEN
# =========================================================

def lokale_funktion(frage):

    normal = text_normalisieren(frage)

    beenden_woerter = [
        "ende",
        "beenden",
        "stopp",
        "stop",
        "tschuss",
        "auf wiedersehen",
    ]

    if normal in beenden_woerter:

        return (
            True,
            "Bis später, Daniel.",
            True,
        )

    if (
        "wie spaet" in normal
        or "uhrzeit" in normal
    ):

        uhrzeit = datetime.now().strftime(
            "%H:%M"
        )

        return (
            True,
            f"Es ist {uhrzeit} Uhr.",
            False,
        )

    if (
        "welches datum" in normal
        or "welcher tag" in normal
    ):

        datum = datetime.now().strftime(
            "%d.%m.%Y"
        )

        return (
            True,
            f"Heute ist der {datum}.",
            False,
        )

    notiz_befehle = [
        "notiz ",
        "notiere ",
        "merke dir ",
    ]

    if any(
        normal.startswith(befehl)
        for befehl in notiz_befehle
    ):

        inhalt = re.sub(
            r"^(notiz|notiere|merke dir)\s+",
            "",
            frage,
            flags=re.IGNORECASE,
        ).strip()

        if not inhalt:

            return (
                True,
                "Ich habe keinen Inhalt "
                "für die Notiz gehört.",
                False,
            )

        notizen.append(
            {
                "text": inhalt,
                "zeit": datetime.now().isoformat(
                    timespec="seconds"
                ),
            }
        )

        notizen_speichern()

        return (
            True,
            "Die Notiz wurde gespeichert.",
            False,
        )

    if (
    "notizen vorlesen" in normal
    or "meine notizen" in normal
    or "welche notizen" in normal
    or "was hast du dir gemerkt" in normal
    or "was hast du gespeichert" in normal
):
        if not notizen:

            return (
                True,
                "Du hast noch keine "
                "gespeicherten Notizen.",
                False,
            )

        letzte_notizen = [
            eintrag.get("text", "")
            for eintrag in notizen[-5:]
        ]

        antwort = (
            "Deine letzten Notizen sind: "
            + ". ".join(letzte_notizen)
        )

        return (
            True,
            antwort,
            False,
        )

    if "notizen loeschen" in normal:

        notizen.clear()

        notizen_speichern()

        return (
            True,
            "Alle Notizen wurden gelöscht.",
            False,
        )

    internetseiten = {
        "youtube": "https://www.youtube.com",
        "google": "https://www.google.de",
        "gmail": "https://mail.google.com",
        "outlook": "https://outlook.office.com",
    }

    if (
        normal.startswith("oeffne ")
        or normal.startswith("starte ")
    ):

        for name, adresse in internetseiten.items():

            if name in normal:

                webbrowser.open(adresse)

                return (
                    True,
                    f"Ich öffne {name}.",
                    False,
                )

    if (
        normal.startswith("suche nach ")
        or normal.startswith("google ")
    ):

        suchtext = re.sub(
            r"^(suche nach|google)\s+",
            "",
            frage,
            flags=re.IGNORECASE,
        ).strip()

        if suchtext:

            suchadresse = (
                "https://www.google.de/search?q="
                + quote_plus(suchtext)
            )

            webbrowser.open(suchadresse)

            return (
                True,
                f"Ich suche nach {suchtext}.",
                False,
            )

        # =====================================================
    # WINDOWS-LAUTSTÄRKE
    # =====================================================

    # Lautstärke auf X Prozent setzen
    treffer = re.search(
        r"lautstaerke.*?(\d{1,3})",
        normal
    )

    if treffer:
        wert = max(0, min(100, int(treffer.group(1))))

        geraet = AudioUtilities.GetSpeakers()
        geraet.volume_percent = wert

        return (
            True,
            f"Lautstärke ist jetzt auf {wert} Prozent.",
            False,
        )

    # Lauter
    if normal in ["lauter", "mach lauter"]:
        geraet = AudioUtilities.GetSpeakers()

        wert = min(
            100,
            geraet.volume_percent + 10
        )

        geraet.volume_percent = wert

        return (
            True,
            f"Lautstärke ist jetzt auf {round(wert)} Prozent.",
            False,
        )

    # Leiser
    if normal in ["leiser", "mach leiser"]:
        geraet = AudioUtilities.GetSpeakers()

        wert = max(
            0,
            geraet.volume_percent - 10
        )

        geraet.volume_percent = wert

        return (
            True,
            f"Lautstärke ist jetzt t auf {round(wert)} Prozent.",
            False,
        )

        # Rechner schließen
    if (
        "schliesse den rechner" in normal
        or "rechner schliessen" in normal
        or "mach den rechner zu" in normal
    ):
        gefunden = False

        for prozess in psutil.process_iter(["name"]):
            try:
                name = (
                    prozess.info["name"] or ""
                ).lower()

                if name == "calculatorapp.exe":
                    prozess.terminate()
                    gefunden = True

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass


        if gefunden:
            return True, "Der Rechner ist geschlossen.", False

        return True, "Der Rechner war nicht geöffnet.", False
           # Downloads öffnen
    if (
        "download" in normal
        and (
            "oeffne" in normal

            or "oeffnet" in normal
            or "oeffnen" in normal
            or "aufmachen" in normal
        )
    ):
        ordner = Path.home() / "Downloads"

        subprocess.Popen([
            "explorer.exe",
            str(ordner)
        ])

        return True, "Ich habe Downloads geöffnet.", False 
    return False, "", False

# =========================================================
# JARVIS DENKT
# =========================================================

def denken(frage):

    global LM_MODELL

    lokale_aktion, antwort, beenden = (
        lokale_funktion(frage)
    )

    if lokale_aktion:

        return antwort, beenden

    if not LM_MODELL:

        LM_MODELL = lm_modell_finden()

    if not LM_MODELL:

        return (
            "LM Studio ist nicht erreichbar. "
            "Starte dort den lokalen Server "
            "und lade ein Modell.",
            False,
        )

    gespraech.append(
        {
            "role": "user",
            "content": frage,
        }
    )

    verlauf_begrenzen()

    try:

        ergebnis = (
            client.chat.completions.create(
                model=LM_MODELL,
                messages=gespraech,
                temperature=0.6,
                            )
        )

        antwort = (
            ergebnis
            .choices[0]
            .message
            .content
            or ""
        ).strip()

        if not antwort:

            antwort = (
                "Ich habe leider keine "
                "Antwort erhalten."
            )

        gespraech.append(
            {
                "role": "assistant",
                "content": antwort,
            }
        )

        verlauf_begrenzen()

        return antwort, False

    except Exception as fehler:

        print()
        print(
            "Fehler bei LM Studio:",
            fehler,
        )

        return (
            "Beim Abrufen der Antwort ist "
            "ein Fehler aufgetreten. "
            "Prüfe LM Studio.",
            False,
        )


# =========================================================
# AUFRÄUMEN
# =========================================================

def aufraeumen():

    dateien = [
        EINGABE_WAV,
        AUSGABE_WAV,
    ]

    for datei in dateien:

        try:

            if datei.exists():

                datei.unlink()

        except OSError:

            pass


# =========================================================
# HAUPTPROGRAMM
# =========================================================

def hauptprogramm():
    gespraechsmodus = False

    if not dateien_pruefen():

        input(
            "\nDrücke Enter zum Beenden..."
        )

        return

    if not FFMPEG_EXE:

        print()
        print(
            "FFmpeg wurde nicht gefunden."
        )

        input(
            "Drücke Enter zum Beenden..."
        )

        return

    print()
    print("Jarvis ist bereit.")

    print(
        "Sage zum Beispiel: "
        "Jarvis, wie spät ist es?"
    )

    print(
        "Zum Beenden sage: "
        "Jarvis, Ende."
    )

    try:

        sprechen(
            "Jarvis ist bereit."
        )

    except Exception as fehler:

        print(
            "Sprachausgabe beim Start "
            "fehlgeschlagen:",
            fehler,
        )
        gespraechsmodus = False

    while True:

        try:

            aufnehmen()

            text = verstehen()

            if not text:

                continue
            # Gesprächsmodus mit "Danke Jarvis" beenden
            text_klein = text.lower().strip()

            if gespraechsmodus and (
                "danke jarvis" in text_klein
                or "danke, jarvis" in text_klein
            ):
                sprechen("Gerne, Daniel.")
                gespraechsmodus = False
                continue

            if aktiviert:
               gespraechsmodus = True

            if not frage:
                sprechen("Ja, Daniel?")
                continue

            elif gespraechsmodus:
                 frage = text

            else:
                 print("Aktivierungswort nicht erkannt.")
                 continue

                 antwort, beenden = denken(frage)
                 sprechen(antwort)

            if beenden:
               break

        except KeyboardInterrupt:
            print()
            print("Jarvis wurde beendet.")
            break


        except Exception as fehler:         				                     	    print()
            print("Fehler:", fehler)

            try:

                sprechen(
                    "Es ist ein Fehler aufgetreten. "
                    "Die genaue Meldung steht "
                    "im Fenster."
                )

            except Exception:

                pass

            time.sleep(1)

    aufraeumen()


# =========================================================
# PROGRAMM STARTEN
# =========================================================

if __name__ == "__main__":

    hauptprogramm()