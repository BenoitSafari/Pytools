#!/usr/bin/env python3
"""Export Claude Code local data into a portable ZIP archive."""

import argparse
import zipfile
from datetime import date
from pathlib import Path

HOME = Path.home()

SOURCES = [
    (HOME / ".claude/projects",                              "claude_code/projects"),
    (HOME / ".claude/plans",                                 "claude_code/plans"),
    (HOME / ".claude/settings.json",                         "claude_code/settings.json"),
    (HOME / ".claude/settings.local.json",                   "claude_code/settings.local.json"),
    (HOME / ".claude/history.jsonl",                         "claude_code/history.jsonl"),
    (HOME / ".claude/backups",                               "claude_code/backups"),
    (HOME / ".claude/shell-snapshots",                       "claude_code/shell-snapshots"),
    (HOME / ".claude/paste-cache",                           "claude_code/paste-cache"),
    (HOME / ".config/Claude/config.json",                    "claude_desktop/config.json"),
    (HOME / ".config/Claude/claude_desktop_config.json",     "claude_desktop/claude_desktop_config.json"),
    (HOME / ".config/Claude/logs",                           "claude_desktop/logs"),
    (HOME / "Documents/.claude/settings.local.json",        "claude_desktop/documents_settings.local.json"),
]

README_TEMPLATE = """# Claude Data Export — {date}

## Contenu de ce ZIP

### claude_code/
- `projects/`       : Historique complet de toutes les sessions Claude Code
- `plans/`          : Fichiers de planification des sessions
- `settings.json`   : Préférences Claude Code (langue, modèle, effort)
- `settings.local.json` : Permissions locales (pacman, chemins système)
- `history.jsonl`   : Historique chronologique des commandes
- `backups/`        : Sauvegardes de configuration
- `shell-snapshots/`: Snapshots de l'environnement zsh
- `paste-cache/`    : Cache presse-papiers

### claude_desktop/
- `config.json`                    : Configuration de l'appli desktop (fr-FR, thème, display)
- `claude_desktop_config.json`     : Dossiers approuvés, permissions, modes
- `logs/`                          : Logs applicatifs (main.log, ssh.log, etc.)
- `documents_settings.local.json`  : Permissions du dossier Documents

## Ce qui N'est PAS dans ce ZIP

- `.credentials.json` : tokens OAuth Anthropic + MCP (exclu pour la sécurité)
- Caches binaires (~750 Mo) : régénérables automatiquement par l'appli
- Conversations claude.ai (interface web) : stockées côté serveur Anthropic

## Export des conversations claude.ai (interface web)

Pour récupérer l'historique des conversations de l'interface web :
1. Aller sur https://privacy.anthropic.com
2. Section "Download my data" (droit RGPD/CCPA)
3. Délai : 24-72h, export envoyé par email

## Mémoires automatiques

Les mémoires auto-générées par Claude Code se trouvent dans :
  claude_code/projects/-home-benoitsafari/memory/

Ce dossier contient MEMORY.md (index) et les fichiers .md thématiques
(profil utilisateur, feedbacks, projets en cours, références externes).

## Utilisation avec une autre IA

Pour redonner le contexte à une autre IA :
1. Fournir les fichiers `memory/*.md` en priorité (profil + préférences)
2. Fournir les fichiers `plans/*.md` pour les contextes de travail récents
3. `history.jsonl` pour la chronologie des commandes exécutées
"""


def _add_path(zf: zipfile.ZipFile | None, src: Path, dest: str, dry_run: bool) -> int:
    if not src.exists():
        print(f"  [SKIP] {src}  (introuvable)")
        return 0

    count = 0
    if src.is_file():
        if not dry_run:
            zf.write(src, dest)
        count = 1
    else:
        for file in sorted(src.rglob("*")):
            if file.is_file():
                arc_name = f"{dest}/{file.relative_to(src)}"
                if not dry_run:
                    zf.write(file, arc_name)
                count += 1

    print(f"  [OK]   {src}  →  {dest}  ({count} fichier(s))")
    return count


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        prog="claude-export",
        description="Exporte les données locales Claude Code dans un ZIP portable",
    )
    parser.add_argument(
        "--output", metavar="PATH",
        help="Chemin du ZIP de sortie (défaut: ~/claude_export_YYYYMMDD.zip)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Affiche ce qui serait inclus sans créer le ZIP",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)

    today = date.today().strftime("%Y%m%d")
    output = (
        Path(args.output).expanduser()
        if args.output
        else HOME / f"claude_export_{today}.zip"
    )

    print(f"Claude Data Export — {today}")
    print(f"Destination : {output}")
    if args.dry_run:
        print("*** DRY RUN MODE ***")
    print()

    if args.dry_run:
        for src, dest in SOURCES:
            _add_path(None, src, dest, dry_run=True)
        print("\nAucun fichier créé (dry-run).")
        return 0

    total = 0
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        zf.writestr("README.md", README_TEMPLATE.format(date=today))
        for src, dest in SOURCES:
            total += _add_path(zf, src, dest, dry_run=False)

    size_mb = output.stat().st_size / 1_048_576
    print(f"\n{total} fichiers exportés → {output} ({size_mb:.1f} Mo)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
