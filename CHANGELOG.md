# 2.16.1 — 2026-09-26

- Der animierte Status im unteren Bereich lässt sich bis auf das Symbol verkleinern. Der vollständige Text bleibt im Tooltip. So begrenzt er unter Windows nicht mehr den horizontalen Seitenleisten-Schieberegler.
- Die Windows-Installationsprüfung verwendet beim Qt-Offscreen-Test den Systemschriftordner statt eines nicht vorhandenen Fontverzeichnisses aus dem Qt-Paket.
- Der Installer zeigt die acht Schritte als Fortschrittsbalken, markiert den erfolgreichen Abschluss klarer und zeigt bei einem GUI-Prüffehler die letzten Protokollzeilen direkt an.
- GUI-Tests wurden auch mit erhöhter Oberflächenskalierung durchgeführt.

# 2.16.0 — 2026-09-26

- Auto Answer setzt eine abgeschlossene Unterhaltung fort, wenn die Option nach einer Pause wieder eingeschaltet wird. Die konfigurierbare Rundenbegrenzung bleibt erhalten.
- Ein ausbleibendes Audio-Abschlussereignis blockiert eine bereits vorbereitete Runde nicht mehr, sofern keine Wiedergabe läuft.
- Ein kleines animiertes Statussymbol links neben „Ausgaben öffnen“ zeigt Modellvorbereitung, Warten auf Tokens, Reasoning, Textausgabe, Werkzeugaufrufe, Sprachausgabe, Folge-Runden und konkrete Pausengründe. Ohne neue Modell-Daten zeigt es die verstrichene Zeit an.
- GUI-Regressionen testen die Wiederaufnahme und den Audio-Übergang.

# 2.15.0 — 2026-09-26

- Drucker, 3D-Drucker und Robotik erhalten je Plugin die zusätzliche, explizit zu aktivierende Berechtigung „Immer, ohne Bestätigung (auch Aktionen)“. Damit werden Druck-, 3D-Druck- und Bewegungsbefehle in Auto Answer ohne blockierenden Dialog ausgeführt.
- Das bisherige „Immer zustimmen“ heißt bei diesen drei Geräten nun „Immer zustimmen (Aktionen bestätigen)“: Statusabfragen bleiben direkt, Befehle mit physischer Wirkung fragen weiterhin. Alle Plugins bleiben bei einer Neuinstallation ausgeschaltet und im aktiven Zustand standardmäßig auf „5 Minuten fragen“.
- Das Drucker-Plugin bietet eine neue reine Leseabfrage für Druckwarteschlange und Spooler-Status. Not-Stopp und Auftragsabbruch bleiben als direkte Stopppfade erhalten.
- Berechtigungsnormalisierung, Speicherung, zwölf Sprachdateien und GUI-/Worker-Regressionen wurden um die neue Auswahl erweitert.

# 2.14.0 — 2026-09-26

- Die integrierten Einstellungen haben zwischen den zehn Kategorien zusätzlichen Platz vor und nach jeder Trennlinie. Die linke Navigation richtet die gewählte Überschrift weiter am oberen Rand aus.
- Für Assistent und simulierten Benutzer kommen jeweils 15 unterschiedliche, deutsch und englisch beschriebene Persönlichkeits-Presets hinzu. Es stehen jetzt 35 pro Rolle zur Wahl.
- Der Charaktereditor ergänzt Professionalität, Geduld, Skepsis und Eigeninitiative sowie eine optionale sinnliche beziehungsweise flirtende Tonalität. Werte werden in eigene Presets und Überschreibungen übernommen; alte Dateien behalten kompatible Standardwerte.
- Bei optionaler Tonalität von 0 fehlen deren Begriff und zugehörige Anweisung vollständig im Modell-Prompt; Werte über 0 werden nur für passende Gespräche zwischen Erwachsenen beschrieben.
- Übersetzungen für zwölf Oberflächensprachen, Installationsprüfung und GUI-/Kern-Regression wurden angepasst.

# 2.13.0 — 2026-09-25

