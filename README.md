# OllamaVibeDesk v2.16.1

Offline-orientierte PyQt6-Desktopoberfläche für lokale **Ollama**-Modelle mit Chat-Historie, Streaming, Windows-SAPI/VibeVoice-TTS, VibeVoice-ASR-Mikrofoneingabe, Auto-Answer, Projekt-ZIPs, Plugins, Langzeitgedächtnis und portabler TiddlyWiki-Wissensquelle.

In v2.16.1 bleiben Statusanzeige und Seitenleiste unter Windows bei verschiedenen Auflösungen verschiebbar; der Installer zeigt einen Fortschrittsbalken und liefert bei einem Prüffehler direkt die letzten Logzeilen. In v2.16.0 setzt Auto Answer nach dem erneuten Einschalten eine abgeschlossene Unterhaltung fort. Ein animiertes Symbol links unten zeigt, ob das Modell vorbereitet wird, auf Tokens wartet, gerade denkt oder schreibt, ein Werkzeug benutzt oder auf die nächste Runde übergeht. Nach längerer Zeit ohne neue Modell-Daten zeigt es die verstrichene Zeit; bei einem Abbruch oder Limit den Grund. Ein fehlendes Audio-Abschlussereignis blockiert eine bereits vorbereitete Runde nicht mehr. Die Berechtigungen für Drucker, 3D-Drucker und Robotik aus v2.15.0 bleiben erhalten.

Frühere Änderungen und technische Details stehen in `CHANGELOG.md`.

## Wichtige Funktionen

- lokale Ollama-Modelle auswählen und Antworten streamen
- persistente Chats unter `app_data/chats/`
- persistenter Tokenzähler für eingehende und ausgehende Tokens plus aktuelle Kontextbelegung; native Ollama-Werte werden bevorzugt, rekonstruierte Altwerte sichtbar als Näherung markiert
- manueller Kontext-Neustart mit ursprünglicher Aufgabe, bis zu drei vollständigen Dialogrunden und wiederhergestellter Projekt-Arbeitskopie
- optionaler autonomer Kontext-Neustart im Auto-Answer-Modus mit strikter Modellentscheidung, Sicherheitsgrenze und unverändert erhaltenem Quellchat
- Auto-Answer-Modus mit drei Quellen, die zusammen immer 100 % ergeben:
  - ELIZA
  - separate lokale Auto-Answer-LLM
  - sprachspezifische Zufallsphrasen als verbleibender Anteil
- eigenes Modell, Tokenlimit und eigener Persönlichkeit/System-Prompt für die Auto-Answer-LLM
- getrennte sprachspezifische Auto-Answer-Dateien und Editoren
- 25 optionale Zielführungs-Presets mit einstellbarer Stärke und getrenntem Einfluss auf Zufallsphrasen und Auto-Answer-LLM
- Windows-SAPI, der Python-Realtime-TTS-Wrapper und die geprüften VibeVoice-GGUF-TTS-Modelle von CrispASR
- integrierter Einstellungsbereich mit visuellen Abschnitten und linker Bereichsnavigation
- scrollbarer Plugin-Bereich mit getrennten Berechtigungen für Kommandozeile, PowerShell, Bilder/Webcam, Sensoren, Standort, Internetrecherche, Drucker, 3D-Drucker und Robotik
- optionale Audio-Postproduktion (Chorus, Echo, Vocoder/Robotik und Raum/Hall) mit separater `_postproduction.wav`; Originalaufnahmen bleiben unverändert
- Mikrofonaufnahme mit VibeVoice-ASR; der erkannte Text wird editierbar in das Nachrichtenfeld eingesetzt
- getrennte Stimmen und Stimmgestaltung für Benutzer und Assistent: Tempo, Tonhöhe, Lautstärke, Profilstärke sowie natürlich, tief/männlich, hell/weiblich, Erzähler, dramatisch, robotisch, angetrunken, Comic und flüsternd
- Thinking-Inhalte sichtbar, aber nicht in der Sprachausgabe
- Codeblöcke werden nicht vorgelesen und zusätzlich nach erkanntem Dateityp unter `OUTPUTS/code_blocks/` gespeichert
- Projekt-ZIPs korrigieren eindeutig falsche `.txt`-Endungen, erkennen Einstiegspunkte und enthalten statische Struktur-/Syntaxberichte
- unvollständige Godot-Ausgaben mit vorhandener Szene erhalten eine protokollierte minimale `project.godot`; Modellcode bleibt unverändert
- automatische Folge-Chats bei wachsendem Kontext
- automatische Fortsetzung einzelner durch Ollamas Ausgabelimit unterbrochener Antworten; vollständig abgeschlossene Dateien werden bei einem Abbruch als gekennzeichneter Teilstand gerettet
- themenabhängige, durchnummerierte Namen für Folge-Chats statt eines immer gleichen Fortsetzungsnamens
- Reasoning/Thinking pro Ollama-Modell: Aus, automatisch bei Code, Low, Medium oder High
- hardwareabhängige Ollama-Kontextgröße mit manueller Übersteuerung
- lokale Datei-/Medienreferenzen und selektives chatübergreifendes Langzeitgedächtnis
- optionale TiddlyWiki-kompatible Wissensquelle mit lokaler `brain.html`
- externe JSON-Themes, darunter Light, Dark, Sepia, Ocean, Matrix, Hellfire, Purple, Aurora und **Amiga ECS**
- detaillierbares JSONL-Debuglog
- Konfigurationsprofile laden/speichern

