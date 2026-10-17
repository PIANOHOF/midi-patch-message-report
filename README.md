<img src="pianohof-logo.png" width="110" height="110" alt="PIANOHOF Logo">

# MIDI Patch Message Report

**Bank Select und Program Change in einer MIDI-Datei finden — lokal, ohne Wiedergabe.**

Beim Start einer MIDI-Datei wählt das Digitalpiano plötzlich einen anderen Klang. Dieser Bericht macht die dafür interessanten Dateinachrichten sichtbar: Bank Select MSB (CC0), Bank Select LSB (CC32) und Program Change. Er zeigt, an welcher Stelle sie gespeichert sind, und lässt sich auf einen Kanal oder eine logische Dateiroute begrenzen. Er repariert kein Instrument und behauptet nicht, den tatsächlich gehörten Klang zu erkennen.

## Was der Bericht enthält

Jede Fundstelle nennt Sequenz, absoluten Tick, Spur, Ereignisposition, logische Portnummer, Kanal, Nachrichtentyp und Rohwert. Kanalnummern werden als 1–16 angezeigt. Für Program Change stehen der gespeicherte Wert 0–127 und zusätzlich eine ausdrücklich als solche bezeichnete Anzeige 1–128 nebeneinander. Das erleichtert den Vergleich mit einer Geräteanzeige, ohne deren Nummerierung vorauszusetzen.

Die Portnummer ist eine Kennzeichnung aus der Datei, keine Erkennung eines USB-Anschlusses. Ohne vorherige MIDI-Port-Metanachricht verwendet der Bericht die logische Vorgabe 0 und markiert `port_declared=false`. Ein späterer Port-Eintrag gilt beim Durchgehen nur für die betreffende Spur. Vorhandene Nummern sagen nicht, welches reale Gerät eine DAW damit verbindet.

## Lokal starten