- Streaming-Antworten aktualisieren die sichtbare Nachricht während der laufenden Generierung als stabilen Text, statt bei jedem Token den gesamten Markdown-Baum neu aufzubauen. Dadurch bleiben auch lange und noch nicht geschlossene Codeblöcke sichtbar; das bisherige Aufblitzen einzelner Zeilen entfällt.
- Bei expliziten Programmieraufgaben übernimmt die App vollständige, vom Modell versehentlich ausschließlich im Reasoning ausgegebene Codeblöcke in die sichtbare Antwort. Die Übernahme wird gekennzeichnet, bleibt exportierbar und wird nicht vorgelesen.
- Die Antwortsprache wird aus den echten Benutzereingaben des aktuellen Gesprächs ermittelt. Code, URLs, Assistentenantworten und automatisch erzeugte Auto-Answer-Nachrichten beeinflussen diese Erkennung nicht; bei Gleichstand gewinnt die jüngste klare Benutzersprache.
- Übersetzungen, GUI-Kontinuitätstest, Streaming-Code-Test und Installationsprüfung wurden erweitert.

# 2.12.0 — 2026-09-25

- Auto Answer kann optional bei hoher aktueller Kontextbelegung einen kontrollierten Folgechat anlegen. Die Funktion ist standardmäßig deaktiviert; Prüf- und Sicherheitsgrenze liegen bei 78 % beziehungsweise 92 % des sicheren Promptbudgets.
- Die Modellprüfung sieht ausschließlich den sichtbaren Dialog, startet erst nach mindestens zwei abgeschlossenen Assistentenrunden und akzeptiert nur ein exaktes `RESTART`. Lange, aber weiterhin kohärente Gespräche sowie uneindeutige Ausgaben bleiben im vorhandenen Abschnitt.
- Der autonome Neustart nutzt denselben geprüften Übergabepfad wie der manuelle Neustart: ursprüngliche Aufgabe, bis zu drei vollständige jüngste Runden und vollständiger Projektstand werden in einen separat auswählbaren Folgechat übernommen; der Quellchat bleibt unverändert. Auto Answer setzt anschließend im neuen Abschnitt fort.
- Neue standardmäßig deaktivierte Internetwerkzeuge erlauben öffentliche Websuche und begrenzten Seitentext-Abruf. Lokale/private/reservierte Zieladressen und entsprechende Weiterleitungen werden blockiert; fehlgeschlagene Recherche blockiert das Gespräch nicht.
- Neue Druckerwerkzeuge listen Systemdrucker auf und übergeben freigegebene PDF-, Text- oder Bilddateien aus Projekt-Arbeitskopie beziehungsweise `OUTPUTS` an die Betriebssystem-Druckwarteschlange.
- Neue OctoPrint-kompatible 3D-Druckwerkzeuge unterstützen Status, Upload/Start und Abbruch. URL und API-Schlüssel sind im Plugin-Bereich konfigurierbar.
- Neue Robotikwerkzeuge unterstützen Status, begrenzte JSON-Aktionen und Not-Stopp über eine konfigurierbare lokale Bridge für Roboter, Arme, Drohnen oder RC-Fahrzeuge. Bewegungsbefehle enthalten einen Dead-Man-Hinweis; gerätespezifische Grenzen verbleiben bei der Bridge.
- Druck-, 3D-Druck- und Bewegungsaktionen verlangen unabhängig von „Immer zustimmen“ jedes Mal eine aktuelle Bestätigung. Nach fünf Minuten ohne Antwort wird verweigert und das Modell zur nicht blockierenden Alternative aufgefordert.
- Der Plugin-Bereich ist für Full-HD und kleinere Fenster scrollbar. Konfiguration, Übersetzungen, Installerprüfung und Regressionstests decken die neuen Werkzeuge, Berechtigungen und autonomen Kontextwechsel ab.

# 2.11.0 — 2026-09-25

