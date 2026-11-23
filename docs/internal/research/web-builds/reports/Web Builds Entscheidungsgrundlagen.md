# Threads, Toolchain und Imports prägen Web-Builds

Die neun offenen Fragen des Web-Prototyps sind nicht gleichrangig. Drei bilden eine Kette, die zuerst und gemeinsam entschieden werden muss: **die Template-Wahl (Threads × `dlink`)**, **die Form des Runtimes** und **die Emscripten-Toolchain**. Threads verändern die native ABI von Extensions und die Hosting-Anforderungen. `dlink` verändert nur, welches Template geladen wird, und damit, ob der Runtime mehr als eine Datei bereitstellen muss. Die Toolchain bestimmt, ob Extensions und quellgebaute Engines überhaupt für das Web entstehen. Alle anderen Fragen, also Tests, Shell-Dateien, Ausgabe-Layout, `bazel run`, Renderer und Debug-Symbole, lassen sich danach lokal entscheiden. Godot selbst empfiehlt seit 4.3 Exporte ohne Threads und liefert Extensions-Support nur in separaten `dlink`-Templates. Ein erster Meilenstein „prebuilt, nothreads, ohne Extensions, nur GDScript“ ist deshalb fachlich gedeckt und hält die teuren Fragen offen. Ein Befund reicht über das Web hinaus: Ohne explizite Projekteinstellungen hängt die Auswahl der VRAM-komprimierten Texturformate beim Import von der **CPU der Ausführungsplattform** ab. ARM-Linux-Hosts erzeugen ETC2/ASTC, x86- und alle macOS-Hosts S3TC/BPTC. Das betrifft die Import-Ausgaben aller Exportplattformen und sollte unabhängig von Web-Support behoben werden. Die Empfehlungen in diesem Bericht sind als **Vorschlag** markiert. Entschieden hat das Team noch nichts.

