# Google Translate Simple — ComfyUI

Minimal [ComfyUI](https://github.com/comfyanonymous/ComfyUI) custom nodes that do
**only one thing**: translate text with Google Translate.

No JavaScript, no server routes, no frontend hooks, no extra dependencies.

---

## Why this pack exists

The popular `ComfyUI_Custom_Nodes_AlekPet` pack bundles a lot of frontend
JavaScript (painter, pose, IDE, enhanced previews...). One of its extensions
hooks the `onExecuted` handler of image preview nodes and loads every image a
second time just to read its dimensions — which slows down (and sometimes
breaks) the way images appear on Preview/Save nodes.

This pack deliberately contains **zero JavaScript**, so it cannot interfere with
the ComfyUI UI. It ships one small Python module.

## Nodes

| Node | Inputs | Outputs | Category |
|---|---|---|---|
| **Google Translate Text** | `text`, `source_language`, `target_language` | `text` (STRING) | `Translate/Google` |
| **Google Translate CLIP Text Encode** | `text`, `source_language`, `target_language`, `clip` | `conditioning`, `text` | `Translate/Google` |

`source_language` defaults to `auto (detect language)`, so the input language is
detected automatically. **134 languages** are available.

Typical use: write your prompt in your own language, translate it to English
(or any other language the model understands better), then feed the result into
a `CLIP Text Encode` node — or use the combined *CLIP Text Encode* node directly.

## Installation

### Manual

Copy the folder into your ComfyUI custom nodes directory:

```
ComfyUI/custom_nodes/ComfyUI-GoogleTranslateSimple
```

Then restart ComfyUI. Nothing to `pip install` — only `requests`, which ComfyUI
already bundles.

### ComfyUI Manager

Search for `Google Translate Simple` in the Manager, or install it from the URL:

```
https://github.com/Verolelb/ComfyUI-GoogleTranslateSimple
```

## How it works

* Uses the free Google Translate web endpoints, with automatic failover between
  three of them in case one is unavailable or answers `429 Too Many Requests`.
* Requests are sent as `POST` (no URL-length limit), and long texts are split
  into chunks of 1800 characters, then reassembled — line breaks are preserved.
* If the `GOOGLE_TRANSLATION_API_KEY` environment variable is set, the official
  Google Cloud Translation API is used first, with a fallback to the free
  endpoint.
* If Google is unreachable, the node raises an explicit error instead of
  silently returning an empty string.

> 💡 Some networks/ISPs get a `429` from `translate.googleapis.com`. That is why
> the node automatically falls back to `clients5.google.com`, which usually
> still works.

## Repository layout

```
ComfyUI-GoogleTranslateSimple/
├── __init__.py                 # node mappings
├── simple_google_translate.py  # translation logic + nodes
├── pyproject.toml              # ComfyUI registry metadata
├── LICENSE
└── README.md
```

## License

MIT — see [LICENSE](LICENSE).

---

# 🇫🇷 Version française

Un pack de custom nodes ComfyUI minimaliste : **uniquement** de la traduction
Google. Rien d'autre.

## Pourquoi ce pack ?

Le pack `ComfyUI_Custom_Nodes_AlekPet` embarque beaucoup de JavaScript (paint,
pose, IDE, preview enrichi...). Une de ses extensions s'accroche à
`onExecuted` des nodes d'image et recharge chaque image une seconde fois pour
afficher ses dimensions — c'est ce qui provoquait un retard d'affichage des
images sur les nodes Preview/Save.

Ce pack-ci ne contient **aucun fichier JavaScript**, aucune route serveur, aucun
hook. Il ne peut donc pas interférer avec l'affichage des images.

## Nodes fournis

| Node | Entrées | Sorties | Catégorie |
|---|---|---|---|
| **Google Translate Text** | `text`, `source_language`, `target_language` | `text` (STRING) | `Translate/Google` |
| **Google Translate CLIP Text Encode** | `text`, `source_language`, `target_language`, `clip` | `conditioning`, `text` | `Translate/Google` |

`source_language` est réglé sur `auto (detect language)` par défaut : la langue
d'entrée est détectée automatiquement. **134 langues** disponibles.

## Installation

Copier le dossier dans :

```
ComfyUI/custom_nodes/ComfyUI-GoogleTranslateSimple
```

Puis redémarrer ComfyUI. Aucune dépendance à installer : le pack n'utilise que
`requests`, déjà fourni avec ComfyUI.

## Notes techniques

* Traduction via les endpoints web gratuits de Google, avec bascule automatique
  entre trois endpoints si l'un est indisponible ou renvoie une erreur 429.
* Requêtes envoyées en `POST` (pas de limite de longueur d'URL) et textes longs
  découpés par blocs de 1800 caractères puis recollés, en conservant les retours
  à la ligne.
* Si la variable d'environnement `GOOGLE_TRANSLATION_API_KEY` est définie,
  l'API officielle Google Cloud Translation est utilisée en priorité (avec repli
  sur l'endpoint gratuit).
* Si Google est injoignable, une erreur explicite est levée au lieu de renvoyer
  un texte vide en silence.