- Der Hauptbereich zeigt pro Chatabschnitt einen persistenten Zähler für kumulierte Eingabe- und Ausgabetokens sowie eine Schätzung der aktuell belegten Kontextgröße. Native Ollama-Statistiken werden bevorzugt; rekonstruierte Altwerte und Fallback-Schätzungen sind mit `≈` gekennzeichnet.
- Auch Anfragen der separaten Auto-Answer-LLM fließen in den sichtbaren Zähler ein. Werte bleiben nach Chatwechsel und Neustart erhalten.
- „Kontext neu starten“ legt einen echten, separat auswählbaren Folgechat an und setzt dessen Zähler auf null. Die ursprüngliche Benutzeraufgabe, bis zu drei vollständige letzte Dialogrunden und der aktuelle Projektstand werden kontrolliert übernommen; der alte Chat wird nicht verändert.
- Die Dialogübergabe passt sich an das verfügbare Kontextbudget an. Projektcode wird nicht zeichenweise abgeschnitten: Das neueste passende Projekt-ZIP wird sicher entpackt, alternativ wird die letzte Arbeitskopie vollständig übernommen; nur vollständige Textdateien werden zusätzlich in den Chatkontext eingebettet.
- Der wiederhergestellte Projektstand liegt unter `OUTPUTS/projects/workspaces/<neue Chat-ID>/` und enthält Dateiliste sowie vorhandenen statischen Prüfstatus. Archivpfade werden weiterhin gegen Verzeichnisausbruch geprüft.
- Ein geplanter Auto-Answer-Timer wird während der Bestätigungsabfrage pausiert und bei Abbruch mit seiner Restzeit fortgeführt. Ausstehende Sprach-/Auto-Submit-Zustände sperren den Neustart, sodass kein Quellchat im Hintergrund wechselt.
- Persistenz-, Archiv-, Token-, Full-HD-Layout-, Timer- und GUI-Regressionsprüfungen wurden erweitert.

# 2.10.1 — 2026-09-25

- Sämtliche bewusst erzeugten Benutzerdateien liegen nun im zentralen portablen Ordner `OUTPUTS`: einzelne Codeblöcke, Projekt-ZIPs und Werkzeug-Arbeitsbereiche, TTS-/Mikrofon-Audio sowie Chat-Exporte besitzen klar getrennte Unterordner. Interne Chats, Konfiguration und Wissensdaten verbleiben in `app_data`.
- Ein automatisch angelegtes `OUTPUTS/README.txt` erklärt die Verzeichnisstruktur. Vorhandene Ausgaben älterer Versionen werden aus Sicherheitsgründen weder verschoben noch gelöscht.
- Sehr lange Reasoning-/Thinking-Spuren werden ausschließlich in ihrer sichtbaren Vorschau begrenzt, damit die eigentliche Antwort und insbesondere Code weiterhin vollständig erreichbar bleiben. Die allgemeine sichtbare Antwortgrenze wurde zusätzlich deutlich erhöht.
- Bleibt eine Antwort trotz Fortsetzungsversuchen unvollständig, exportiert die App nun bereits vollständig geschlossene Codeblöcke und fertig geschriebene Werkzeugdateien als ausdrücklich gekennzeichneten, prüfpflichtigen Teilstand. Der offene letzte Codeblock wird weiterhin nicht als fertige Datei übernommen.
- Bei Programmieraufgaben wird nur ein begrenzter, relevantester Ausschnitt der lokalen Wissensquelle in den Prompt eingesetzt. TiddlyWiki und Langzeitgedächtnis bleiben vollständig erhalten, beanspruchen aber weniger von dem für Code benötigten Kontext.
- Auto Answer erhält ausschließlich den normalen sichtbaren Gesprächsinhalt. Interne Übergabeerinnerungen, Wissensabrufe, Werkzeugdaten und Reasoning werden nicht mehr verdeckt in den simulierten Benutzer-Prompt übernommen.
- Reine Datei-/Statusfragmente wie `index.html 1 2000` gelten nicht mehr als fertige Modellantwort: Die App fordert einmal gezielt die vollständige sichtbare Antwort nach. Bleibt die Ausgabe unbrauchbar, pausiert Auto Answer nachvollziehbar, statt auf unsichtbaren oder erfundenen Kontext zu reagieren.
- Installer, Starter, Übersetzungen, statische Release-Prüfung und Regressionstests wurden an die neue Ausgabeablage und Teilstand-Sicherheitslogik angepasst.