## Persönlichkeits-Presets

- 35 eigenständige JSON-Persönlichkeiten für die simulierte Benutzerrolle im Auto-Answer-Modus.
- 35 eigenständige JSON-Persönlichkeiten für die antwortende LLM.
- Weibliche, männliche und neutrale Presets mit einstellbaren Charakterparametern; Professionalität, Geduld, Skepsis und Eigeninitiative ergänzen die bisherigen Werte.
- Optionale sinnliche oder flirtende Tonalität steht standardmäßig auf 0 und wird dann überhaupt nicht in den Modell-Prompt aufgenommen. Erst ein höherer Wert aktiviert den entsprechenden Hinweis für passende Gespräche zwischen Erwachsenen.
- Eigener Charakter-/Persönlichkeitseditor zum Anlegen, Überschreiben, Duplizieren, Importieren, Exportieren und Löschen.
- Eingebaute Presets liegen unter `resources/personalities/<rolle>/`; eigene Dateien und Überschreibungen unter `app_data/personalities/<rolle>/`.
- Die freie System-Prompt-Eingabe bleibt über die Auswahl „Benutzerdefiniert“ vollständig erhalten.


## Installation unter Windows

1. Python 3.10 oder neuer installieren, inklusive Python Launcher `py` oder Python in `PATH`.
2. `install_windows.bat` starten.
3. Der Installer prüft zuerst das Release, erstellt eine projektlokale `.venv`, bevorzugt vorhandene Offline-Wheels, installiert die Abhängigkeiten und füllt nach Möglichkeit `wheelhouse/` für spätere Offline-Installationen. Optional kann er anschließend die AVX2-unabhängige CrispASR-CPU-Laufzeit installieren.
4. Vor dem ersten Start werden Paketkonsistenz, Python-Imports, Ressourcen, Übersetzungen, Kernlogik, Ollama-API-Kompatibilität und eine unsichtbare GUI-Konstruktion geprüft. Bei einem Fehler startet die App nicht halb installiert, sondern verweist auf `app_data/logs/install_v2.15.0.log`.
5. Danach mit `run_windows.bat` starten.

Mit `build_wheelhouse.bat` lässt sich auf einem verbundenen Windows-Rechner ein vollständiger lokaler Paketcache für spätere Offline-Installationen erzeugen.

Die App versucht Ollama automatisch zu starten, wenn es unter dem üblichen lokalen Windows-Pfad gefunden wird. Andernfalls erscheint ein Dialog zur manuellen Auswahl bzw. Installation.

## Datenablage

Alle app-eigenen Daten bleiben portabel im Projektordner:

- `app_data/config.json` – aktive Konfiguration
- `app_data/config_profiles/` – gespeicherte Konfigurationsprofile
- `app_data/chats/` – Chatverläufe
- `OUTPUTS/audio/` – erzeugte Sprachausgabe und bewusst gestartete Mikrofonaufnahmen
- `OUTPUTS/code_blocks/` – extrahierte, vollständig geschlossene Codeblöcke nach Sprache/Dateityp
- `OUTPUTS/projects/zips/` – zusammengehörige, versionierte Projektarchive mit Prüfbericht
- `OUTPUTS/projects/workspaces/` – vollständige Arbeitskopien für Werkzeugläufe und manuelle Kontext-Neustarts
- `OUTPUTS/chat_exports/` – exportierte Chat-Dokumente
- `app_data/debug_logs/` – optionale Debuglogs und abgefangene Fehler
- `app_data/knowledge_base/` – lokales Langzeitgedächtnis, Imports und Retrieval-Daten
- `app_data/speech/crispasr/` – optionale CrispASR-Laufzeit, Modellcache und getrennte ASR-/TTS-Logs
- `app_data/cache/tiddlywiki_empty.html` – gecachte leere TiddlyWiki-Vorlage