Quellenkonventionen: Godot-Quelltextverweise zeigen auf den Tag [`4.7.2-stable`](https://github.com/godotengine/godot/tree/4.7.2-stable) (Commit `ed1daf0b`, derselbe Hash steht in den offiziellen Templates). Die Zeilennummern wurden in der lokalen Kopie im Bazel-Repository-Cache geprüft. Aussagen zu 4.8 beruhen auf der lokalen 4.8-beta-Kopie des Rulesets und auf den offiziellen 4.8.beta1-Templates. Größen stammen aus lokalen Messungen an den offiziellen Templates. Ruleset-Pfade sind relativ zu diesem Bericht verlinkt.

## Überblick: neun Entscheidungen, drei davon gekoppelt

| # | Entscheidung | Hängt zusammen mit | Vorschlag (kurz) | Experiment vor der Entscheidung |
| --- | --- | --- | --- | --- |
| 1 | Threads/`dlink` | 2, 5, 6, 7, 8 | Threads als Constraint vorbereiten, zunächst nur nothreads; `dlink` aus den Web-Extensions des Packs ableiten | nothreads-Side-Module im `dlink_nothreads`-Template laden |
| 2 | Emscripten-Toolchain, nicht unterstützte Targets | 1, 3, 7, 9 | Sofort: inkompatible Fallback-Toolchains für `os:emscripten`; später: der Consumer registriert emsdk, das Ruleset validiert die Version | Vorrang Fallback vs. emsdk; godot-cpp als Side Module mit emsdk |
| 3 | Tests auf Web | 2, 8 | A: inkompatibel/übersprungen; B erst mit Harness aus `bazel run --headless` | `quit(code)` → `onExit` in headless Chrome |
| 4 | Texturformate/Imports | alle Exportplattformen | Import-Familien pro Zielplattform explizit setzen; Web: S3TC/BPTC immer | ARM-Linux-Import reproduzieren; Pack-Größe messen |
| 5 | Shell, Icons, Splash, PWA | 1, 6 | Hybrid: Probe rendert Bilder, Python füllt Text; PWA opt-in | Golden-Vergleich gegen Godots eigenen Export |
| 6 | Ausgabe-Layout, Provider | 1, 5, 8 | `index.*` behalten; Output-Groups, Provider erst bei Bedarf | – |
| 7 | Form des Runtimes, Versionsprüfung | 1, 2 | Im Repository-Rule entpacken und beschreiben; Godot- und Emscripten-Version als Fakten | – |
| 8 | `bazel run` | 1, 3 | 127.0.0.1, 8060 mit Ausweichport, `--device` = Browser | – |
| 9 | Scope, Renderer, C#, Debug-Symbole | alle | Scope zuerst; C# zur Analysezeit ablehnen; Renderer-Hinweis | – |

## Querschnittsbefund: Import-Ausgaben hängen von der Host-CPU ab

Dieser Befund steht vor den Einzelentscheidungen, weil er nicht nur das Web betrifft. Die Projekteinstellungen `rendering/textures/vram_compression/import_s3tc_bptc` und `import_etc2_astc` sind beide standardmäßig `false` ([rendering_server.cpp:3659-3660](https://github.com/godotengine/godot/blob/4.7.2-stable/servers/rendering/rendering_server.cpp#L3659-L3660)). Ist eine davon aus, importiert der Importer die Familie trotzdem, wenn `OS::get_preferred_texture_format()` sie bevorzugt ([resource_importer_texture_settings.cpp:38-53](https://github.com/godotengine/godot/blob/4.7.2-stable/editor/import/resource_importer_texture_settings.cpp#L38-L53)). Diese Präferenz wird zur Compile-Zeit über die CPU-Architektur des Editors entschieden. **ARM-Builds liefern ETC2/ASTC, x86-Builds S3TC/BPTC** ([core/os/os.cpp:747-755](https://github.com/godotengine/godot/blob/4.7.2-stable/core/os/os.cpp#L747-L755)). macOS überschreibt das auf **allen CPUs mit S3TC/BPTC** ([os_macos.mm:1058-1062](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/macos/os_macos.mm#L1058-L1062)). Der Koordinator hat beide Stellen im 4.7.2-Quelltext nachgeprüft. Linux hat keinen Override.

In rules_godot läuft ein Import einmal pro Projekt und Zielplattform ([architecture.md](../../../../../rules_godot/docs/internal/architecture.md)). Welche `.ctex`-Varianten eine Import-Action schreibt, hängt dann bei unveränderten Einstellungen von der Ausführungsplattform ab. Ein lokaler Mac und ein BuildBuddy-Linux-x86_64-Executor erzeugen zufällig dasselbe, nämlich S3TC/BPTC. Ein Linux-arm64-Executor oder ein Linux-Container auf Apple Silicon erzeugt dagegen nur ETC2/ASTC. Für das Web ist die Folge besonders unangenehm. Ein Web-Pack mit dem Standard `for_desktop = true, for_mobile = false` fände dann keine passende Remap-Variante und verlöre alle VRAM-komprimierten Texturen. Der Web-Exporter meldet dafür in 4.7.2 und 4.8 beta **keinen Fehler**, weil er nur den Mobile-Fall prüft ([export_plugin.cpp:466-479](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/export/export_plugin.cpp#L466-L479)). Auf anderen Plattformen fangen die Exporter von macOS, Android und Apple-embedded einen Teil davon mit eigenen Prüfungen ab. Die Prüfung für beliebige Presets steckt nur im Export-Dialog des Editors und läuft bei headless `--export-*` nicht. Das Szenario folgt aus den zitierten Codepfaden und wurde **nicht experimentell reproduziert**. Weil die Editor-Binaries je Host verschieden sind, entstehen auch unterschiedliche Action-Keys. Das Problem ist also keine Cache-Vergiftung, sondern fehlende Reproduzierbarkeit über Hosts hinweg und, je nach Exporter, stiller Funktionsverlust.

**Vorschlag:** Das Ruleset setzt beide Import-Schalter pro Zielplattform explizit, damit das Ergebnis nie von der Host-CPU abhängt. Weil die Import-Konfiguration `import_etc2_astc` bereits führt ([project_config_test.py](../../../../../rules_godot/godot/private/tests/project_config_test.py)), ist das eine Erweiterung bestehender Mechanik und keine neue Kostenklasse. Die Web-spezifische Ausgestaltung beschreibt Entscheidung 4.

## Entscheidung 1: Threads ändern die ABI, `dlink` nur die Verpackung

### Hintergrund

Zwei boolesche Exportoptionen bestimmen den Template-Namen eins zu eins: `web` + `_dlink` (bei `variant/extensions_support`) + `_nothreads` (ohne `variant/thread_support`) + `_debug.zip`/`_release.zip`. Daraus ergeben sich acht Templates ([export_plugin.h:59-73](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/export/export_plugin.h#L59-L73)). Beide Optionen sind standardmäßig `false` ([export_plugin.cpp:374-375](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/export/export_plugin.cpp#L374-L375)). Dieselben Schalter steuern noch mehr. Sie erzeugen die Feature-Tags `threads`/`nothreads` und `web_extensions`/`web_noextensions` ([export_plugin.cpp:348-367](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/export/export_plugin.cpp#L348-L367)). Sie setzen die HTML-Konstante `$GODOT_THREADS_ENABLED`, die den Browser-Check auf Cross-Origin-Isolation auslöst. Und sie bestimmen, ob die PWA-On-Demand-Cache-Liste `.side.wasm` und die Extension-Dateien enthält ([export_plugin.cpp:135-193, 229-275](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/export/export_plugin.cpp#L135-L275)). Zur Laufzeit beantwortet die Engine dieselben Tags aus Compile-Defines (`THREADS_ENABLED`, `WEB_DLINK_ENABLED`). **Export-Tags und Laufzeit-Tags stimmen also nur überein, wenn das Template zu den Optionen passt** ([os_web.cpp:160-178](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/os_web.cpp#L160-L178)).

Godot prüft eine Fehlkombination erst im Browser. `gdextensionLibs` wird aus den Shared Objects des Packs befüllt, **unabhängig** von `extensions_support`. Erst `startGame` bricht ab, wenn der Runtime `loadDynamicLibrary` fehlt ([engine.js:165-169](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/js/engine/engine.js#L165-L169)). Ein Ruleset kann diese Prüfung auf die Build-Zeit vorziehen. Der Prototyp leitet Threads außerdem falsch ab. Er sucht `godot.worker.js` im Template, aber kein 4.7.2- oder 4.8-Template enthält diese Datei. Godot entscheidet über die Exportoption ([package_web.py](../../../../../rules_godot/tools/platforms/package_web.py)).

**Kosten von `dlink`:** Ein `dlink`-Template ist ein kleines `MAIN_MODULE=1`-Programm mit `EXPORT_ALL`, das ganz Godot als Side Module lädt ([SCsub:79-99](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/SCsub#L79-L99)). Gemessen an den 4.7.2-Release-Templates sind das **1,5 MB `godot.wasm` plus 44,1 MB `godot.side.wasm` statt 39,5 MB**. Die ZIPs wachsen von 10,2 auf 11,5 MB, und `godot.js` wächst von 0,28 auf 2,86 MB (lokale Messung). Emscripten nennt dynamisches Linken einen Overhead, empfiehlt für Performance statisches Linken und führt „Dynamic linking + pthreads“ als experimentell ([Emscripten: Dynamic Linking](https://emscripten.org/docs/compiling/Dynamic-Linking.html)). Laufzeitmessungen `dlink` gegen statisch wurden nicht gefunden.

**Kosten von Threads:** Threaded Exporte brauchen `SharedArrayBuffer` und damit Cross-Origin-Isolation durch COOP `same-origin` und COEP `require-corp` ([MDN SharedArrayBuffer](https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/SharedArrayBuffer)). Godot nennt den Single-Thread-Export „the preferred and now default way“. Grund sind die Schwierigkeiten mit Isolation, der Verlust von Werbung und Drittintegrationen und Probleme unter macOS und iOS ([Exporting for the Web](https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_web.html)). Der 4.3-Blog spricht davon, mit SharedArrayBuffer „on the wrong horse“ gesetzt zu haben ([Web Export in 4.3](https://godotengine.org/article/progress-report-web-export-in-4-3/)). Die Opt-in-Option von itch.io beruht auf COEP `credentialless`, und **Safari unterstützt `credentialless` bis heute nicht** ([caniuse](https://caniuse.com/mdn-http_headers_cross-origin-embedder-policy_credentialless)). GitHub Pages erlaubt keine eigenen Header ([community #13309](https://github.com/orgs/community/discussions/13309)). Dort funktionieren Threads nur mit Godots PWA-Service-Worker, der die Header simuliert ([service-worker.js](https://github.com/godotengine/godot/blob/4.7.2-stable/misc/dist/html/service-worker.js)). **Threads koppeln also an Entscheidung 5 (PWA).**

**ABI:** Ein threaded Side Module (`-sUSE_PTHREADS=1`, ab 4.8 `-pthread`) lässt sich nicht in einen nothreads-Main-Module laden und umgekehrt. godot-cpp hängt dafür `.nothreads` an den Bibliotheksnamen. `.gdextension`-Dateien wählen Web-Bibliotheken über den Tag `threads` aus, wie bei einer CPU ([godot-cpp tools/web.py](https://github.com/godotengine/godot-cpp/blob/master/tools/web.py), [godot-rust: Export to Web](https://godot-rust.github.io/book/toolchain/export-web.html)). `dlink` ändert die ABI der Extension dagegen nicht, denn Extensions sind immer Side Modules. Es entscheidet nur, ob das Template sie laden kann. 4.8 baut den `dlink`-Main-Module zusätzlich mit `-fwasm-exceptions` ([godot#124118](https://github.com/godotengine/godot/pull/124118)). Extensions, die C++-Exceptions brauchen, laufen deshalb auf 4.7 im Web nicht, und Extensions für 4.8 müssen mit Wasm-Exceptions gebaut werden.

Ein Widerspruch in den Quellen ist offen. Die Godot-Doku sagt, Extensions Support brauche „also“ Isolation-Header ([Exporting for the Web](https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_web.html)). Der 4.7.2-Quelltext prüft Isolation aber nur bei `threads` ([features.js:94-101](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/js/engine/features.js#L94-L101)) und liefert `web_dlink_nothreads_*`-Templates aus. Der Doku-Satz stammt vermutlich aus 4.2, als `dlink`-Templates immer threaded waren. Hier gilt der Quelltext, ein Experiment sollte das bestätigen.

### Optionen und Folgen

Andere Rulesets modellieren solche Dimensionen unterschiedlich. emsdk behandelt Threads als **Attribut pro Binary**, das über eine Transition das Toolchain-Feature `use_pthreads` setzt ([wasm_cc_binary.bzl](https://github.com/emscripten-core/emsdk/blob/main/bazel/emscripten_toolchain/wasm_cc_binary.bzl)). apple_support modelliert Device und Simulator als **Plattform-Constraint** ([constraints/BUILD](https://github.com/bazelbuild/apple_support/blob/main/constraints/BUILD)). rules_godot nutzt bereits beide Muster: den Constraint für die iOS-Umgebung ([platforms/BUILD.bazel](../../../../../rules_godot/godot/platforms/BUILD.bazel)) und `//godot:variant` als `string_flag` mit `target_settings` an den Runtime-Toolchains ([components.bzl](../../../../../rules_godot/godot/engine/private/components.bzl)).

| Option | Folgen für Threads | Folgen für `dlink` | Folgen für andere Features |
| --- | --- | --- | --- |
| A. Fest: nothreads, `dlink` nur bei Bedarf | Keine Threads; eine einzige Extension-ABI | „bei Bedarf“ ist in Wahrheit D oder B | Ein Runtime-Slot pro Variante; einfachstes Hosting |
| B. Attribut von `godot_export_platform`, als Constraint | Passt: Threads ändern die native ABI wie Device/Simulator; `select()`, `target_compatible_with` und cc-Toolchain-Auflösung sehen es; Add-ons können threaded Web ausschließen | Passt schlecht: keine ABI-Wirkung, eine Plattform pro Wert | Mehr Exportplattformen und Konfigurationen, kein Cache-Sharing zwischen ihnen (für ABI-verschiedenen Code ohnehin unvermeidbar) |
| C. Build-Setting wie `//godot:variant` | Global pro Build, threaded und nothreads nicht in einem Aufruf; native Builds müssen dasselbe Flag lesen; für `@platforms`-Kompatibilität unsichtbar | Passt besser, weil `dlink` eine Verpackungswahl ist | Kein automatisches Überspringen inkompatibler Add-ons |
| D. Abgeleitet: `dlink` genau dann, wenn das Pack Web-Extensions hat | Nicht anwendbar, Threads sind eine Hosting-Entscheidung | Sicherer als Godot selbst; die Extensions sind zur Analysezeit bekannt | Der Runtime muss beide Templates (mit/ohne `dlink`) bereitstellen, die Application-Rule wählt (Entscheidung 7); `variant/extensions_support` und der Feature-Tag `web_extensions` müssen beim Pack-Export folgen |

### Offen und Experimente

Nicht getestet ist, ob ein nothreads-Side-Module im 4.7.2-`dlink_nothreads`-Template tatsächlich lädt. Belegt ist nur der Codepfad über `dynamicLibraries` ([config.js:286-292](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/js/engine/config.js#L286-L292)) sowie ein Forenbericht ([Godot Forum](https://forum.godotengine.org/t/gdextension-not-loading-in-web-export/81867)). Dasselbe Experiment klärt den Doku-Widerspruch: Läuft eine `dlink_nothreads`-Seite ohne COOP/COEP? Für Option D ist außerdem zu klären, wie die Ableitung in den Pack-Export zurückwirkt. Der Prototyp besitzt `variant/*` als Konstante `false`, und die Feature-Tags des Packs hängen davon ab. Offen ist schließlich, ob nicht nur 4.8, sondern auch 4.7 bei `dlink`+Threads praktisch brauchbar ist. Upstream hat Emscripten auf 6.0.12 gehoben, weil ältere Versionen „invalid dlink+pthread builds“ erzeugten ([build-containers](https://github.com/godotengine/build-containers/commits/main/Dockerfile.web)).

### Vorschlag

**Vorschlag (keine Entscheidung):** Threads als Constraint-Setting an `godot_export_platform` anlegen, mit Default `nothreads`, aber zunächst nur die Plattform `web_wasm32` (nothreads) ausliefern. Eine spätere `web_wasm32_threads`-Plattform kommt dann ohne Umbau hinzu. `dlink` nach Option D aus den Web-Extensions des Packs ableiten. Dazu kommt ein Analysefehler, falls jemand Extensions mit explizit abgeschaltetem `dlink` kombiniert. Das entspricht Godots Default, hält die Extension-Matrix klein (eine Web-ABI) und zieht Godots Laufzeitfehler auf die Build-Zeit vor. Der Preis ist ein Runtime, der zwei Templates beschreibt (siehe Entscheidung 7).

## Entscheidung 2: Nur emsdk baut Side Modules, und Shared Libraries fehlen dort noch

### Hintergrund

Die einzige Bazel-Toolchain für `wasm32-unknown-emscripten` ist die von emsdk. Auf der BCR liegt sie als Modul `emsdk`, Version **7.0.0 vom 2026-11-07**, nur für Bzlmod ([BCR emsdk](https://registry.bazel.build/modules/emsdk), [README](https://github.com/emscripten-core/emsdk/blob/main/bazel/README.md)). toolchains_llvm und hermetic_cc_toolchain können nur freestanding- oder WASI-Wasm, und das reicht für Godots Side-Module-ABI nicht ([toolchains_llvm common.bzl](https://github.com/bazel-contrib/toolchains_llvm/blob/master/toolchain/internal/common.bzl), [hermetic_cc_toolchain](https://github.com/uber/hermetic_cc_toolchain/blob/main/README.md)). emsdk registriert seine C++-Toolchains aus dem eigenen MODULE.bazel und schränkt nur auf `@platforms//cpu:wasm32` ein. **Jedes `bazel_dep(emsdk)` im Graphen macht also eine Toolchain verfügbar, die zu `web_wasm32` passt.** Die Version ist ein Singleton. `emscripten_deps.config(version = …)` schlägt fehl, wenn mehr als ein Modul eine Version setzt ([emscripten_deps.bzl](https://github.com/emscripten-core/emsdk/tree/7.0.0/bazel)).

Für Hermetik und Remote Execution gilt Folgendes. Die Archive sind gepinnt und kosten **280–355 MB pro Host und Version** (gemessen über Content-Length, z. B. 4.0.20 linux x86_64 354,6 MB). Ausführungsplattformen gibt es für Linux x86_64/arm64, macOS und Windows. Die Default-Sysroot enthält aber **keine PIC-, LTO- oder 64-bit-Systembibliotheken**. Varianten baut `embuilder` in einem Repository-Rule auf dem Host. Diese Ausgaben sind weder remote cachebar noch nach Nutzerberichten deterministisch: CI-Rebuilds „completely invalidate the build cache“ ([emsdk #1581](https://github.com/emscripten-core/emsdk/issues/1581)). Mit `prebuilt_cache` lässt sich das umgehen.

**Side Modules sind der eigentliche Engpass.** emsdks `toolchain.bzl` schaltet `supports_pic` und `supports_dynamic_linker` ab ([toolchain.bzl](https://github.com/emscripten-core/emsdk/blob/7.0.0/bazel/emscripten_toolchain/toolchain.bzl)). `cc_binary(linkshared = True)` scheitert ab Emscripten 6 mit Relocation-Fehlern. Issue #1714 ist offen, und ein Maintainer schreibt, er habe `linkshared` mit Emscripten „never seen … working“ ([emsdk #1714](https://github.com/emscripten-core/emsdk/issues/1714)). Eine GDExtension braucht deshalb eine Transition, die `-fPIC -sSIDE_MODULE=1` und die ABI-Flags der Engine auf die gesamte transitive Hülle einschließlich godot-cpp legt. Diese Flags sind Threads, `-sWASM_BIGINT`, `-sSUPPORT_LONGJMP=wasm`, wasm32 und ab 4.8 `-fwasm-exceptions` ([godot-cpp tools/web.py](https://github.com/godotengine/godot-cpp/blob/master/tools/web.py)). Eine Alternative ist eine eigene Toolchain-Konfiguration. Hinzu kommt, dass emsdk den Clang-Include-Pfad fest einträgt ([emsdk #1580](https://github.com/emscripten-core/emsdk/issues/1580)). Eine ältere Emscripten-Version unter einem neueren emsdk-Modul ist daher riskant.

**Versionen:** Die offiziellen 4.7.2-Templates wurden mit **Emscripten 4.0.20** gebaut. `godot.js` gibt in `godot_js_emscripten_get_version` den Wert „4.0.20“ zurück (vom Koordinator verifiziert), und der `4.7`-Branch von build-containers pinnt dieselbe Version ([Dockerfile.web@4.7](https://github.com/godotengine/build-containers/blob/4.7/Dockerfile.web)). 4.8 beta1 nutzt **6.0.12** (lokale Messung). Godots eigene CI und godot-cpps CI verwenden 4.0.11. Maßgeblich für Extensions ist also der Release-Build, nicht die CI. Eine offizielle Godot-Regel, dass Extensions exakt dieselbe Emscripten-Version brauchen, gibt es nicht ([Compiling for the Web](https://docs.godotengine.org/en/4.7/engine_details/development/compiling/compiling_for_web.html)). Die Anforderung folgt aus der fehlenden ABI-Stabilität von Emscripten zwischen Versionen und aus Community-Berichten.

**Nicht unterstützte Targets:** Ohne Toolchain scheitert die Analyse mit einem Fehler, statt das Target zu überspringen. Im Prototyp betrifft das 36 Targets an `@bazel_tools//tools/cpp:toolchain_type` und 8 an rules_dart ([web-prototype.md](../../../../../rules_godot/docs/internal/web-prototype.md)). Bazel überspringt nur inkompatible Targets, und Inkompatibilität ist transitiv ([Bazel: Platforms](https://bazel.build/extending/platforms)). In einem lokalen Experiment mit Bazel 9.3.0 hat ein Muster funktioniert, das ohne Änderungen an jedem Add-on auskommt. Man registriert für `@bazel_tools//tools/cpp:toolchain_type` eine **Fallback-Toolchain mit `target_compatible_with = ["@platforms//os:emscripten"]`, deren `toolchain` auf `@platforms//:incompatible` zeigt**. Daraufhin wurden `cc_library`, `cc_binary(linkshared)` und ein abhängiges Genrule übersprungen, und der Build war erfolgreich. Ohne die Registrierung scheiterte er mit „No matching toolchains found“. Für rules_dart funktioniert dasselbe.

### Optionen und Folgen

| Wer liefert die Toolchain | Folgen |
| --- | --- |
| A. Der Consumer registriert emsdk und setzt die Version; das Ruleset validiert gegen die Version des Runtimes | Keine Singleton-Konflikte; folgt dem Root-Vorrang-Modell von rules_go; nur eine Emscripten-Version pro Graph, also keine zwei Godot-Minors mit Web-Extensions gleichzeitig |
| B. Das Ruleset liefert eigene Emscripten-Repositories und Toolchains pro Godot-Profil (wie der Android-Hub in [android_toolchains.bzl](../../../../../rules_godot/godot/platforms/private/android_toolchains.bzl)) | Mehrere Engine-Versionen nebeneinander möglich; dafür eine eigene cc-Toolchain-Konfiguration pflegen (emsdks `create_toolchains` hängt an `@emscripten_cache`/`@emsdk`) und ~300 MB pro Version und Host |
| C. Das Ruleset hängt an emsdk und setzt die Version | Kollidiert mit jedem Consumer, der selbst eine Version setzt; für ein BCR-Modul nicht ratsam |

| Ohne Toolchain | Folgen |
| --- | --- |
| Fallback-Toolchain (inkompatibel) für `os:emscripten` | Add-ons, `godot_cc_extension`, sqlite, app_auth, platform_paths, Dart werden übersprungen, ohne dass jedes Add-on etwas deklariert; eine echte Toolchain übernimmt automatisch, wenn sie vorher aufgelöst wird; eine Web-App, die über ihr Pack an einer übersprungenen Extension hängt, wird stumm mit übersprungen |
| `target_compatible_with` an jedem Add-on | Explizit, aber jede Ergänzung muss daran denken; vorhandene Muster in reifen Rulesets (z. B. rules_rust) |

### Offen und Experimente

Ungetestet ist der Vorrang zwischen der Fallback-Toolchain und emsdks Toolchain, wenn beide aus Nicht-Root-Modulen kommen. Abhilfe könnte ein `target_settings` an der Fallback-Toolchain schaffen, das bei Opt-in einer Web-cc-Toolchain falsch wird. Ebenfalls ungetestet ist ein godot-cpp-Side-Module mit emsdks Bazel-Toolchain: Reicht `--copt=-fPIC`, oder braucht es PIC-Systembibliotheken? Unklar ist auch, ob ein macOS-Host mit Linux-RBE wegen des Host-Alias `@emscripten_cache` sowohl das Mac- als auch das Linux-Archiv lädt. Eine Diagnose für eine stumm übersprungene Web-App (etwa „keine Emscripten-Toolchain“ bei explizit angefragtem Target) wäre wünschenswert. Quellgebaute Web-Engines setzen dieselbe Toolchain voraus. Dazu kommen JS-Libraries, Pre-/Post-JS, Multi-Output-Link, Closure-Compiler mit Node und für `dlink` eine PIC-Sysroot. Prior Art in Bazel fehlt.

### Vorschlag

**Vorschlag (keine Entscheidung):** Sofort inkompatible Fallback-Toolchains für cc und Dart auf `os:emscripten` registrieren, damit Web-Wildcards überspringen statt zu scheitern. Web bleibt zunächst prebuilt-only. Für den Extension-Meilenstein Option A wählen: Der Consumer registriert emsdk, das Profil in `profiles.bzl` hält die Emscripten-Version des offiziellen Templates (4.7 → 4.0.20, 4.8 → 6.0.12), und das Ruleset vergleicht sie mit dem Wert aus `godot.js` (Entscheidung 7). Die Side-Module-Flags trägt eine Transition der Extension-Rule. Option B lohnt erst, wenn mehrere Godot-Minors mit Web-Extensions in einem Graphen gefordert sind. Weil Remote Execution kompatibel bleiben soll, gehört ein `prebuilt_cache` statt `embuilder` zur Bedingung, bevor PIC-Varianten nötig werden.

## Entscheidung 3: Browser-Tests hätten keinen Präzedenzfall

### Hintergrund

`bazel test` scheitert, weil keine Ausführungsplattform `os:emscripten` für `default_test_toolchain_type` trägt. Bazels Default-Test-Toolchain verlangt, dass die Ausführungsplattform die Constraints der Zielplattform hat ([BUILD.tools, 9.3.0](https://bazel.googlesource.com/bazel/+/refs/heads/release-9.3.0/tools/test/BUILD.tools)). rules_godot registriert für Linux und macOS bereits eigene Test-Toolchains mit `exec_compatible_with` = `target_compatible_with` ([config/BUILD.bazel](../../../../../rules_godot/godot/private/config/BUILD.bazel)). Ein Web-Eintrag, der Web-Ziele auf Host-Ausführungsplattformen abbildet, folgt dem vorhandenen Muster.

Ein Web-Test braucht einen echten Browser. Der Runtime verlangt WebGL 2 und ein `<canvas>` ([display_server_web.cpp](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/display_server_web.cpp), [config.js:334-342](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/js/engine/config.js#L334-L342)). Godots `--headless` setzt einen Headless-Display-Server ein, die Web-Hauptschleife castet aber statisch auf `DisplayServerWeb` ([web_main.cpp:80-86](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/web_main.cpp#L80-L86)). **„Headless“ heißt im Web daher headless Browser mit Software-WebGL.** Den Fehlcast haben wir nur gelesen, nicht ausgeführt. Ausgabe und Exit-Code gelangen sauber nach außen. `onPrint`/`onPrintError` und `onExit(status_code)` sind Engine-Config-Callbacks, und `get_tree().quit(code)` endet in `emscripten_force_exit(exit_code)` ([config.js](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/js/engine/config.js), [web_main.cpp:61-74](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/web_main.cpp#L61-L74)). Ein Harness lädt `index.js` in einer eigenen Seite und übergibt Testargumente über `args`.

Zum Ökosystem: `rules_webtesting` ist archiviert ([GitHub](https://github.com/bazelbuild/rules_webtesting)). `rules_browsers` (BCR 0.4.0, Februar 2026, ohne Versionierungsversprechen) pinnt `chrome-headless-shell` aus Chrome for Testing, aber **ohne Linux arm64** ([chromium.bzl](https://github.com/devversion/rules_browsers/blob/main/browsers/private/versions/chromium.bzl)). `rules_playwright` zieht rules_js und Node mit ([rules_playwright](https://github.com/mrmeku/rules_playwright)). Beide wählen den Browser über die *Ziel*-Konfiguration, die hier emscripten wäre. Der Browser muss also als exec-konfiguriertes Tool eingebunden werden. Auf GPU-losem Linux liefert Chrome WebGL nur über SwiftShader. Das ist seit Chrome 130 kein automatischer Fallback mehr und braucht `--enable-unsafe-swiftshader` als Opt-in ([Chromium SwiftShader](https://chromium.googlesource.com/chromium/src/+/main/docs/gpu/swiftshader.md)). Ohne gepinnten Browser riskiert man, dass das Opt-in in einer späteren Chrome-Version verschwindet.

GdUnit4 hat seinen Kern von `EditorInterface` gelöst. Sein CLI-Runner läuft auf `template_debug`-Binaries ([gdUnit4#973](https://github.com/godot-gdunit-labs/gdUnit4/pull/973), [#1237](https://github.com/godot-gdunit-labs/gdUnit4/pull/1237)). Web-Unterstützung, Doku oder Issues dazu gibt es nicht ([gdUnit4#969](https://github.com/godot-gdunit-labs/gdUnit4/issues/969)). Godots eigene `web_builds.yml` baut nur und testet nicht im Browser ([web_builds.yml](https://github.com/godotengine/godot/blob/master/.github/workflows/web_builds.yml)). **Nach der Regel „precedent or remove“ spricht das gegen Option B als Startpunkt.**

### Optionen und Folgen

| Option | Folgen |
| --- | --- |
| A. Web-Tests inkompatibel, in Wildcards übersprungen | Billig; Tests laufen weiter nur auf Desktop; konsistent mit der Fallback-Logik aus Entscheidung 2 |
| B. GdUnit im headless Browser gegen den Wasm-Runtime | Testet den echten Runtime; braucht gepinnten Browser als exec-Tool, Harness mit `onPrint`/`onExit`, JUnit-XML aus dem Browser-FS (IndexedDB) oder aus stdout; pro Testtarget Browserstart plus ~40 MB Wasm und SwiftShader-Rendering; kein öffentliches Vorbild; neue Lane-Kosten |
| C. Auf dem Host-Editor mit Web-Feature-Tags, wie die Editor-Variante | Prüft Web-spezifische GDScript-Zweige, nicht den Wasm-Runtime; kein Browser nötig; prüft weder Threads noch Extensions noch Texturauswahl |

### Offen und Experimente

Ein Versuch von etwa 20 Minuten würde klären, ob `get_tree().quit(code)` im `web_nothreads_debug`-Template 4.7.2 zuverlässig `onExit(code)` auslöst. Dafür reichen ein Export, ein gepinnter headless-shell und zehn Läufe, die gleichzeitig Boot-Zeit und Flakiness unter SwiftShader messen. Für B ungeklärt: Findet GdUnits Test-Discovery in einem exportierten Pack Skripte trotz `.remap` und binärer Tokens? Und wie lässt sich die Test-Toolchain für Web so registrieren, dass `godot_test` sauber inkompatibel wird? Für eigene Toolchain-Typen hat das lokale Experiment gezeigt, dass das funktioniert. Für `default_test_toolchain_type` ist es noch nicht geprüft.

### Vorschlag

**Vorschlag (keine Entscheidung):** Option A jetzt umsetzen, und zwar als explizite Inkompatibilität, nicht als Analysefehler. B nicht als eigenes Projekt starten, sondern als Folge des Harness für `bazel run --headless` (Entscheidung 8). Diese Seite mit `onPrint`/`onExit` ist der gemeinsame Unterbau. Erst wenn sie stabil ist und ein Nutzer Web-spezifisches Verhalten absichern muss, wird ein Testtarget daraus. C bringt wenig, was ein Desktop-Test mit gesetzten Feature-Tags nicht schon kann, und hat kein Vorbild.

## Entscheidung 4: Texturformate brauchen explizite Import-Familien pro Ziel

### Hintergrund

Der Web-Exporter setzt standardmäßig `vram_texture_compression/for_desktop = true` (Tags `s3tc bptc`) und `for_mobile = false` (Tags `etc2 astc`) ([export_plugin.cpp:348-377](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/export/export_plugin.cpp#L348-L377)). Im Gegensatz zu PC-, Android- und Apple-Exportern ist sein `resolve_platform_feature_priorities` leer ([export_plugin.h:143-144](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/export/export_plugin.h#L143-L144)). **Mit beiden Optionen landen beide Familien im PCK.** Nach Standard-Bitraten (4 bzw. 8 bpp je Familie) verdoppelt das grob die VRAM-komprimierten Texturbytes. Gemessen wurde das an keinem Projekt. Zur Laufzeit nimmt Godot die erste nativ unterstützte Variante. Gibt es keine, dekomprimiert es S3TC/BPTC auf der CPU zu RGBA ([resource_importer.cpp:70-100](https://github.com/godotengine/godot/blob/4.7.2-stable/core/io/resource_importer.cpp#L70-L100)). Ein Mobile-Browser mit Desktop-Pack lädt dann länger und braucht für diese Texturen 4–8× GPU-Speicher. Auf WebGL setzt Godot `etc2_supported = true` **bedingungslos** ([config.cpp:87-113](https://github.com/godotengine/godot/blob/4.7.2-stable/drivers/gles3/storage/config.cpp#L87-L113)). Windows-Browser bieten `WEBGL_compressed_texture_etc` aber nur zu etwa 1,9 % an ([web3dsurvey etc](https://web3dsurvey.com/webgl2/extensions/WEBGL_compressed_texture_etc)). Ein reines ETC2-Pack würde dort native Uploads versuchen statt der CPU-Dekompression, was vermutlich schwarze oder kaputte Texturen ergibt. Das ist eine Folgerung, nicht verifiziert. Umgekehrt bieten Android-Browser S3TC nur zu ~31 % und iOS zu ~56 % an ([web3dsurvey s3tc](https://web3dsurvey.com/webgl2/extensions/WEBGL_compressed_texture_s3tc)). Die Stichprobe der Umfrage ist undatiert und eher Desktop-lastig.

Für Bazel kommt der Querschnittsbefund hinzu. Ohne explizite Einstellungen bestimmt die Host-CPU die Familien. Für `for_desktop` ohne S3TC-Import meldet der Web-Exporter nichts, und `for_mobile` ohne ETC2-Import wird in 4.7.2 ohne Meldung ungültig ([export_plugin.cpp:466-479](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/export/export_plugin.cpp#L466-L479)). Erst 4.8 ergänzt eine CLI-Meldung. 2D-Texturen sind standardmäßig `Lossless` und schreiben eine einzige `.ctex`, unabhängig von den Schaltern ([resource_importer_texture.cpp:232, 949-953](https://github.com/godotengine/godot/blob/4.7.2-stable/editor/import/resource_importer_texture.cpp#L949-L953)). Die Frage betrifft daher vor allem 3D-Projekte. Basis Universal ist die Alternative „eine Datei, beim Laden transkodieren“ ([image_compress_basisu.cpp](https://github.com/godotengine/godot/blob/4.7.2-stable/modules/basis_universal/image_compress_basisu.cpp)).

### Optionen und Folgen

| Option | Folgen |
| --- | --- |
| a. Dem Projekt überlassen (Exportoption und Projekteinstellung, wie heute) | Kein neues Konzept; aber host-abhängige Imports, solange das Projekt `import_s3tc_bptc` nicht setzt; ein Projekt mit `import_etc2_astc=true` für Android zahlt ETC2-Encoding auch im Web-Import |
| b. Das Ruleset setzt die Import-Familien pro Zielplattform explizit; Web: S3TC/BPTC immer, ETC2/ASTC folgt der autorisierten Option `for_mobile` | Host-unabhängig; Imports laufen ohnehin pro Zielplattform, also keine neue Kostenklasse; erfordert Konsistenzprüfung Option ↔ Import, die Godot nicht macht |
| c. Ein Application-Attribut wie `web_mobile` leitet beides ab | Bequem; aber der erste Application-Wert, der Imports ändert. Imports hängen heute an Projekt und Zielplattform, nicht an der App, und das bräche dieses Schnittmuster |
| d. Basis Universal empfehlen | Eine Familie, keine Duplikation; Qualitäts- und Transkodierkosten; eine Projektentscheidung, kein Ruleset-Mechanismus |

### Offen und Experimente

Das ARM-Linux-Szenario sollte in einem Linux-arm64-Container auf dem Mac reproduziert werden: Import mit Standardeinstellungen, Web-Export, prüfen, welche `.ctex` im PCK landen. Lichtpost bietet sich an, um die Pack-Größe mit einer und mit beiden Familien zu messen. Offen ist auch, was ein ETC2-Upload in einem Windows-Browser ohne ETC-Extension tatsächlich tut.

### Vorschlag

**Vorschlag (keine Entscheidung):** Option b. Das Ruleset leitet `import_s3tc_bptc`/`import_etc2_astc` pro Zielplattform ab und hebt damit die Host-Abhängigkeit auch für Desktop, Android und iOS auf. Für Web gilt S3TC/BPTC immer. ETC2/ASTC kommt nur, wenn die autorisierte Exportoption `for_mobile` es verlangt. Ein Analysefehler greift, wenn `for_mobile` ohne passende Import-Familie gesetzt ist oder ein Web-Pack ohne S3TC/BPTC entstünde. Ein `web_mobile`-Attribut erst einführen, wenn ein Nutzer es braucht.

## Entscheidung 5: Die Shell ist Textersetzung plus gerenderte Bilder

### Hintergrund

Ein Standard-4.7.2-Export ohne PWA und mit `html/export_icon` (Default `true`) schreibt für die Basis `index` neun Dateien: `.html .js .wasm .audio.worklet.js .audio.position.worklet.js .pck .png .icon.png .apple-touch-icon.png`. Mit `dlink` kommen `.side.wasm` und die Extension-`.wasm`-Dateien unter eigenem Namen hinzu, mit PWA sechs weitere: Service Worker, Offline-Seite, Manifest und drei Icons ([export_plugin.cpp:522-617](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/export/export_plugin.cpp#L522-L617)). Von Projektdaten hängen nur HTML, Splash, Icons und PWA-Dateien ab. `.js`, `.wasm`, Worklets und `.side.wasm` sind reine Template-Kopien. `index.html` muss bei jeder Pack-Änderung neu entstehen, weil es die PCK-Größe enthält.

`_fix_html` baut ein Config-JSON mit zehn Schlüsseln, unter PWA mit `serviceWorker` als elftem. Es stellt Icon- und Manifest-`<link>`s vor `html/head_include` und ersetzt acht `$GODOT_*`-Platzhalter zeilenweise in Einfügereihenfolge ([export_plugin.cpp:117-193](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/export/export_plugin.cpp#L117-L193)). Splash und Projekt-Icon werden **unskaliert** aus ihren Quellbildern als PNG geschrieben. Nur das Apple-Touch-Icon (180×180) und die PWA-Icons werden bilinear skaliert. Die Quellbilder lädt Godot über den `ResourceLoader`, einschließlich SVG-Rasterung und `.import`-Dekompression ([editor_export_platform.cpp:99-119](https://github.com/godotengine/godot/blob/4.7.2-stable/editor/export/editor_export_platform.cpp#L99-L119)). Das spricht dafür, die Bilder wie bei iOS und Android im Shell-Probe zu rendern. `html/custom_html_shell`, `progressive_web_app/offline_page` und `progressive_web_app/icon_*` sind `res://`-Projektdateien. Die Custom-Shell durchläuft dieselbe Ersetzung, die Offline-Seite wird unverändert kopiert ([export_plugin.cpp:292-302, 561-575](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/export/export_plugin.cpp#L561-L575)). Laut Doku sind nur `$GODOT_URL` und `$GODOT_CONFIG` Pflicht ([Custom HTML page](https://docs.godotengine.org/en/stable/tutorials/platform/web/customizing_html5_shell.html)).

Der Prototyp weicht in folgenden Punkten von Godot ab ([package_web.py](../../../../../rules_godot/tools/platforms/package_web.py)):

- `godotPoolSize` und `emscriptenPoolSize` fehlen im Config. Godot schreibt sie immer, auch ohne Threads. Das Weglassen ist nur bei Default-Werten neutral.
- `fullsize--` muss aus `application/boot_splash/stretch_mode != Disabled` kommen, nicht aus dem in 4.7.2 nicht mehr gelesenen `…/fullsize` ([main.cpp:3932-3936](https://github.com/godotengine/godot/blob/4.7.2-stable/main/main.cpp#L3932-L3936)).
- Das Threads-Flag muss aus der Option kommen (siehe Entscheidung 1).
- Bei `html/export_icon` fügt Godot zwei `<link>`-Tags und zwei Icon-Dateien ein. Der Prototyp lehnt die Option stattdessen ab, obwohl ihr Default `true` ist.
- Pythons `round()` rundet zur geraden Zahl auf float64, Godot dagegen half-away-from-zero auf float32 ([color.cpp:112-133](https://github.com/godotengine/godot/blob/4.7.2-stable/core/math/color.cpp#L112-L133)). Exakte .5-Werte können um eins abweichen.
- Godot ersetzt zeilenweise in Einfügereihenfolge und hängt an jede Zeile `\n` an.

Die Splash-Farbe stimmt dagegen bereits. Das erzeugte `index.html` enthält `#242424`, weil der Prototyp `application/boot_splash/bg_color` aus den Facts liest. Der fest kodierte Fallback `#000000` in `_color_html` greift nur, wenn die Facts den Wert nicht tragen.

**PWA:** Der Service Worker bekommt `___GODOT_VERSION___ = unix_time|ticks_usec`, also absichtlich nicht-deterministisch, dazu zwei Cache-Listen ([export_plugin.cpp:229-290](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/export/export_plugin.cpp#L229-L290)). Ein hermetischer Build braucht einen deterministischen Ersatz, etwa einen Inhalts-Hash der gecachten Dateien. `serviceWorker` im Config löst sowohl die Registrierung als auch den COI-Reload-Pfad der Standard-Shell aus. **Isolation ohne Server-Header geht also nur mit den PWA-Dateien.**

### Optionen und Folgen

| Option | Folgen |
| --- | --- |
| a. Python füllt alles aus den Facts (Prototyp) | Konsistent mit Info.plist und Manifesten im Ruleset; Bilder müsste Python aus beliebigen `ResourceLoader`-Typen dekodieren, und das ist nicht realistisch |
| b. Godot exportiert das Web-Projekt selbst, das Ruleset übernimmt die Ausgabe | Byte-identisch per Konstruktion; bricht das Muster „Godot exportiert das Pack, das Ruleset baut das Bundle“; nicht-deterministischer Service Worker; das Template-ZIP wird Export-Input |
| c. Hybrid: der Shell-Probe rendert Splash, Icons und PWA-Icons, Python füllt HTML, Manifest und Service Worker | Wie bei iOS und Android; exakte Bilder inklusive SVG; deterministische SW-Version wählbar; Abweichungen vom Godot-Text bleiben Pflegeaufwand |

### Offen und Experimente

Prüfen, ob der Shell-Probe Defaults wie `bg_color` und `stretch_mode` auch dann aufzeichnet, wenn sie nicht in `project.godot` stehen. Unklar ist auch, in welcher Rastergröße `DefaultProjectIcon` beim headless Export entsteht. Ein Golden-Vergleich mit Godots eigenem Export desselben Projekts würde die Textersetzung festnageln. Godot 4.8 beta ändert an Exporter, Shell und Service Worker nichts, ein 4.7.2-Generator gilt also unverändert (lokaler diff 4.7.2 → 4.8 beta).

### Vorschlag

**Vorschlag (keine Entscheidung):** Option c. `html/export_icon` mit Godots Default unterstützen. Die Custom-Shell und die übrigen `res://`-Dateien über die Pack-Mitglieder auflösen, wie `application/liquid_glass_icon`. Die genannten Abweichungen schließen. PWA als Opt-in mit Inhalts-Hash als Version umsetzen, und zwar zusammen mit Threads, weil es dort für Hosts ohne Header-Kontrolle gebraucht wird.

## Entscheidung 6: `index.*` passt zu itch.io, Cloudflare Pages passt nicht

### Hintergrund

Godot benennt jede Datei nach dem HTML-Basisnamen. Die Doku empfiehlt `index.html` und warnt davor, andere Dateien umzubenennen ([Exporting for the Web](https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_web.html)). itch.io verlangt ein ZIP mit `index.html`, höchstens 1.000 Dateien, 500 MB entpackt und 200 MB pro Datei ([itch.io HTML5](https://itch.io/docs/creators/html5)). Cloudflare Pages begrenzt Assets auf **25 MiB pro Datei**, weniger als die **37,9–39,5 MB von `godot.wasm`** ([Cloudflare Pages limits](https://developers.cloudflare.com/pages/platform/limits/)). Unkomprimierte Godot-Exporte lassen sich dort also nicht direkt deployen. CrazyGames erlaubt 50 MB initialen Download, für die mobile Startseite 20 MB ([CrazyGames requirements](https://docs.crazygames.com/requirements/technical/)). GitHub Pages bietet keine eigenen Header und 1 GB pro Site ([GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)). Netlify setzt Header über eine `_headers`-Datei ([Netlify headers](https://docs.netlify.com/manage/routing/headers/)).

**Vorkomprimierung** ist Sache des Hostings, nicht des Loaders. Godot lädt die schlichten URLs `B.wasm`/`B.pck`, zählt den Fortschritt gegen unkomprimierte `fileSizes` und erzwingt selbst `application/wasm` ([preloader.js:29-105](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/js/engine/preloader.js#L29-L105)). itch.io erkennt `.br` an der Endung und gzip am Inhalt und komprimiert `wasm`/`pck` automatisch. Damit widerspricht die itch.io-Doku als Primärquelle der Godot-Doku, die behauptet, itch.io komprimiere nicht. Weil Dateinamen keine Hashes tragen, ist langes `immutable`-Caching für `index.*` unsicher.

### Optionen und Folgen

| Frage | Optionen | Folgen |
| --- | --- | --- |
| Name | `index.*` oder App-Name | `index` deployt unverändert auf itch.io und statischen Hosts; der App-Name bräuchte zusätzlich `index.html` |
| Provider | eigener `GodotWebAppInfo` oder die Desktop-Output-Groups `bundle`/`archive` wiederverwenden | Ein Provider kann Header-Anforderung (Threads), Einstiegsdatei und Verzeichnis für `bazel run`, Tests und Deploy-Rules transportieren; Output-Groups reichen, solange niemand das braucht |
| Vorkomprimierung | aus, optional `.br`/`.gz` daneben, ersetzen | Kanonisch bleiben unkomprimierte Dateien, weil der Loader nie `.br` anfragt; optional für itch.io/nginx `*_static`; hilft nicht gegen das Cloudflare-Limit pro Asset |
| Header-Datei | optional `_headers` mit COOP/COEP | Server-Gegenstück zum PWA-Workaround für Threads |

### Vorschlag

**Vorschlag (keine Entscheidung):** `index.*` beibehalten. Verzeichnis und ZIP über die vorhandenen Output-Groups liefern. Einen eigenen Provider erst einführen, wenn ein konkreter Konsument ihn braucht, etwa ein Test-Harness (3B) oder eine Deploy-Rule. Vorkomprimierung und `_headers` als spätere, optionale Ausgaben vormerken. `fileSizes` bleiben unkomprimiert.

## Entscheidung 7: Der Runtime sollte seine Dateien und Versionen beschreiben

### Hintergrund

Heute hält `GodotRuntimeInfo.executable` das Template-ZIP, so wie Godots `custom_template` ([web-prototype.md](../../../../../rules_godot/docs/internal/web-prototype.md)). Die Godot-Version steht **nicht** in `godot.js`. Sie steht als `Godot Engine v4.7.2.stable.official` samt Commit-Hash in `godot.wasm`, bei `dlink`-Templates in `godot.side.wasm` (vom Koordinator verifiziert). `godot.js` enthält dafür die **Emscripten-Version** („4.0.20“ in 4.7.2, „6.0.12“ in 4.8 beta1), genau den Wert, gegen den Extension-Side-Modules passen müssen ([library_godot_emscripten.js:35-41](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/js/libs/library_godot_emscripten.js#L35-L41)). `check_engine` läuft für Web-Runtimes noch nicht.

### Optionen und Folgen

| Option | Folgen |
| --- | --- |
| a. ZIP als `executable` behalten | Minimal; jede App entpackt 10–12 MB; Versionsprüfung müsste im ZIP lesen; für `dlink` nach Option D (Entscheidung 1) bräuchte der Runtime ohnehin ein zweites ZIP |
| b. Im Repository-Rule entpacken und die Dateien beschreiben (js, wasm, optional side.wasm, Worklets, Shell-HTML, Service Worker, Offline-Seite) | Template-Kopien werden direkt verlinkt oder kopiert und sind unabhängig vom Projekt cachebar; Godot- und Emscripten-Version werden zur Fetch-Zeit als Fakten gelesen; `nothreads` und `dlink_nothreads` passen in ein Runtime-Objekt; das Shape weicht von den Desktop-Runtimes ab |
| Versionsprüfung | Wasm nach `Godot Engine v` durchsuchen (side.wasm, falls vorhanden) oder dem gepinnten Archiv-Hash vertrauen | Der Scan ist billig und das Gegenstück zu nativen Binaries; der Hash-Pin deckt nur Profil-Fehler ab, nicht selbst gebaute Templates |

### Vorschlag

**Vorschlag (keine Entscheidung):** Option b, mit einem Web-spezifischen Runtime-Feld, das je Variante das nothreads- und das `dlink_nothreads`-Template beschreibt. Die Godot-Version aus dem (Side-)Wasm und die Emscripten-Version aus `godot.js` schon im Repository-Rule als Fakten ablegen. `check_engine` vergleicht die erste, die Extension-Toolchain-Prüfung aus Entscheidung 2 die zweite. Ob quellgebaute Templates ohne `.official` dasselbe Präfix tragen, ist noch zu prüfen.

## Entscheidung 8: `bazel run` braucht Port-Fallback, Browserwahl und später einen Harness

### Hintergrund

Godots Editor exportiert für „Run in Browser“ in ein Temp-Verzeichnis, serviert auf `localhost:8060` (Editor-Settings `export/web/http_host`, `http_port`, optional TLS mit selbstsigniertem Zertifikat) und öffnet die URL mit `shell_open` ([export_plugin.cpp:779-896](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/export/export_plugin.cpp#L779-L896)). Er sendet immer COOP/COEP, `Access-Control-Allow-Origin: *` und `Cache-Control: no-store` ([editor_http_server.cpp:104-114](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/export/editor_http_server.cpp#L104-L114)). Godots `serve.py` bindet dagegen alle Interfaces ([serve.py](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/serve.py)). Der Prototyp bindet `127.0.0.1:8060` mit COOP/COEP und `no-store`, ihm fehlt nur `Access-Control-Allow-Origin` ([launch_web.py](../../../../../rules_godot/tools/platforms/launch/launch_web.py)). Weil `localhost` ein sicherer Kontext ist, laufen threaded und PWA-Builds lokal ohne TLS. TLS bräuchte man nur für Tests vom Telefon im LAN. Die gemeinsamen Launcher-Optionen kennen bereits `--device`, `--list-devices` und `--headless` ([launch_common.py](../../../../../rules_godot/tools/platforms/launch/launch_common.py)). Remote-Debugging fügt Godot nur beim One-Click-Deploy über `--remote-debug ws://…` hinzu. Es gehört nicht ins deploybare Artefakt.

### Optionen und Folgen

Ein fester Port 8060 kollidiert bei zwei gleichzeitigen `bazel run`. Port 0 oder der nächste freie Port mit ausgegebener URL löst das, Godots 8060 bleibt als Default vertraut. `--device` kann für Web „welcher Browser“ heißen, analog zu Flutters `-d chrome`. Python-`webbrowser`-Namen eignen sich dafür. Beides stammt aus allgemeinem Wissen und nicht aus einer in dieser Recherche gelesenen Quelle. `--headless` kann nicht Godots `--headless` bedeuten (siehe Entscheidung 3). Es müsste einen gepinnten headless Browser mit Harness-Seite starten, `onPrint` als Log streamen und mit dem `onExit`-Code enden. Das ist derselbe Unterbau wie bei Test-Option B. Die Editor-Variante bleibt inkompatibel, denn Godots Web-Editor liegt außerhalb des Scopes.

### Vorschlag

**Vorschlag (keine Entscheidung):** Auf `127.0.0.1` binden, 8060 als Default mit Ausweichen auf einen freien Port und ausgegebener URL. `Access-Control-Allow-Origin: *` ergänzen und COOP/COEP immer senden. `--device` als Browserwahl und `--list-devices` als Liste der registrierten Browser. `--headless` vorerst mit klarer Fehlermeldung ablehnen und den Harness erst bauen, wenn Entscheidung 3 ihn verlangt.

## Entscheidung 9: Scope zuerst, Renderer und C# sind von upstream festgelegt

### Hintergrund

Die [Capability-Matrix](../../../../../rules_godot/docs/internal/capabilities.md) führt Web-Applications als offen. Am Bedarf besteht wenig Zweifel. itch.io listet ~157.000 browserspielbare Godot-Spiele unter ~174.000 Godot-Spielen ([itch.io HTML5 made with Godot](https://itch.io/games/html5/made-with-godot), [made with Godot](https://itch.io/games/made-with-godot), Stand 2026-11-23, Tags von den Autoren gesetzt). Beim GMTK Game Jam 2026 kamen **47 % der Einreichungen aus Godot** ([Game World Observer](https://gameworldobserver.com/2026/07/29/unity-is-no-longer-the-leader-godot-has-become-the-most-popular-engine-at-gmtk-game-jam-2026)). Vorhandene CI-Prior-Art wie [godot-ci](https://github.com/abarichello/godot-ci) und [godot-export](https://github.com/firebelley/godot-export) exportiert nur Presets und deployt sie. Texturformate und COOP/COEP behandelt sie nicht. Die heutigen Ruleset-Nutzer bauen aber mobile Apps mit nativen Add-ons, und die laufen im Web erst nach Entscheidung 2.

**Renderer:** `rendering/renderer/rendering_method.web` kennt nur den Wert `gl_compatibility`, kommentiert als „a bit of a hack until we have WebGPU support“ ([main.cpp:2649](https://github.com/godotengine/godot/blob/4.7.2-stable/main/main.cpp#L2649)). Ein Forward+-Projekt exportiert und läuft, verliert aber stumm Features wie Compute, SDFGI, SSR und Decals ([Overview of renderers](https://docs.godotengine.org/en/stable/tutorials/rendering/renderers.html)). WebGPU gibt es nur in einem inoffiziellen Fork ([godotwebgpu](https://github.com/dwalter/godotwebgpu)). **C#/.NET:** Der Web-Exporter bricht in 4.7.2 und 4.8 beta mit Fehler ab ([export_plugin.cpp:425-431](https://github.com/godotengine/godot/blob/4.7.2-stable/platform/web/export/export_plugin.cpp#L425-L431)). Ein .NET-Prototyp von 2025 hat keinen Zeitplan ([Godot blog](https://godotengine.org/article/live-from-godotcon-boston-web-dotnet-prototype/)). **Debug-Symbole:** Offizielle Templates enthalten weder Name-Section noch DWARF noch Source-Map (lokaler Scan). Godots SCons kennt für Web nur eingebettetes DWARF. Emscripten bietet `-gseparate-dwarf` und `-gsource-map` ([Emscripten: Debugging](https://emscripten.org/docs/porting/Debugging.html)). Für prebuilt Runtimes gibt es daher nichts einzusammeln. **Weitere Grenzen**, die Add-on-Features treffen können: kein Low-Level-Networking, `user://` liegt in IndexedDB und ist nicht garantiert persistent, Web-Audio-Sample-Playback ohne Effekte ([Exporting for the Web](https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_web.html)). **Benennung:** rules_godot nennt das OS `web`, Bazel `emscripten`. `wasm32` kommt in `CPU_TABLE` und zu den reservierten Feature-Tags. **4.8:** Exporter, Shell und Template-Layout bleiben gleich. Neu sind Emscripten ≥ 6.0.1, kein wasm64 mehr ([godot#122538](https://github.com/godotengine/godot/pull/122538)) und `-fwasm-exceptions` für `dlink`.

### Vorschlag

**Vorschlag (keine Entscheidung):** Den Scope als Meilensteine festlegen. M1: prebuilt, nothreads, ohne Extensions, GDScript, mit Fallback-Toolchains, Texturfix, vollständiger Shell ohne PWA und `bazel run`. M2: Extensions über `dlink`-Ableitung und eine vom Consumer registrierte emsdk-Toolchain. M3, nur bei Bedarf: Threads mit PWA sowie Browser-Tests. C#-Projekte für `web` zur Analysezeit ablehnen. Für Forward+-/Mobile-Projekte eine Analysezeit-Notiz ausgeben, aber „web == Compatibility“ nicht fest verdrahten, weil ein künftiger WebGPU-Renderer die Template-Matrix ändern würde. Debug-Symbole bleiben leer, bis quellgebaute Web-Engines kommen. Dann ist `-gseparate-dwarf` das Gegenstück zu `.dSYM`.

## Nachtrag: Engine-Größe und Playable Ads

Für Playable Ads zählt jedes Megabyte. Das verschiebt die Prioritäten: Ein verkleinerter, aus dem Quellcode gebauter Engine-Build wird damit zum Kernfall. Bisher war er ein Nebenthema der Extensions. Zwei Ergänzungen in den Notizen belegen das. [minimal_engine_size.md](../research_notes/Web%20Builds%20Entscheidungsgrundlagen/minimal_engine_size.md) enthält eigene Messungen mit SCons und emsdk 4.0.20. [playable_ads.md](../research_notes/Web%20Builds%20Entscheidungsgrundlagen/playable_ads.md) sammelt die Vorgaben von zwölf Ad-Netzwerken.

**Gemessen (Godot 4.7.2, `godot.wasm` ohne Threads):**

| Build | roh | gzip | Brotli |
| --- | ---: | ---: | ---: |
| Offizielles Template | 39,5 MB | 10,1 MB | 7,1 MB |
| Minimal-Module + `disable_*`, `-Os` (L) | 23,4 MB | 5,5 MB | 3,8 MB |
| wie L, plus `disable_3d` (nur 2D) | 21,2 MB | 5,0 MB | 3,5 MB |
| wie L, `size_extra` (`-Os` + `SIZE_EXTRA`) + volle LTO + `webp` (L2, läuft Lichtpost) | 17,7 MB | 5,2 MB | 3,6 MB |
| wie L2, aber `-Oz` (O1) | 12,8 MB | 4,3 MB | 3,2 MB |
| wie L2, plus Build-Profil für Lichtpost, 233 Klassen aus (P1) | 14,2 MB | 4,2 MB | 3,0 MB |
| **Profil und `-Oz` (P2, läuft Lichtpost)** | **10,4 MB** | **3,5 MB** | **2,6 MB** |

- **Die Modul-Auswahl halbiert die Engine.** Beides deckt die Source-Recipe von rules_godot heute schon ab: die Allowlist `enabled_modules` und die `disable_*`-Schalter über `build_options`.
- **Feinschliff bringt komprimiert wenig.** `disable_3d` und `size_extra` (`-Os` + `SIZE_EXTRA`) mit voller LTO sparen nur noch einige Prozent. `-Oz` (rules_godots `size_min`) wurde für Web nicht gemessen. Was weiter schrumpfen soll, steckt im Szenen- und Renderer-Kern. Godots `build_profile` schaltet einzelne Klassen ab; seit [autoload-dev/autoload#79](https://github.com/autoload-dev/autoload/pull/79) nimmt ein Source-Recipe es als Attribut an.
- **Die Import-Einstellungen bestimmen, welche Engine-Module nötig sind.** Lichtpost lief mit L, aber ohne Hintergründe: Verlustfrei importierte Texturen werden als WebP gespeichert, und das Modul `webp` fehlte. Das fiel erst im Browser auf. Die Import-Ergebnisse sind zur Build-Zeit bekannt, also könnte das Ruleset die nötigen Decoder-Module prüfen.
- **Bauzeit:** 1–2 Minuten pro Variante auf einem Apple-Silicon-Mac. Ein Minimal-Build ist billig.

**Playable Ads (Kurzfassung der Recherche):**

- **Limits:** Fast alle Netzwerke erlauben etwa 5 MB, zählen aber Unterschiedliches. Google, TikTok/Pangle, Mintegral, Snapchat und die ZIP-Variante von Meta messen das komprimierte ZIP. AppLovin, Unity und Moloco messen die rohe HTML-Datei. Meta erlaubt für eine einzelne HTML-Datei laut Entwicklerdoku nur 2 MB.
- **Komprimierte Payload in der HTML ist etablierte Praxis.** Defold, PlayCanvas und Unity Luna machen es so. Nativ dekomprimieren Browser per `DecompressionStream` aber nur gzip und deflate. Für Brotli, xz oder zstd muss ein JS-Decoder mit in die HTML.
- **Budget mit L2 und Lichtpost:**
  - Die Engine allein kommt mit gzip auf 5,2 MB und mit Brotli auf etwa 3,6 MB.
  - Das PCK von Lichtpost hat 3,6 MB, weil die Hintergründe verlustfrei gespeichert sind.
  - Zusammen sind das etwa 7,2 MB mit Brotli. Das liegt über jedem Limit.
  - Bei Netzwerken, die die rohe HTML zählen, kostet Base64 ein weiteres Drittel.
- **Jedes Netzwerk braucht einen eigenen Adapter:**
  - MRAID mit `mraid.open()` bei AppLovin, Unity, Liftoff und Digital Turbine.
  - `FbPlayableAd.onCTAClick()` bei Meta und Moloco.
  - `ExitApi.exit()` bei Google.
  - `install()`, `gameReady()` und `gameEnd()` bei Mintegral.
- **Godot-spezifische Hürden:**
  - Der Loader holt `index.wasm` fest per `fetch`. Für eine Single-File-Ausgabe braucht er eine eigene Shell.
  - Die Audio-Worklets brauchen Blob-URLs.
  - `godot.js` enthält `XMLHttpRequest`, das der Prüfer von Moloco ablehnt, und IndexedDB, die Google untersagt.
  - Für Godot-Playables gibt es keinen bekannten Präzedenzfall.

**Folgen für die Entscheidungen:**

- **Entscheidung 2:** Ein eigener Engine-Build braucht die Emscripten-Toolchain. Ein kleiner Build ist ein statischer Main Module ohne `dlink`, braucht also keinen PIC-Sysroot. LTO würde allerdings den LTO-Sysroot brauchen.
- **Entscheidung 6:** „Single-File-HTML pro Netzwerk“ ist ein eigenes Ausgabeformat mit Adapter, Kompression und Größenprüfung. Es passt als Packaging-Schritt nach dem normalen Web-Build, so wie Needle Engine es mit Build-Profilen pro Netzwerk löst.
- **Neue Frage:** Soll rules_godot `build_profile` erlauben oder aus den genutzten Klassen eines Projekts erzeugen? Dazu gehört die Prüfung der nötigen Module aus den Import-Ergebnissen. Die Design-Prinzipien sagen bisher: „Die App bestimmt die Allowlist, Inferenz ist unzuverlässig.“ Die Prüfung über die Importe wäre keine Inferenz, sondern eine Konsistenzprüfung.

**Messung nachgeholt:** Mit dem Build-Profil aus dem iOS-Prototyp von #76 (233 Klassen aus) und `-Oz` (rules_godots `size_min`) sinkt die Engine auf 2,6 MB Brotli, 63 % unter dem offiziellen Template. Lichtpost läuft darauf. Für das Spiel bleiben damit etwa 2,3 MB bei ZIP-gezählten Netzwerken, 1,9 MB bei AppLovin mit base122 und 1,4 MB bei Unity Ads und Moloco, jeweils vor Decoder, Shell und Adapter. Details in [minimal_engine_size.md](../research_notes/Web%20Builds%20Entscheidungsgrundlagen/minimal_engine_size.md).

**Vorschlag (keine Entscheidung):** Playable Ads als eigener Meilenstein nach M1. Vorher noch eine Messung: ob eine Single-File-Shell mit Brotli-Decoder die Prüfer von AppLovin, Meta, Mintegral und Google besteht.

## Fazit

Der Prototyp zeigt, dass Web-Builds technisch in das bestehende Modell passen: Exportplattform, Runtime-Slot, Pack-Export über den Shell-Probe, Bundle in Python. Die eigentliche Arbeit steckt nicht im Bundle, sondern an zwei Stellen, die das Ruleset bisher nicht berühren musste. Erstens hängt die native ABI an einer Hosting-Eigenschaft (Threads), und die Emscripten-Version ist pro Godot-Minor fixiert. Bazels einzige Emscripten-Toolchain kennt diese Version nur als Singleton und kann noch keine Shared Libraries. Wer Threads-Constraint, Runtime-Shape und Toolchain-Validierung zusammen entwirft, vermeidet einen späteren Umbau. Wer Extensions vorerst ausklammert, kann alles Übrige mit geringem Risiko liefern.

Zweitens hat die Recherche einen Fehler außerhalb des Webs aufgedeckt. Godots Import ist ohne explizite Einstellungen nicht host-unabhängig, und sein Web-Exporter verschweigt fehlende Desktop-Texturen. Für ein Ruleset, das auf Remote Execution und reproduzierbare Imports zielt, ist das Fixieren der Import-Familien pro Zielplattform der wertvollste Einzelschritt, auch ohne Web-Support. Die nächsten Schritte sind kleine Experimente, keine großen Bauarbeiten: ARM-Linux-Import, `dlink_nothreads` mit einem Side Module, `onExit` im headless Browser und Toolchain-Vorrang. Jedes davon dauert unter einer Stunde und entscheidet eine der gekoppelten Fragen.