# 2.10.0 — 2026-09-25

- Projekt-ZIPs erkennen Dateitypen jetzt zusätzlich am tatsächlichen Inhalt. Eindeutige Signaturen werden unter anderem für Godot-Szenen/-Ressourcen, GDScript, Python, HTML, CSS, JavaScript, JSON, XML, Shader, C#, Go, Rust, PowerShell, Batch und Shell ausgewertet.
- Falsch bezeichnete Dateien wie `Main.tscn.txt`, `rotate.txt` oder `config.txt` erhalten nur bei starker inhaltlicher Evidenz die passende Endung. Echte Textdateien wie `requirements.txt` bleiben unverändert.
- Godot-Ausgaben mit vorhandener Szene, aber fehlender `project.godot`, erhalten eine minimale Startkonfiguration mit der erkannten Hauptszene. Diese Ergänzung wird transparent im Manifest ausgewiesen; Modellcode selbst wird nicht umgeschrieben.
- Jedes Projekt-ZIP enthält nun `_archive/PROJECT_CHECK.md` und `_archive/project_check.json` mit erkannter Projektart, Einstiegspunkten, Dateinamensableitungen, erzeugten Metadaten sowie Fehlern und Warnungen.
- Statische Prüfungen umfassen Python-, JSON-, TOML- und XML-Syntax, Godot-Dateiköpfe, Hauptszene, fehlende `res://`-Ressourcen und typische Einstiegspunkte für Python, Web, JavaScript/TypeScript und .NET.
- Der Prüfstatus unterscheidet `structure_complete`, `needs_review` und `invalid`. Er behauptet ausdrücklich keinen erfolgreichen Programmlauf, solange das erzeugte Projekt nicht wirklich ausgeführt wurde.
- Die Projekt-/Plugin-Regressionstests wurden um namenlose Codeblöcke, falsch angehängte `.txt`-Endungen, Godot-Vervollständigung, Syntaxfehler und fehlende Ressourcen erweitert.

# 2.9.2 — 2026-09-25

- Die linke Kategorienavigation der integrierten Einstellungen richtet den gewählten Abschnitt nun exakt am oberen Rand des rechten Bereichs aus, statt ihn lediglich irgendwo sichtbar zu machen.
- Alle zehn Einstellungsbereiche besitzen eine gut sichtbare, kursive Überschrift und eine abschließende Trennlinie; auch Stimmgestaltung und Modell-/Kontextoptionen beginnen an der richtigen Abschnittsgrenze.
- Der letzte Abschnitt erhält dynamischen Scrollraum und kann deshalb ebenso wie mittlere Abschnitte oben ausgerichtet werden. Ein erneuter Klick auf die bereits gewählte Kategorie richtet sie erneut aus.
- Der Offscreen-GUI-Test kontrolliert Überschriften, Trennlinien, alle Randfälle der Abschnittsnavigation und die vorhandene Zurück-Navigation.

# 2.9.1 — 2026-09-25

- Auto-Answer wartet bei schnell beendeter Sprachausgabe auf das Aufräumen der laufenden Modellanfrage; die nächste Runde geht nicht mehr durch eine zeitliche Überschneidung verloren.
- Leere Auto-Answer-LLM-Ausgaben und Kontextfehler verwenden eine lokale Gesprächsphrase; ausbleibende TTS-Ausgaben blockieren automatische Runden nicht. Automatische TTS-Fehler zeigen keinen unbeaufsichtigten Bestätigungsdialog mehr.
- Modellantworten, die mit `done_reason=length` mitten in einem Satz oder Codeblock enden, werden in begrenzten Schritten ergänzt. Fortgesetzte Antworten werden vor Code- und ZIP-Export zusammengeführt.
- Wenn die Antwort nach den Fortsetzungsversuchen unvollständig bleibt, kennzeichnet die App dies sichtbar und erstellt aus dem abgeschnittenen Code keine Datei und kein Projekt-ZIP.
- Die 12 Sprachdateien, Regressionstests und der GUI-Testserver umfassen die neuen Abbruch- und Wiederaufnahmepfade.