## Sprach- und Auto-Answer-Struktur

UI-Texte liegen getrennt unter:

- `lang/de.json`
- `lang/en.json`
- usw.

Sprachabhängige Verhaltensdaten liegen unter:

- `resources/language_profiles/<sprache>.json`

Bearbeitbare Auto-Answer-Daten liegen getrennt nach Datentyp und Sprache:

- `app_data/auto_answer/phrases/<sprache>.json`
- `app_data/auto_answer/topic_words/<sprache>.json`
- `app_data/auto_answer/question_replies/<sprache>.json`
- `app_data/auto_answer/eliza/<sprache>.json`
- `app_data/auto_answer/guidance/<sprache>.json` – lokalisierte Zielführungs-Kataloge
- `app_data/auto_answer/guidance_overrides/<sprache>/<preset>.json` – eigene Preset-Phrasen

Die unveränderlichen Wiederherstellungswerte liegen spiegelbildlich unter `resources/auto_answer/`.

**Topic-Wörter und andere Auto-Answer-Daten werden zur Laufzeit nicht mit einer anderen Sprache gemischt.** Für mehrere `@@@`-Platzhalter in einem Satz werden nach Möglichkeit unterschiedliche Begriffe derselben Sprachdatei verwendet.

## Plugins, Recherche und physische Geräte

Alle Plugins sind nach einer Neuinstallation ausgeschaltet. Für jedes aktivierte Plugin stehen „5 Minuten fragen“, „Immer ablehnen“ und „Immer zustimmen“ zur Wahl. Drucker, 3D-Drucker und Robotik bieten zusätzlich „Immer, ohne Bestätigung (auch Aktionen)“. Bei dieser bewusst zu aktivierenden Stufe werden Druckaufträge, 3D-Druck und Bewegungsbefehle auch in Auto Answer unmittelbar ausgeführt. Erfolgt bei einer Rückfrage innerhalb von fünf Minuten keine Antwort, wird der Zugriff verweigert und das Modell erhält die Anweisung, mit einer nicht blockierenden Alternative fortzufahren.

- Internetrecherche bietet öffentliche Suche und begrenzten Seitentext-Abruf. Suchbegriffe verlassen den Rechner; lokale, private, reservierte und Link-Local-Adressen sind beim Seitenabruf gesperrt und Weiterleitungen werden erneut geprüft.
- Der Systemdrucker kann verfügbare Drucker, die Warteschlange und den Spooler-Status abfragen sowie PDF-, Text- oder Bilddateien aus der aktuellen Projekt-Arbeitskopie beziehungsweise `OUTPUTS` an den Standarddrucker übergeben.
- Die 3D-Druck-Anbindung verwendet eine konfigurierbare OctoPrint-kompatible HTTP-API. Status, Upload und Abbruch werden getrennt angeboten; fertiger G-Code ist der verlässlichste Eingabetyp, STL/3MF benötigen serverseitige Slicing-Unterstützung.
- Robotik verwendet eine bewusst einfache konfigurierbare lokale Bridge mit `GET /status`, `POST /command` und `POST /stop`. Bewegungsbefehle enthalten einen 2-Sekunden-Dead-Man-Hinweis; echte Grenzwerte, Authentifizierung, Not-Aus und Kollisionsschutz muss die konkrete Bridge beziehungsweise Gerätesteuerung erzwingen.

„Immer zustimmen (Aktionen bestätigen)“ erlaubt reine Status- und Rechercheabfragen ohne erneuten Dialog. `print_file`, `submit_3d_print` und `send_robot_command` verlangen in dieser Stufe weiterhin eine aktuelle Bestätigung mit Ziel und Parametern. Erst „Immer, ohne Bestätigung“ überspringt diese Rückfrage für das jeweils ausgewählte Geräte-Plugin. Not-Stopp und Auftragsabbruch bleiben als Stopppfade direkt erreichbar. Ist Hardware oder Bridge nicht verfügbar, erhält das Modell einen begrenzten Fehlertext und soll ohne Stillstand eine Alternative wählen.

