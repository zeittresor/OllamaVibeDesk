# Prüfung 2.4.1

Vollständige vorhandene Installationsprüfung einschließlich 14 Kontextregressionstests, Kern-/API-Tests und tatsächlicher Qt-Offscreen-GUI ausgeführt. Der GUI-Test prüft zusätzlich mehrere historische Titelzeilen desselben Chats, Erhalt des Vorgänger-Chats, erneutes Laden und Anklicken beider Abschnitte, Scrollziel sowie Fortsetzen am Ende.

Der Screenshot zeigt nur einen Chat-Eintrag; daraus lässt sich kein bereits erfolgter Speicher-Rollover beweisen. Der nachvollziehbare Implementierungsfehler war: ältere Titel waren nur im Detaildialog sichtbar, nicht als auswählbare Positionen in der Seitenleiste. Diese Positionen werden jetzt zusätzlich zu echten Folge-Chats angezeigt.

Kein nativer Windows-Lauf auf diesem Linux-Testhost. Die weiteren Grenzen des Tests aus dem Bericht 2.4.0 gelten weiterhin.