Benötigt werden Python 3.10 oder neuer und Mido 1.3.3. Eine virtuelle Umgebung hält die Abhängigkeit vom übrigen System getrennt. Der Bericht öffnet keine MIDI-Ein- oder Ausgänge, spielt nichts ab und benötigt weder Konto noch Internetzugriff für die Analyse. Die Eingabedatei bleibt unverändert; JSON oder CSV erscheinen auf der Standardausgabe.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python patch_report.py example.mid
python patch_report.py example.mid --channel 1 --port 1
python patch_report.py example.mid --format csv > report.csv
python -m unittest -v test_patch_report.py
```

Bei einem Fehler liefert das Programm Status 2 und eine Meldung auf der Fehlerausgabe. Eine gültige Datei ohne passende Nachrichten liefert einen leeren Bericht mit Status 0. Die Dateigröße ist auf 32 MiB begrenzt. Das Werkzeug bearbeitet Standard-MIDI-Dateien mit `MThd`-Header; eine Audioaufnahme, ein DAW-Projekt und ein herstellerspezifischer MIDI-2.0-Container sind andere Formate.

## Das Beispiel nachvollziehen

`example.mid` ist vollständig synthetisch. Am Anfang der ersten Spur stehen CC0 mit 2, CC32 mit 5 und Program Change mit dem Rohwert 10. Das Beispiel enthält außerdem zwei kurze Notennachrichten als zeitlichen Abstand. Sie werden nicht als Patch-Nachrichten ausgegeben. Der erste Programmwert erscheint zusätzlich als Anzeige 11; ein konkreter Instrumentenname wird daraus nicht abgeleitet.

Bei Tick 960 stehen auf zwei Spuren derselben logischen Route eine weitere Program-Change-Nachricht und ein Bank-Select-Eintrag. Beide bekommen `cross_track_same_tick=true`. Die vollständige erwartete JSON-Ausgabe liegt in `expected-example.json`. Sie dient zum Nachrechnen der Dateipositionen und Zählwerte, nicht als Aufnahme oder Dokumentation eines realen Fehlers.

## Gleiche Ticks richtig lesen

Innerhalb einer Spur bleibt die gespeicherte Ereignisreihenfolge erhalten. Bei Format 1 können passende Nachrichten mehrerer synchroner Spuren denselben Tick, Port und Kanal betreffen. Der Bericht markiert diese Gruppe und sortiert ihre Zeilen zur Darstellung nach Spur und Ereignisposition. Diese Darstellung legt keine Ausführungsreihenfolge eines Abspielgeräts fest. Insbesondere wird daraus keine vermeintlich sichere Bank-und-Programm-Kombination zusammengesetzt.

Format 2 wird als mehrere unabhängige Sequenzen behandelt: Jede Spur hat ihren eigenen Zeitursprung und eine eigene Sequenznummer. Die Tickwerte sind keine Sekunden oder Taktnummern. Tempo wird nicht umgerechnet. Eine negative gespeicherte Zeitdivision wird als rohe SMPTE-Division gekennzeichnet, statt sie als positive Auflösung pro Viertelnote auszugeben.

## Den Fund mit dem Instrument vergleichen

Suchen Sie zuerst die passende Passage und den vorgesehenen Kanal. Vergleichen Sie dann Rohwert, Anzeige und Bankangaben mit der MIDI-Implementation des konkreten Geräts oder Plugins. Welche Banknummern unterstützt werden und wie ein Empfänger auf die Nachrichten reagiert, bestimmt der Bericht nicht. Er setzt weder General-MIDI-Klangnamen noch einen besonderen Schlagzeugkanal voraus.

Bevor Einstellungen geändert werden, lohnt sich eine Sicherung des eigenen Arbeitsprojekts und ein kontrollierter Vergleich mit derselben Datei. Halten Sie fest, ob die Änderung beim Laden, beim Start oder erst an einer späteren Stelle auftritt. Senden Sie keine vermeintlichen Testbefehle an ein unbekanntes Gerät, nur weil eine Zahl im Bericht steht. Dieses Werkzeug enthält bewusst keine Sendefunktion.

## Grenzen und überprüfbare Dateien

SysEx-Nachrichten werden nur gezählt, nicht entschlüsselt oder mit ihren Nutzdaten ausgegeben. Herstellerbefehle können deshalb außerhalb dieser Fundstellen liegen. Auch CC121 wird nur als nicht interpretierter Reset-Hinweis gezählt. Filter begrenzen die ausgegebenen Zeilen. Im JSON bleiben Dateizählwerte und Hinweise auf gleichzeitig betroffene Spuren ausdrücklich Werte vor der Filterung. CSV enthält nur die ausgewählten Ereigniszeilen und ihre Markierung, keine zusätzlichen Übersichtsfelder. Ein leerer Bericht beweist somit nicht, dass kein Klangwechsel möglich ist.

Die Tests verwenden ausschließlich synthetische Dateien und kontrollieren unter anderem Nummerierungsgrenzen, Delta-Zeiten, Port- und Kanaltrennung, Format 2, gleichzeitige Spuren, beschädigte Eingaben und unveränderte Eingabebytes. Ein unabhängiger Erzeugungsprüfer vergleicht außerdem 100 Streams mit je 120 konstruierten Ereignissen. Quelltext und Dokumentation wurden mit KI-Unterstützung erstellt und geprüft. Programm und Text stehen unter MIT; Name, Logo und andere Markenrechte sind davon ausgenommen.

Grundlagen: [MIDI Association — MIDI messages](https://midi.org/about-midi-part-3midi-messages), [Control Change table](https://midi.org/midi-1-0-control-change-messages), [Mido — MIDI files](https://mido.readthedocs.io/en/stable/files/midi.html) und [message types](https://mido.readthedocs.io/en/stable/message_types.html). Herausgeber ist PIANOHOF. Bei einer technischen Störung am Instrument, die sich durch die Dateinachrichten nicht erklären lässt, informiert die Werkstatt über [E-Piano-Reparatur](https://www.pianohof.de/leistungen/e-piano-reparatur). Ein Dateibericht ersetzt keine Untersuchung vor Ort.