## Sprachausgabe und Stimmprofile

Die Einstellungen enthalten getrennte Profile und Feinwerte für die Assistenten- und Benutzerstimme. Windows SAPI setzt Geschwindigkeit, Tonhöhe und Lautstärke nativ um. Bei externen VibeVoice-Laufzeiten werden fehlende Regler vorsichtig lokal auf der erzeugten WAV-Datei umgesetzt. Dadurch bleiben die Profile offline nutzbar und benötigen kein zusätzliches Audio-Paket. Wie stark ein Profil klingt, hängt weiterhin von der konkret gewählten Grundstimme ab.

Die Modelllisten sind absichtlich geschlossen und nach Aufgabe und Laufzeit getrennt:

- Python-Realtime-TTS-Wrapper: ausschließlich `microsoft/VibeVoice-Realtime-0.5B`
- CrispASR TTS: `vibevoice-tts` / Realtime 0.5B (Preset-Stimmen) oder `vibevoice-1.5b` (neutrale Stimme bzw. autorisierte WAV-Referenz außerhalb der App)
- CrispASR ASR: vollständiges mehrsprachiges `vibevoice`-Modell einschließlich Deutsch oder das kleinere `vibevoice-bitnet` nur für die in der Oberfläche genannten Sprachen

Ein ASR-Modell wird niemals an ein TTS-Backend übergeben; Realtime-Stimmpakete werden nicht mit dem strukturell inkompatiblen 1.5B-Modell kombiniert. Belegte, aber inkompatible Checkpoints erscheinen nicht als auswählbare Alternative.

Für die Spracheingabe in den Einstellungen VibeVoice ASR aktivieren, CrispASR installieren und danach im Eingabefeld auf das Mikrofon klicken. Der erste Einsatz lädt das gewählte Modell in den lokalen CrispASR-Cache; je nach Modell und Verbindung kann das deutlich länger dauern.

Der Hauptinstaller benötigt Python 3.10 oder neuer. Der aktuelle VibeVoice-Wrapper verwendet eine getrennte Python-3.13-Umgebung. Der Setup-Assistent sucht diese Version gezielt und kann sie unter Windows über `winget` einrichten.

## Auto-Answer-Mischung

In den Einstellungen werden ELIZA- und lokale-LLM-Anteil gewählt. Der Zufallsphrasen-Anteil wird automatisch als Rest berechnet.

Beispiel:

- ELIZA: 0 %
- lokale Auto-Answer-LLM: 90 %
- Zufallsphrasen: automatisch 10 %

Die normale Gesprächs-LLM und die Auto-Answer-LLM können unterschiedliche Modelle und unterschiedliche System-/Persönlichkeitsprompts verwenden.

### Optionale Gesprächs-Zielführung

„Standard / keine Zielführung“ ändert nichts am bisherigen Ablauf. Bei einem aktiven Preset bestimmt die Einflussstärke, wie häufig innerhalb des ohnehin vorhandenen Zufallssatz-Anteils eine passende Zielphrase verwendet wird. Der Quellenmix selbst bleibt unverändert. Unabhängig davon kann dasselbe Ziel als verborgene Arbeitsanweisung an die Auto-Answer-LLM gegeben werden. Beide Wege lassen sich einzeln ausschalten.

Die 25 Presets decken Programmierung, fortgeschrittene GUI-Arbeit, iterativen Programmaufbau mit Funktionstests, Fehlersuche, Architektur/Refactoring, KI-Weiterentwicklung, lokale KI-Optimierung, Projektabschluss, Recherche, Lernen, kritische Prüfung, Entscheidungen, psychologische Selbstreflexion ohne Diagnosen, Gesprächsbelebung, Motivation, transparente Partnersimulation, Fantasie, kreatives Schreiben, Science-Fiction-Weltenbau, Spielentwicklung, visuelle Bedienbarkeit, Systemverwaltung, Datenschutz/Sicherheit, Philosophie/Ethik/Zukunft und spielerische Experimente ab.

Direkte Fragen werden weiterhin bevorzugt beantwortet. Die Zielführung verändert ausschließlich automatisch erzeugte Auto-Answer-Benutzernachrichten, niemals manuell eingegebenen Text. Kataloge und eigene Phrasen bleiben strikt nach Oberflächensprache getrennt.

