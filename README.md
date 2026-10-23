# Google Translate Simple — ComfyUI

Minimal [ComfyUI](https://github.com/comfyanonymous/ComfyUI) custom nodes that do
**only one thing**: translate text with Google Translate.

No heavy frontend code, no dependencies to install, no interference with the
rest of ComfyUI.

---

## Why this pack exists

The popular `ComfyUI_Custom_Nodes_AlekPet` pack bundles a lot of frontend
JavaScript (painter, pose, IDE, enhanced previews...). One of its extensions
hooks the `onExecuted` handler of image preview nodes and loads every image a
second time just to read its dimensions — which slows down (and sometimes
breaks) the way images appear on Preview/Save nodes.

This pack ships only one small frontend file, and it only adds a button to its
own two nodes. Nothing else is patched.

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

## The "Manual Translate" button and the preview box

Each node has a **Manual Translate** button at the bottom:

1. Type your text in the `text` field.
2. Pick the languages.
3. Click **Manual Translate**.

The translation is shown in the preview box below the node; **the `text` field
keeps your original text**, so you can keep it, edit it or translate again. A
toast shows which engine answered.

Under the button there is a **read-only preview box** showing the translated
text. It is filled either by the *Manual Translate* button or by the workflow
itself: every time you press *Queue Prompt*, the node shows there what it
actually sent to the next node. It is read-only, but you can still select and
copy the text from it.

The node still translates automatically on *Queue Prompt*; the button is there
to preview the translation up-front, without losing the source text.

## Prompt library

Under the node there is a small prompt manager, shared by both nodes of the
pack:

| Control | What it does |
|---|---|
| `save as` | Optional name for the save. Leave it empty to let the first line of the text be used as the name. |
| `saved prompts` | Every saved prompt, newest first. |
| **Save Prompt** | Saves the current text. Reusing an existing name updates that save instead of creating a duplicate (the toast says *Prompt updated*). |
| **Load Prompt** | Writes the selected save back into the `text` field. The translation preview is cleared, since it belonged to the previous text. |
| **Delete Prompt** | Deletes the selected save, after a confirmation. |
| **Delete All Prompts** | Deletes the whole library, after a confirmation. |

Saves are stored server-side in
`<ComfyUI>/user/google_translate_simple/prompts.json`, so they survive browser
cache clears, ComfyUI restarts and workflow reloads. Each save also remembers the
source and target languages used when it was created (they are not restored on
load, only the text is).

> 💡 Saving with an empty name never overwrites a previous save: a suffix
> ` (2)`, ` (3)`... is added automatically when the name already exists.

## Installation

### ComfyUI Manager

Search for `Google Translate Simple`, or install from the URL:

```
https://github.com/Verolelb/ComfyUI-GoogleTranslateSimple
```

### Manual

Clone into your ComfyUI custom nodes directory:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/Verolelb/ComfyUI-GoogleTranslateSimple.git
```

Then restart ComfyUI. There is nothing to `pip install`: only `requests`, which
ComfyUI already bundles.

## How it works

* **Provider chain.** Google rate-limits its free web endpoints and answers
  `429 Too Many Requests` fairly easily (this is the usual cause of translation
  failures). The node therefore tries, in order:
  1. three independent Google endpoints (using the permissive `dict-chrome-ex`
     client, which survives long after the classic `gtx` client gets blocked),
  2. [MyMemory](https://mymemory.translated.net) as a non-Google fallback,
  3. the official Google Cloud Translation API first, if
     `GOOGLE_TRANSLATION_API_KEY` is set.
  Only if *everything* fails does it raise an explicit error — it never silently
  returns an empty string.
* **Retries.** Each endpoint is retried once after a short pause. Some networks
  get a `429` from `translate.googleapis.com` but are still served by
  `clients5.google.com`, which is why several endpoints are used.
* **Caching.** Translations are cached in memory, so re-running a workflow (or
  clicking *Manual Translate* twice) does not hit the network again.
* **Long texts** are split automatically (1800 characters per request, 450 for
  MyMemory), then reassembled with line breaks preserved.

> 💡 If translation ever fails, try setting `source_language` explicitly instead
> of `auto`: it makes every provider usable, including the fallback ones.

## Repository layout

```
ComfyUI-GoogleTranslateSimple/
├── __init__.py                 # node mappings + WEB_DIRECTORY
├── simple_google_translate.py  # translation logic + nodes + server route
├── prompt_store.py             # saved prompt library + its routes
├── web/
│   └── google_translate_simple.js   # button, preview and prompt library
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

Ce pack-ci ne contient qu'un petit fichier frontend, qui ajoute uniquement un
bouton à ses deux nodes. Rien d'autre n'est modifié.

## Nodes fournis

| Node | Entrées | Sorties | Catégorie |
|---|---|---|---|
| **Google Translate Text** | `text`, `source_language`, `target_language` | `text` (STRING) | `Translate/Google` |
| **Google Translate CLIP Text Encode** | `text`, `source_language`, `target_language`, `clip` | `conditioning`, `text` | `Translate/Google` |

`source_language` est réglé sur `auto (detect language)` par défaut : la langue
d'entrée est détectée automatiquement. **134 langues** disponibles.

## Le bouton « Manual Translate » et l'encart d'aperçu

Chaque node possède un bouton **Manual Translate** en bas :

1. Tapez votre texte dans le champ `text`.
2. Choisissez les langues.
3. Cliquez sur **Manual Translate**.

La traduction s'affiche dans l'encart d'aperçu sous le node ; **le champ `text`
conserve votre texte d'origine**, que vous pouvez donc garder, modifier ou
retraduire. Une notification indique quel moteur a répondu.

Sous le bouton se trouve un **encart d'aperçu en lecture seule** qui affiche le
texte traduit. Il est rempli soit par le bouton *Manual Translate*, soit par le
workflow lui-même : à chaque *Queue Prompt*, le node y montre ce qu'il a
réellement envoyé au node suivant. Le texte n'est pas modifiable, mais il reste
sélectionnable et copiable.

Le node continue aussi de traduire automatiquement au *Queue Prompt* ; le bouton
sert à prévisualiser la traduction en amont, sans perdre le texte source.

## Bibliothèque de prompts

Sous le node se trouve un petit gestionnaire de prompts, partagé par les deux
nodes du pack :

| Contrôle | Rôle |
|---|---|
| `save as` | Nom facultatif de la sauvegarde. Laissez vide pour utiliser la première ligne du texte comme nom. |
| `saved prompts` | Toutes les sauvegardes, les plus récentes en premier. |
| **Save Prompt** | Sauvegarde le texte courant. Réutiliser un nom existant met à jour cette sauvegarde au lieu de créer un doublon (la notification indique *Prompt updated*). |
| **Load Prompt** | Réécrit la sauvegarde sélectionnée dans le champ `text`. L'aperçu de traduction est vidé, car il correspondait au texte précédent. |
| **Delete Prompt** | Supprime la sauvegarde sélectionnée, après confirmation. |
| **Delete All Prompts** | Supprime toute la bibliothèque, après confirmation. |

Les sauvegardes sont stockées côté serveur dans
`<ComfyUI>/user/google_translate_simple/prompts.json` : elles survivent donc au
vidage du cache du navigateur, aux redémarrages de ComfyUI et au rechargement des
workflows. Chaque sauvegarde retient aussi les langues source et cible utilisées
lors de sa création (seul le texte est restauré au chargement).

> 💡 Sauvegarder sans nom n'écrase jamais une sauvegarde existante : un suffixe
> ` (2)`, ` (3)`… est ajouté automatiquement si le nom est déjà pris.

## Installation

Copier le dossier dans :

```
ComfyUI/custom_nodes/ComfyUI-GoogleTranslateSimple
```

Puis redémarrer ComfyUI. Aucune dépendance à installer : le pack n'utilise que
`requests`, déjà fourni avec ComfyUI.

## Notes techniques

* **Chaîne de secours.** Google limite fortement ses endpoints web gratuits et
  renvoie facilement `429 Too Many Requests` (c'est la cause habituelle des
  échecs de traduction). Le node essaie donc, dans l'ordre :
  1. trois endpoints Google indépendants (via le client permissif
     `dict-chrome-ex`, qui résiste bien plus longtemps que le client `gtx`
     classique),
  2. [MyMemory](https://mymemory.translated.net) comme secours non-Google,
  3. l'API officielle Google Cloud Translation en premier, si
     `GOOGLE_TRANSLATION_API_KEY` est définie.
  Ce n'est que si *tout* échoue qu'une erreur explicite est levée — jamais de
  texte vide renvoyé en silence.
* **Nouvelles tentatives.** Chaque endpoint est retenté une fois après une courte
  pause. Certains réseaux reçoivent un `429` de `translate.googleapis.com` tout
  en étant servis par `clients5.google.com`, d'où l'usage de plusieurs endpoints.
* **Cache.** Les traductions sont mises en cache en mémoire : relancer un
  workflow (ou cliquer deux fois sur *Manual Translate*) ne refait pas d'appel
  réseau.
* **Textes longs** découpés automatiquement (1800 caractères par requête, 450
  pour MyMemory) puis recollés, en conservant les retours à la ligne.

> 💡 En cas d'échec, essayez de régler `source_language` explicitement au lieu de
> `auto` : tous les fournisseurs, y compris les secours, deviennent utilisables.