# 2.9.0 — 2026-09-24

- Einstellungen sind jetzt als integrierter Hauptfenster-Bereich mit klarer Zurück-Navigation und linker Bereichsauswahl umgesetzt; die bisherigen direkten `QDialog`-Aufrufe bleiben für Kompatibilität und Tests verfügbar.
- Einstellungen wurden in visuell getrennte Abschnitte für Allgemeines, Sprachausgabe/-eingabe, Auto-Answer, Modelle/Kontext, Persönlichkeit, Wissen und Profile gegliedert.
- Optionale lokale Audio-Postproduktion ergänzt: Chorus, Echo, Vocoder/Robotik und Raum/Hall werden mit Schiebereglern gesteuert, sind standardmäßig deaktiviert und erzeugen neben dem unveränderten Original eine separate Datei mit `_postproduction.wav`.
- Postproduktion ist fehlertolerant: Bei unlesbaren oder nicht unterstützten WAV-Dateien bleibt die normale Ausgabe verfügbar; temporäre Dateien werden atomar ersetzt und nicht zurückgelassen.
- Konfiguration, Übersetzungen, Persistenz, Offscreen-GUI und Audio-Regressionsprüfungen erweitert; der Installer prüft weiterhin die vollständige Anwendung vor dem ersten Start.

# 2.8.1 — 2026-09-24

- Das Hauptfenster startet regulär maximiert; die bisherige bildschirmabhängige Full-HD-/UHD-Größe bleibt als passende Wiederherstellungsgröße erhalten.
- Der Rückkehrbutton im Plugin-Bereich heißt nun eindeutig „Zurück zum Hauptbereich“ und besitzt zusätzlich einen Richtungspfeil, Tooltip und barrierefreien Namen.
- Die neue Rückkehrbeschriftung ist in allen 12 Oberflächensprachen lokalisiert und wird bei einem Sprachwechsel aktualisiert.
- GUI-Regressionstest für maximierten Startzustand, Rückkehrbeschriftung und Plugin-Navigation ergänzt.

# 2.8.0 — 2026-09-24

- Optionale Gesprächs-Zielführung mit 25 Presets, unter anderem Programmieraufgaben, fortgeschrittene GUI-Entwicklung, iterativer Programmaufbau mit Tests, KI-Weiterentwicklung, Fehlersuche, psychologische Selbstreflexion ohne Diagnosen, Motivation, transparente Partnersimulation, Fantasie, Spielentwicklung, Datenschutz und spielerische Experimente.
- „Standard / keine Zielführung“ bewahrt das bisherige Auto-Answer-Verhalten exakt; die vorhandene ELIZA-/LLM-/Zufallssatz-Mischung bleibt weiterhin zusammen 100 %.
- Einflussstärke von 0 bis 100 Prozent sowie getrennte Schalter für Zufallssatz-Anteil und Auto-Answer-LLM.
- Sprachgetrennte Kataloge für alle 12 unterstützten Sprachen mit mindestens acht Einflussphrasen pro Preset; eigene Preset-Phrasen lassen sich bearbeiten und einzeln zurücksetzen.
- Echte Fragen behalten Vorrang vor Zielphrasen; manuell geschriebene Benutzernachrichten werden nie verändert.
- Zielführungs-Auswahl, Stärke und Zielschalter werden in Konfigurationen und Profilen gespeichert und beim erneuten Öffnen wiederhergestellt.
- Neue Katalog-, Prioritäts-, Konfigurations-, Editor- und GUI-Regressionstests; vollständige Installationsprüfung weiterhin Bestandteil des Release-Builds.

# 2.7.0 — 2026-09-24