## Hardware und Kontext

Die Automatik prüft vor jeder Modellanfrage das geladene Modell (`/api/ps`), seine Metadaten (`/api/show`) sowie bei lokalen Endpunkten verfügbare RAM-/NVIDIA-VRAM-Reserven. Die Prüfung läuft außerhalb der Oberfläche. Assistent und Auto-Answer-Modell erhalten getrennte Entscheidungen und Fehlergrenzen.

Neue Standardwerte:

| Einstellung | Standard | Wirkung |
|---|---:|---|
| Nachrichtenlimit | 0 / automatisch | Kein Abschneiden nach acht Nachrichten; Wechsel anhand des Tokenbudgets |
| Übernommene Nachrichten | 0 / automatisch | Vollständige letzte Dialogeinträge passend zum Budget |
| Automatische Kontextwahl | an | Konservativer Start meist 4.096 Token; Wachstum nur bei Bedarf und belastbaren Messdaten |
| Kontextobergrenze | 32.768 Token | Obergrenze, keine sofortige Speicherreservierung; Modellgrenze gilt zusätzlich |
| Maximale Antwort | 65.536 Token | Manuell bis 1.000.000; tatsächlich auf den freien Tokenrahmen begrenzt |
| Kurze Antworten erzwingen | aus | Neue Diskussionen dürfen ausführlicher sein |
| Auto-Answer-LLM-Ausgabe | 512 Token | Mehr Platz für sinnvolle Nachfragen; weiterhin einstellbar |
| Autonomer Auto-Answer-Neustart | aus | Kein selbstständiger Chatwechsel ohne bewusste Aktivierung |
| Dialogprüfung | 78 % | Ab hier darf die Auto-Answer-LLM Zielbezug und Kohärenz anhand des sichtbaren Dialogs bewerten |
| Sicherheitsneustart | 92 % | Kontrollierter Wechsel vor einer nahezu gefüllten nächsten Anfrage |
| Stimmhöhe Assistent | 0 | Neutrale Ausgangseinstellung |

Die kleine Nachrichtenanzahl löst standardmäßig keinen Wechsel mehr aus. 12 % des Kontextfensters bleiben als Schätzreserve frei; zusätzlich wird Platz für die nächste Antwort eingeplant. Wachstum erfolgt in begrenzten Schritten. Als RAM-Reserve gelten mindestens 2 GiB bzw. 15 %, bei NVIDIA-VRAM mindestens 1 GiB bzw. 12 % plus Laufzeitpuffer. Das sind konservative Heuristiken, keine exakte Speicherprognose. Bei kritischer Reserve pausiert die Anfrage und erhält die Eingabe.

Ohne verwertbare Modell-/Speicherdaten, bei unbekannten KV-Architekturen oder unklarer Mehr-GPU-Verteilung wird nicht spekulativ vergrößert. Die native Kontextgrenze gilt unabhängig von der Automatik. Bei entfernten Servern werden lokale RAM-/VRAM-Werte nicht verwendet; eine manuelle Größe bleibt möglich. Ein localhost-Endpunkt wird als lokaler Server behandelt (bei SSH-Tunneln Automatik entsprechend vorsichtig verwenden). Andere Serverclients, parallele Ollama-Anfragen, dynamische Last und Modellgewichte können dennoch OOM auslösen. Eine absolute OOM-Garantie gibt es nicht.

Ein neuer Chat spart nicht automatisch Ollamas KV-Speicher: Bei erkanntem Kontext-/Speicherfehler wird daher einmal mit halbiertem `num_ctx` versucht; nötigenfalls entsteht dabei ein Folge-Chat. Die reduzierte Obergrenze bleibt für dieses Modell und diesen Server bis zum App-Neustart aktiv. Bereits teilweise ausgegebene Antworten werden nicht automatisch doppelt generiert. Zu große einzelne Eingaben/Systemprompts werden klar gemeldet und bleiben ungekürzt gespeichert.

Beim Wechsel übernimmt die App einen nach Budget bemessenen aktuellen Dialogausschnitt und eine begrenzte Übergabe älterer Textauszüge mit Quelle, Zeitpunkt und Rolle. Das ursprüngliche menschliche Ziel wird bevorzugt erhalten. Diese Übergabe ist verlustbehaftet und ausdrücklich keine Faktenprüfung oder vollständige semantische Zusammenfassung; die Originalabschnitte bleiben vollständig im Verlauf verfügbar. Sie funktioniert unabhängig vom optionalen Langzeitgedächtnis.

