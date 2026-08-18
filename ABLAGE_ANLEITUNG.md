# Ablage der Dateien

Zielverzeichnis: `C:\Projekte\immocore\`

```
C:\Projekte\immocore\
├── .claude\
│   └── agents\
│       ├── immo-explorer.md      ← Haiku-Worker  (nur lesen)
│       ├── immo-builder.md       ← Sonnet-Worker (umsetzen)
│       └── immo-architect.md     ← Opus-Worker   (Eskalation)
└── FABLE5_ORCHESTRATOR_PROMPT_BELEG_DOKUMENT.md   ← Prompt zum Reinkopieren
```

## Schritte
1. Die drei `.md`-Dateien nach `C:\Projekte\immocore\.claude\agents\` legen.
   Ordner ggf. anlegen:
   `New-Item -ItemType Directory -Force C:\Projekte\immocore\.claude\agents`
2. Claude-Code-Session mit Modell **Fable 5** starten (bzw. neu starten), damit
   die Agenten geladen werden.
3. Sicherstellen, dass das **Agent-Tool** in den erlaubten Tools der Session
   aktiv ist (Subagenten werden darüber aufgerufen).
4. Inhalt von `FABLE5_ORCHESTRATOR_PROMPT_BELEG_DOKUMENT.md` in die Session
   einfügen. Fable startet mit Phase 0.

## Optional: feste Modellversionen
In den drei Agent-Dateien lässt sich `model: haiku|sonnet|opus` durch die
konkreten Versionen ersetzen:
- `claude-haiku-4-5-20251001`
- `claude-sonnet-5`
- `claude-opus-4-8`