- Aktivieren des Langzeitgedächtnisses legt bei fehlender Verknüpfung automatisch die portable Standard-Wissensquelle an; das gilt auch nach Neustarts und beim erneuten Öffnen der Einstellungen.
- Eine vorhandene, validierte TiddlyWiki-Vorlage wird ohne manuelles Kopieren als `brain.html` bereitgestellt; ältere App-Platzhalter werden automatisch repariert.
- App-eigene Wissenseinträge werden zusätzlich zu den `.tid`-Dateien direkt und skriptsicher in die eigenständige `brain.html` gespiegelt, sodass sie beim lokalen Öffnen sichtbar sind.
- Wiki-Download im Installer ist atomar, größenbegrenzt und inhaltlich validiert; beschädigte oder unvollständige Downloads ersetzen keinen gültigen Cache.
- Begrenzte Textlesevorgänge und Windows-sichere Namen für importierte Wissensdateien vermeiden unnötigen Speicherverbrauch und problematische Pfadlängen.
- Unbenutzte Imports, doppelte Daten und veraltete Release-Dokumentation entfernt; historische Testberichte werden nicht mehr in das Auslieferungs-ZIP gepackt.
- Neue Wiki-/Cache-/Pfadlängen-Regressionstests; vollständige Installer-, Kern-, API- und Offscreen-GUI-Prüfung bleibt Bestandteil des Release-Builds.

# 2.6.6 — 2026-09-23

- Projektarchive erkennen formatierte und in Codeblöcken ausgegebene `File: ...`-Markierungen zuverlässig.
- Godot GDScript-, Szenen- und Shader-Code erhält automatisch `.gd`, `.tscn` bzw. `.gdshader`.
- Regressionstest für den konkreten mehrteiligen Godot-Dialog ergänzt.

# 2.6.5 — 2026-09-23

- Reine Denktext-Ausgaben erhalten genau einen Versuch auf eine abschließende Antwort ohne Reasoning; Hinweise werden weder vorgelesen noch in Auto Answer weitergereicht.
- Lange Codeblöcke lassen sich weitgehend über die äußere Chat-Bildlaufleiste vollständig lesen.
- Aussagekräftigere Projekttitel, klare Pfeile und weniger redundante Themenmarker links; vorhandene kurze Wurzeltitel werden beim nächsten Update verbessert.
- Offscreen-GUI-Regressionsprüfungen für fehlende Endantworten und lange Codeantworten.

# 2.6.4 — 2026-09-23

- Gewähltes Modell in der modellspezifischen Reasoning-Einstellung wird beim Speichern, erneuten Öffnen und bei Profilimport wiederhergestellt.
- Kompatibilitätshinweis als Tooltip an den Feldern statt als langer Text unter der Auswahl; konkrete Modellnennung entfernt.
- GUI-Test mit realem Konfigurationsschreiben und erneutem Laden gegen ein isoliertes Testprofil.

# 2.6.3 — 2026-09-23

- Bevorzugtes Ollama-Modell Q3_K_M und Auto-Answer-Mischung 15/50/35 für neue Installationen; bestehende Einstellungen bleiben erhalten.
- Antwort-Tokens standardmäßig 65.536; Slider reicht manuell bis 1.000.000, begrenzt durch das verfügbare Kontextbudget.
- Windows-Installer fragt nur bei erreichbarem lokalen Ollama und fehlendem Modell mit 10 Sekunden Zeitlimit und Nein als Standard nach dem optionalen Download.
- Lokaler Fake-Ollama-Regressionstest prüft Modellprüfung, Download, erneute Installation und Ablehnung externer Server.

# 2.6.2 — 2026-09-23

- Chatleiste lässt sich deutlich weiter mit der Maus vergrößern; Kopfbereich und Statuszeile geben dafür Breite frei.
- Plugins öffnen über eine Schaltfläche neben Einstellungen; die Tab-Leiste über dem Chat entfällt.
- Auto-Answer verwendet die Farben des gewählten Themes und zeigt keinen ELIZA-Zusatz mehr.
- Startgröße richtet sich nach der verfügbaren Bildschirmfläche: Full HD als Ausgangspunkt, kleinere Displays passend begrenzt und UHD bis 2560 × 1440 startend.