Der Zähler rechts neben Auto Answer summiert pro Chatabschnitt die von Ollama gemeldeten Prompt- und Ausgabetokens aller normalen sowie separaten Auto-Answer-Modellanfragen. Fehlen native Statistiken oder wird ein älterer Chat erstmals geladen, rekonstruiert die App konservative Werte und kennzeichnet sie mit `≈`. „Kontext neu starten“ setzt nicht bloß eine Zahl zurück: Die App legt einen echten neuen Folgechat an und übernimmt nur vollständige, prüfbare Einheiten. Sehr große Dialogrunden werden nach dem aktuellen Kontextbudget reduziert; Projektdateien werden niemals mitten im Code abgeschnitten, sondern vollständig in eine neue Arbeitskopie übernommen und im Chat nur soweit vollständig darstellbar eingebettet.

Der optionale autonome Neustart verwendet nicht den kumulierten Tokenzähler, sondern die geschätzte Belegung der nächsten Anfrage. Ab der Prüfgrenze beurteilt die ausgewählte Auto-Answer-LLM ausschließlich den sichtbaren Dialog und darf nur mit dem exakten Steuerwort `RESTART` einen Wechsel auslösen; Erklärungen oder uneindeutige Antworten gelten als „behalten“. Mindestens zwei abgeschlossene Assistentenrunden sind erforderlich. An der höheren Sicherheitsgrenze erfolgt der kontrollierte Wechsel direkt. Danach läuft Auto Answer im neuen Abschnitt weiter; der alte Abschnitt bleibt auswählbar und unverändert.

Abschnittstitel werden nach Beiträgen anhand der jüngsten Inhalte aktualisiert: Grundthema, aktueller Schwerpunkt und Abschnittsnummer. Die Benennung ist eine lokale Schlüsselwortheuristik ohne zusätzliche Modelllast. Doppelklick auf einen Chat zeigt den Titelverlauf mit Nachrichtenpositionen, Übergabeauszüge und Kontextdiagnose; von dort lässt sich der direkte Vorgänger öffnen. Die Archivliste lädt unveränderte Dateien nicht bei jeder Antwort neu.

