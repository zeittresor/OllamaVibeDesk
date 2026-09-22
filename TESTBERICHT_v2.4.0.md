# OllamaVibeDesk 2.4.0 — Prüfbericht

Stand: 21.09.2026. Ausgangsbasis: unverändertes Release 2.3.0.

## Ausgeführte Prüfungen

| Prüfung | Ergebnis / Umfang |
|---|---|
| Frische Python-Umgebung | Python 3.12, projektgetrennte venv, alle vier direkten Abhängigkeiten neu installiert; `pip check` ohne Fehler |
| Syntax und Daten | Python-Dateien in app/tools/tests geparst; JSON-Ressourcen, Themes, Persönlichkeiten und gleiche Schlüssel in allen 12 Sprachpaketen geprüft |
| Statische Namensprüfung | Ruff F821/F822/F823 ohne Befund |
| Bestehende Kernprüfungen | Konfiguration, Reasoning, Sprachmodellkatalog, TTS-WAV-Verarbeitung, sichere Archivextraktion und Kernlogik bestanden |
| Adaptive Kontextpolitik | 14 Regressionstests: bedarfsgesteuertes Wachstum, RAM-/VRAM-Druck, kritische Pause, entfernte Server, fehlende Daten, Mehr-GPU-Fallback, Modell-/Fehlergrenzen, kleine Kontextfenster, Konfigurationsmigration, Unicode, vollständige Eingaben, wechselnde Titel, Metadaten und Übergaben über zehn Abschnitte |
| Ollama-Protokoll | Lokaler HTTP-Testserver: Reasoning-Stufen und boolescher Kompatibilitätsfallback; Antwort und Thinking getrennt |
| Echte Qt-Konstruktion | SettingsDialog und MainWindow unter Linux/offscreen geöffnet, Layout/Controls und neuer Defaults-Knopf geprüft |
| GUI + HTTP-Integration | Asynchrone Kontextprüfung über `/api/ps` und `/api/show`, Streamingantwort, Tokenstatistik, Rückkehr zum bedienbaren Fenster |
| Gesprächsübergang | Mehr als acht Nachrichten im API-Kontext; ursprüngliches Ziel, Originaltexte und Vorgängerbezug erhalten; Rundenzähler und Anhänge bleiben erhalten |
| Fehlerszenarien | Simulierter HTTP-500-OOM: genau ein Retry mit 4096 → 2048 Token; wiederholter OOM beendet den Zyklus; übergroße Eingabe bleibt gespeichert; kritische Speicherreserve sendet keine Anfrage; abgebrochene Vorprüfung startet keine verspätete Generierung; abgebrochener Auto-Answer-Worker meldet seinen Abschluss |
| Windows-Paketverfügbarkeit | Pip-Dry-Run für 64-Bit-Windows/Python 3.10 löst zehn Binärpakete erfolgreich auf; keine Quellkompilierung nötig |
| Installer-/Build-Review | BAT-Aufrufpfade, Python-Auswahl, lokale Wiederverwendung, Prüfung vor Erststart, Exitcode-Übernahme, optionale Komponenten und Wheelhouse-Fehlerpfade statisch geprüft |

Die vollständige Prüfung ist über `python tools/verify_installation.py` wiederholbar und wird vom Windows-Installer aufgerufen. `--quick` und `--source-only` weisen ihren eingeschränkten Umfang ausdrücklich aus. Der ZIP-Build ruft die vollständige Prüfung auf, kontrolliert ZIP-Integrität und schreibt eine SHA-256-Datei. Benutzerdaten, Umgebungen, Logs und Caches werden nicht mitgepackt.

## Testumgebung

- Linux x86-64, Python 3.12, PyQt6 6.11.0 / Qt 6.11.2.
- requests 2.34.2, Markdown 3.10.3, psutil 7.2.2.
- GUI-Tests verwenden temporäre Chats, eine isolierte Konfiguration und einen lokalen Protokoll-Testserver. Speicherwerte werden für reproduzierbare Integrationstests simuliert; der produktive Sammler nutzt psutil und gegebenenfalls nvidia-smi.
- Neue/angepasste Oberflächentexte sind Deutsch und Englisch; andere Sprachpakete verwenden hierfür englischen Fallback. Vorhandene übrige Übersetzungen bleiben erhalten.

## Noch nicht praktisch belegt

Ein nativer Windows-Installationslauf, Windows-SAPI-Wiedergabe, Mikrofon-Hardware, reale VibeVoice-Modelle sowie Last-/OOM-Tests mit einer tatsächlichen Ollama-GPU-Laufzeit konnten auf diesem Host nicht durchgeführt werden. Die Paketauflösung ersetzt keinen Windows-Lauf. Der Testserver belegt die API- und GUI-Fehlerbehandlung, nicht die Antwortqualität echter Modelle.

Die Speichersteuerung ist eine konservative Heuristik vor Anfragen, kein Echtzeit-Monitor während jeder Tokenausgabe. Sie berücksichtigt keine garantierte Obergrenze für fremde Prozesse oder andere Clients am Ollama-Server. Unbekannte KV-Architekturen und unklare GPU-Zuordnung begrenzen automatisches Wachstum. Sehr große Modellgewichte können selbst beim kleinen Kontext nicht passen. Ein universelles Versprechen „keine OOMs“ wäre deshalb unzutreffend.

Übergaben sind begrenzte Textauszüge, keine verlustfreie Erinnerung. Sie priorisieren das ursprüngliche menschliche Ziel und jüngere ältere Beiträge; Details können entfallen. Für die Diagnose bleiben Originalchats, Titelhistorie, Quellenpositionen und Wechselgrund erhalten. Die Titelerkennung ist eine Schlüsselwortheuristik, keine semantische Modellbewertung.

## Kurzer Abnahmelauf auf Windows

1. Bestehenden Projektordner sichern; neues ZIP entpacken bzw. Quelldateien über den bestehenden Projektordner kopieren (ohne app_data zu ersetzen).
2. `install_windows.bat` ausführen und vollständige Prüfung im Installationslog kontrollieren.
3. In den Optionen „Adaptive Diskussionswerte übernehmen“ wählen und speichern; ein installiertes Ollama-Modell auswählen.
4. Mehr als acht kurze Nachrichten austauschen: kein automatischer Wechsel nur wegen dieser Zahl.
5. Gespräch länger fortführen und Thema wechseln; Titelentwicklung sowie später Übergabe/Vorgänger per Doppelklick auf einen Abschnitt prüfen.
6. Auto-Answer mit begrenzter Rundenzahl testen: automatischer Abschnittswechsel darf den Zähler nicht zurücksetzen. Stop darf keine weiteren Runden planen.
7. `build_release.bat` ausführen; ZIP und SHA-256 liegen anschließend im Ordner release.

Die Schritte 1–7 sind der noch offene native Windows-Abnahmelauf, keine bereits behaupteten Testergebnisse.