# 2.6.1 — 2026-09-23

- Windows-Installationsabbruch in der Standort-Fallback-Regression korrigiert: Eine konfigurierte Windows-Region darf vorhanden sein.
- Windows-Regionspfad mit nachgebildeter OS-Region unabhängig vom Prüfhost getestet.
- Layout-Prüfung vom Betriebssystem-/Schriftgrößen-abhängigen Pixelwert entkoppelt.

# 2.6.0 — 2026-09-23

- Modellwerkzeuge für Systemwerte und Geräteposition mit klar markiertem Offline-Regionsfallback.
- Pro Plugin freies Wählen zwischen zeitlich begrenzter Rückfrage, Ablehnung und dauerhafter Freigabe; Defaults bleiben Rückfrage und deaktiviert.
- Modellgesteuerte Webcam-Einzelaufnahme bei aktivierten Webcam-/Vision-Plugins; Geräteberechtigungen für Kamera, Mikrofon und Standort werden geprüft.
- Keine frei erfundenen Koordinaten und kein IP-Standortdienst; fehlende Sensoren werden angezeigt.
- Modell-Dropdown wächst auf breiten Fenstern und zeigt lange Modellnamen als Tooltip.
- Zusätzliche GUI-/Werkzeug-/Berechtigungs- und Offline-Fallback-Regressionstests.

# 2.5.0 — 2026-09-23

- Vollständige, sichere und pro Projekt/Modell versionierte Programm-ZIPs zusätzlich zum bisherigen Codeexport.
- Verstellbare und ausblendbare linke Chatleiste sowie sichtbarer Auto-Answer-Status.
- Plugin-Tab mit einzeln aktivierbaren Terminal-, PowerShell-, Vision- und Webcam-Funktionen.
- Menschliche Freigabe für jeden Befehl, zeitlich begrenzte Anfrage und Alternativfortsetzung nach Ablehnung.
- Bildanhänge werden gezielt hinzugefügt und bleiben bei automatischem Folgechat erhalten.
- Erweitert verifizierter Installer, GUI- und Archiv-Regressionstest.

# 2.4.1

- Persistierte Themenabschnitte direkt in der linken Chatliste auswählbar.
- Sprung zur gespeicherten Nachrichtenposition, auch nach erneutem Laden.
- Echte Folge-Chats und Vorgänger bleiben separat sichtbar.
- Keine weitere Begrenzung der Titelhistorie auf 64 Einträge.
- Qt-Regressionstest für mehrere Einträge, Auswahl, Scrollposition und Fortsetzen am Gesprächsende.

# Version 2.4.0 — 2026-09-21

- Tokenbudget statt acht Nachrichten als Standard; kein stilles Abschneiden der API-Historie.
- Hintergrundprüfung von Modellgrenze, laufendem Kontext, RAM und NVIDIA-VRAM; konservatives Wachstum, Lastreserve und Pause bei kritischem Speicher.
- Getrennte Steuerung pro Server/Modell, einmaliger OOM-/Kontextfehler-Retry mit kleinerem Kontext.
- Nach Budget übernommene Dialogeinträge und gekennzeichnete, quellenbezogene Übergabeauszüge; Originale bleiben erhalten.
- Dynamische Grundthema-/Schwerpunkttitel mit Nummer, Titelhistorie, Nachrichtenpositionen, Vorgänger-Navigation und Diagnoseansicht per Doppelklick.
- Auto-Answer-Rundenzähler und Anhänge über automatische Übergänge erhalten; Stop setzt geplante Fortsetzungen zurück.
- Auto-Answer-Worker beendet sich bei Abbruch zuverlässig; eigene Modellbudgets und begrenzte Ausgabe.
- Ollama-HTTP-Fehlertexte bleiben für die Speicherdiagnose erhalten; unterbrochene Streams gelten nicht mehr als vollständige Antworten; keine blinde zweite Anfrage bei leerem Stream.
- Native Tokenstatistiken verbessern die modellbezogene Schätzreserve; CJK-/UTF-8-Schätzung korrigiert.
- Neue Defaults: automatische Übernahme, 32k-Obergrenze, kein erzwungener Kurzstil, 512 Token für Auto-Answer-LLM und neutrale Assistentenstimmhöhe. Vorhandene individuelle Einstellungen bleiben bestehen.
- GUI-Limit des Auto-Answer-Modells entspricht jetzt der Konfigurationsgrenze 8192.
- Chatlisten-Cache, vollständige Qt-Integrationstests, klare Teilprüfungsberichte und reproduzierbarer ZIP-Build ohne Benutzerdaten.
- Installer verwendet intakte lokale Pakete wieder, prüft 64-Bit-Python und erhält den Rückgabecode der GUI-Prüfung. Wheelhouse-Build verwendet nur Binärpakete.