Technische Grundlagen: [Ollama-Kontextgröße](https://docs.ollama.com/context-length), [laufende Modelle](https://docs.ollama.com/api/ps), [Modellmetadaten](https://docs.ollama.com/api-reference/show-model-details), [Chat-Statistiken](https://docs.ollama.com/api/chat), [Speicher und Parallelität](https://docs.ollama.com/faq).

## Update und eigener Release-Build

1. Anwendung schließen und den bisherigen Ordner sichern.
2. Das ZIP in einen neuen Ordner entpacken. Für ein Update kann der Inhalt seines Projektordners über den bisherigen Projektordner kopiert werden: Das ZIP enthält bewusst keinen `app_data`-Ordner und überschreibt deshalb keine Chats, Einstellungen oder Stimmen.
3. `install_windows.bat` ausführen. Vorhandene funktionsfähige Abhängigkeiten werden wiederverwendet; sonst wird zuerst ein vorhandenes Wheelhouse versucht. Eine verschobene `.venv` neu erstellen, keine fremde virtuelle Umgebung hineinkopieren.
4. Bei alten automatischen Standardprofilen werden die früheren Werte acht Nachrichten/fünf übernommene Einträge auf Automatik migriert. Abweichende benutzerdefinierte Werte bleiben erhalten. Bereits gespeicherte Einstellungen für kurze Antworten, Tokenlimits und Stimmen bleiben bestehen; für die neuen Kontext-/Diskussionswerte in den Optionen „Adaptive Diskussionswerte übernehmen“ anklicken und speichern. Die Stimmen bleiben dabei unverändert.

`build_release.bat` startet die vollständige Prüfung und erzeugt ein reproduzierbares Quell-ZIP samt SHA-256-Datei unter `release/`. Unter anderen Plattformen: `python tools/build_release.py`. Die Anwendung braucht keinen C/C++-Compiler. `build_wheelhouse.bat` lädt passende Binärpakete für das ausführende Windows/Python; fehlende Binärpakete lösen keine unkontrollierte Quellkompilierung aus. Dies ist kein EXE-Compiler.

## Reasoning / Thinking

Unter Einstellungen lässt sich ein Standard festlegen und für jedes erkannte Ollama-Modell separat überschreiben:

- Aus
- Automatisch bei Code: Medium nur für erkannte Code-Anfragen
- Low
- Medium
- High

Die Einstellung gilt sowohl im normalen Chat als auch dann, wenn dasselbe Modell die simulierte Benutzerrolle im Auto-Answer-Modus übernimmt. Ollama erhält den Wert über das native `think`-Feld. Bei älteren Ollama-Versionen wird kontrolliert auf boolesches Thinking und nötigenfalls auf einen Request ohne `think` zurückgefallen. Nicht jedes Modell unterstützt Reasoning; GPT-OSS kann seine Reasoning-Spur modellbedingt nicht vollständig abschalten.

## Langzeitgedächtnis / lokale Wissensquelle

Das Langzeitgedächtnis verwendet einen eigenen lokalen Index für selektives Retrieval. TiddlyWiki dient als sichtbare, menschenlesbare Wissensablage – nicht als alleinige Suchmaschine.

- beim Aktivieren wird automatisch `app_data/knowledge_base/tiddlywiki/` verknüpft, sofern noch keine eigene Quelle gewählt ist
- der Installer cached eine geprüfte leere Wiki unter `app_data/cache/tiddlywiki_empty.html`; ist kein Netz verfügbar, bleibt die App nutzbar und ein erneuter Installerlauf kann die Vorlage später nachholen
- `brain.html` enthält die von der App verwalteten Einträge direkt und kann ohne Node.js lokal geöffnet werden; die `.tid`-Spiegeldateien bleiben für Werkzeuge erhalten
- manuelle Dateien können für die nächste Anfrage als Kontext angehängt werden
- Textinhalte werden lokal ausgelesen; Medien werden als Referenzen gespeichert
- relevante frühere Chat-Erinnerungen werden nur bei passenden aktuellen Begriffen abgerufen
- die abgerufenen Erinnerungen werden als Hintergrundkontext, nicht als neue Benutzeranweisung, an die LLM weitergegeben
- Auto Answer sieht ausschließlich den sichtbaren Gesprächsinhalt; versteckte Wissensabrufe, Werkzeugdaten und interne Übergaben werden nicht als simulierte Benutzerkenntnis weitergegeben

## Themes

Themes sind eigenständige Dateien unter `themes/*.json`. Eigene Themes können ergänzt werden, ohne `main.py` zu verändern.

## Wartung und Prüfungen

- `python tests/smoke_core.py` – Kernlogik und Datendateien
- `python tools/check_translations.py` – Schlüsselgleichheit aller UI-Sprachdateien
- `python tools/verify_installation.py --source-only` – Release-Struktur, Syntax und Ressourcen
- `python tools/verify_installation.py` – vollständige Installations- und GUI-Prüfung
- Chat-/Konfigurationsdateien werden möglichst atomar geschrieben; beschädigte Dateien werden gesichert statt still überschrieben.

## Hinweise

- Neue Anfragen verwenden nach Möglichkeit Ollamas native Tokenstatistiken. `≈` kennzeichnet rekonstruierte Altwerte oder Schätzungen; die Kontextbelegung bleibt modellbedingt eine Sicherheitsnäherung.
- Binäre Medien werden nur dann inhaltlich verstanden, wenn das gewählte Modell und der verwendete Ollama-Endpunkt diese Modalität unterstützen. Andernfalls bleiben sie als lokale Referenz und Metadaten verfügbar.
- Der erste VibeVoice- oder CrispASR-Start lädt die ausgewählten lokalen Modell-/Stimmdateien und kann deshalb länger dauern.

## Short English overview

OllamaVibeDesk v2.15.0 is an offline-first PyQt6 GUI for local Ollama models. Its printer, 3D-printer and robotics plugins now offer an explicit Always, without confirmation choice for unattended physical actions; the existing Always allow mode permits status reads while still confirming print and motion commands. Printer queue and spooler status are available as read-only tools. The release also retains 35 built-in personalities per role, visible streaming code, language-aware responses, persistent token counters, context restart, central portable `OUTPUTS`, project ZIP validation, per-model reasoning, topic-aware follow-ups, adaptive context sizing, VibeVoice ASR/TTS and local TiddlyWiki memory.

## Source

https://github.com/zeittresor/OllamaVibeDesk/