# Changelog

## v2.3.0 – 2026-09-01

- Added per-model Ollama Reasoning/Thinking settings: Off, automatic for code, Low, Medium and High.
- Applied the selected model's reasoning level consistently to normal chat and the Auto-Answer LLM path.
- Replaced the narrow Qwen-specific Thinking switch with native Ollama `think` levels for compatible model families.
- Added safe compatibility retries for older Ollama runtimes: level, boolean Thinking, then omission of the unsupported field.
- Added a local Ollama API integration smoke test covering streamed thinking, content and compatibility fallback.
- Added topic-aware automatic continuation titles derived locally from the latest conversation section.
- Added localized, numbered continuation suffixes and persisted parent/index/topic metadata for every rollover chat.
- Fixed premature rollover caused by reserving the full configured maximum response length for every request.
- Added pure context-budget regressions so short prompts no longer create unnecessary follow-up chats.
- Expanded installation verification for the new modules, reasoning controls and API request behavior.

## v2.2.0 – 2026-08-18

- Added separate assistant and user voice profiles, intensity, speaking rate, pitch and volume.
- Added natural, deep/masculine, bright/feminine, narrator, dramatic, robotic, tipsy, comic and whisper profiles.
- Added dependency-free local WAV character effects and VibeVoice fallback modulation.
- Added atomic TTS audio writes, response-type validation and rejection of JSON/HTML error bodies saved as audio.
- Added VibeVoice microphone input through the OpenAI-compatible CrispASR transcription endpoint.
- Added a closed, runtime-verified speech-model catalog: full multilingual VibeVoice ASR, VibeVoice ASR BitNet, Realtime 0.5B GGUF TTS and VibeVoice 1.5B GGUF TTS.
- Added strict task/runtime/backend validation so ASR checkpoints, realtime voice packs and 1.5B TTS are never mixed incompatibly.
- Added a separate CrispASR Windows installer with CPU-legacy default (no AVX2 assumption), plus optional CPU, Vulkan and CUDA variants.
- Restricted the Python VibeVoice wrapper to its supported `microsoft/VibeVoice-Realtime-0.5B` checkpoint.
- Updated VibeVoice setup to use its required separate Python 3.13 environment, with optional winget installation.
- Added safe ZIP extraction, corruption checks, staged wrapper replacement and atomic partial downloads.
- Added central `version.txt` versioning for the app, installer and launcher.
- Reworked the Windows installer to prefer offline wheels, verify package consistency and perform an off-screen GUI startup check before first launch.
- Added `build_wheelhouse.bat` and `tools/verify_installation.py`.
- Added configuration type/range/URL validation and migration for v2.1 profiles.
- Hardened chat-session parsing and filenames against malformed or unsafe stored IDs.
- Improved Ollama response validation and streaming error messages.
- Fixed stop handling between externally generated TTS segments.
- Updated every language pack with the new localizable UI keys.

## v2.1 – 2026-07-21

- Added 20 user and 20 assistant personality presets plus the personality editor.
