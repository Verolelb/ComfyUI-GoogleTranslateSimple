/**
 * Simple Google Translate - frontend extension.
 *
 * Adds to each node:
 *   * a "Manual Translate" button, which translates the text field without
 *     modifying it,
 *   * a read-only "translation preview" box under the node, filled either by
 *     the button or by the workflow execution,
 *   * a small prompt library: save the current text under a name, load it back
 *     later, and delete saves one by one or all at once. The original text is
 *     always kept in the text field.
 *
 * Deliberately small: it only touches the two node types of this pack and
 * overrides nothing globally (no hook on image preview/save nodes), so it
 * cannot interfere with the rest of ComfyUI.
 */

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

const NODE_TYPES = new Set([
  "SimpleGoogleTranslateTextNode",
  "SimpleGoogleTranslateCLIPTextEncodeNode",
]);

const ROUTE = "/google_translate_simple/translate";
const PROMPTS_ROUTE = "/google_translate_simple/prompts";

const BUTTON_LABEL = "Manual Translate";
const PREVIEW_NAME = "translation_preview";
const PREVIEW_PLACEHOLDER = "Translation preview...";

// Internal widget names (prefix "gt_" avoids clashing with node inputs).
const SAVE_NAME_WIDGET = "gt_save_name";
const SAVED_PROMPT_WIDGET = "gt_saved_prompt";
const NO_PROMPT = "(no saved prompt)";

function notify(severity, summary, detail) {
  try {
    if (app.extensionManager?.toast?.add) {
      app.extensionManager.toast.add({ severity, summary, detail, life: 5000 });
      return;
    }
  } catch (error) {
    // ignore, fall back to the console
  }
  if (severity === "error") {
    console.error(`[Google Translate Simple] ${summary}: ${detail}`);
  } else {
    console.log(`[Google Translate Simple] ${summary}: ${detail}`);
  }
}

function widgetByName(node, name) {
  return node?.widgets?.find((widget) => widget.name === name);
}

function redraw(node) {
  node?.setDirtyCanvas?.(true, true);
  app.graph?.setDirtyCanvas?.(true, true);
  app.canvas?.setDirty?.(true, true);
}

/** Write a value into a widget, keeping its DOM element in sync. */
function writeWidget(node, widget, value) {
  if (!widget) return;
  widget.value = value;

  const element = widget.inputEl ?? widget.element;
  if (element && "value" in element && element.value !== value) {
    element.value = value;
  }

  try {
    widget.callback?.(value);
  } catch (error) {
    // ignore
  }
  redraw(node);
}

/** Grow the node if the added widgets do not fit in its current size. */
function fitNode(node) {
  try {
    const computed = node.computeSize?.();
    if (computed && Array.isArray(computed) && node.size[1] < computed[1]) {
      node.setSize([node.size[0], computed[1]]);
    }
  } catch (error) {
    // ignore, purely cosmetic
  }
}

function addWidgetButton(node, label, handler) {
  const button = node.addWidget("button", label, null, handler.bind(node));
  if (button) button.serializeValue = () => undefined;
  return button;
}

// ---------------------------------------------------------------------------
// Translation preview
// ---------------------------------------------------------------------------

/**
 * Create the read-only preview box. Created through ComfyWidgets.STRING so it
 * looks and behaves like a native multiline text field (wrapping, scrolling,
 * text selection), but the user cannot type in it.
 */
function createPreviewWidget(node) {
  if (widgetByName(node, PREVIEW_NAME)) return;

  let created;
  try {
    created = ComfyWidgets.STRING(
      node,
      PREVIEW_NAME,
      [
        "STRING",
        {
          default: "",
          placeholder: PREVIEW_PLACEHOLDER,
          multiline: true,
        },
      ],
      app
    );
  } catch (error) {
    console.warn("[Google Translate Simple] cannot create the preview widget:", error);
    return;
  }

  const widget = created?.widget ?? created;
  const element = created?.inputEl ?? widget?.inputEl ?? widget?.element;

  if (element) {
    element.readOnly = true;
    element.spellcheck = false;
    element.style.fontStyle = "italic";
    element.style.opacity = "0.85";
    element.title = "Translation result (read-only)";
  }

  if (widget) {
    widget.label = "translation";
  }
}

function setPreview(node, text) {
  const widget = widgetByName(node, PREVIEW_NAME);
  if (!widget) return;
  writeWidget(node, widget, String(text ?? ""));
}

// ---------------------------------------------------------------------------
// Prompt library
// ---------------------------------------------------------------------------

function isTranslateNode(node) {
  return NODE_TYPES.has(node?.comfyClass ?? node?.type);
}

function translateNodes() {
  const nodes = app.graph?._nodes ?? app.graph?.nodes ?? [];
  return nodes.filter(isTranslateNode);
}

function savedPromptsOf(node) {
  if (!(node.__gtSavedPrompts instanceof Map)) {
    node.__gtSavedPrompts = new Map();
  }
  return node.__gtSavedPrompts;
}

/** One GET in flight at a time, even when several nodes load together. */
let promptsRequest = null;

function requestPrompts() {
  if (!promptsRequest) {
    promptsRequest = api
      .fetchApi(PROMPTS_ROUTE)
      .then(async (response) => {
        let data = {};
        try {
          data = await response.json();
        } catch (error) {
          // keep data = {}
        }
        if (!response.ok || data.error) {
          throw new Error(data.error || `HTTP ${response.status} ${response.statusText}`);
        }
        return Array.isArray(data.prompts) ? data.prompts : [];
      })
      .finally(() => {
        promptsRequest = null;
      });
  }
  return promptsRequest;
}

/** Fill a node's combo box with the current library, keeping its selection. */
function applyPromptList(node, prompts) {
  const combo = widgetByName(node, SAVED_PROMPT_WIDGET);
  if (!combo) return;

  savedPromptsOf(node).clear();
  for (const prompt of prompts) {
    if (prompt?.name) node.__gtSavedPrompts.set(prompt.name, prompt);
  }

  const names = prompts.map((prompt) => prompt.name).filter(Boolean);
  combo.options = combo.options ?? {};
  combo.options.values = names.length ? names : [NO_PROMPT];

  if (!names.includes(combo.value)) {
    combo.value = names[0] ?? NO_PROMPT;
  }
  redraw(node);
}

async function refreshPromptList(node, { silent = true } = {}) {
  if (!isTranslateNode(node)) return null;
  try {
    const prompts = await requestPrompts();
    applyPromptList(node, prompts);
    return prompts;
  } catch (error) {
    if (!silent) notify("error", "Saved prompts", String(error));
    return null;
  }
}

async function refreshAllPromptLists({ silent = true } = {}) {
  try {
    const prompts = await requestPrompts();
    for (const node of translateNodes()) {
      applyPromptList(node, prompts);
    }
    return prompts;
  } catch (error) {
    if (!silent) notify("error", "Saved prompts", String(error));
    return null;
  }
}

function selectSavedPrompt(node, name) {
  const combo = widgetByName(node, SAVED_PROMPT_WIDGET);
  if (!combo || !name) return;
  const values = combo.options?.values ?? [];
  if (!values.includes(name)) return;
  combo.value = name;
  try {
    combo.callback?.(name);
  } catch (error) {
    // ignore
  }
  redraw(node);
}

/** The entry currently selected in the combo box, or null. */
function selectedPrompt(node) {
  const combo = widgetByName(node, SAVED_PROMPT_WIDGET);
  const name = String(combo?.value ?? "");
  if (!name || name === NO_PROMPT) return null;
  return savedPromptsOf(node).get(name) ?? null;
}

function createSaveNameWidget(node) {
  if (widgetByName(node, SAVE_NAME_WIDGET)) return;

  let created;
  try {
    created = ComfyWidgets.STRING(
      node,
      SAVE_NAME_WIDGET,
      [
        "STRING",
        {
          default: "",
          placeholder: "Name (optional)",
          multiline: false,
        },
      ],
      app
    );
  } catch (error) {
    console.warn("[Google Translate Simple] cannot create the save name widget:", error);
    return;
  }

  const widget = created?.widget ?? created;
  const element = created?.inputEl ?? widget?.inputEl ?? widget?.element;
  if (element) {
    element.placeholder = "Name (optional)";
    element.spellcheck = false;
  }
  if (widget) widget.label = "save as";
}

function createSavedPromptWidget(node) {
  if (widgetByName(node, SAVED_PROMPT_WIDGET)) return;

  const combo = node.addWidget(
    "combo",
    SAVED_PROMPT_WIDGET,
    NO_PROMPT,
    () => {},
    { values: [NO_PROMPT] }
  );
  if (combo) {
    combo.label = "saved prompts";
    combo.serializeValue = () => undefined;
  }
}

async function savePrompt() {
  const node = this;
  const textWidget = widgetByName(node, "text");
  if (!textWidget) {
    notify("error", "Save prompt", "Text widget not found on this node.");
    return;
  }

  const text = String(textWidget.value ?? "");
  if (!text.trim()) {
    notify("warn", "Save prompt", "The text field is empty.");
    return;
  }

  const nameWidget = widgetByName(node, SAVE_NAME_WIDGET);

  try {
    const response = await api.fetchApi(PROMPTS_ROUTE, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: String(nameWidget?.value ?? ""),
        text,
        source_language: widgetByName(node, "source_language")?.value,
        target_language: widgetByName(node, "target_language")?.value,
      }),
    });

    let data = {};
    try {
      data = await response.json();
    } catch (error) {
      // keep data = {}
    }

    if (!response.ok || data.error) {
      throw new Error(data.error || `HTTP ${response.status} ${response.statusText}`);
    }

    const saved = data.prompt;
    if (nameWidget) writeWidget(node, nameWidget, "");

    await refreshAllPromptLists({ silent: false });
    selectSavedPrompt(node, saved?.name);

    notify(
      "success",
      data.created === false ? "Prompt updated" : "Prompt saved",
      saved?.name ?? ""
    );
  } catch (error) {
    notify("error", "Save prompt failed", String(error));
  }
}

function loadPrompt() {
  const node = this;
  const saved = selectedPrompt(node);
  if (!saved) {
    notify("warn", "Load prompt", "No saved prompt is selected.");
    return;
  }

  const textWidget = widgetByName(node, "text");
  if (!textWidget) {
    notify("error", "Load prompt", "Text widget not found on this node.");
    return;
  }

  writeWidget(node, textWidget, String(saved.text ?? ""));
  // The preview belonged to the previous text: clear it instead of showing a
  // stale translation.
  setPreview(node, "");
  fitNode(node);
  notify("success", "Prompt loaded", saved.name);
}

async function deletePrompt() {
  const node = this;
  const saved = selectedPrompt(node);
  if (!saved) {
    notify("warn", "Delete prompt", "No saved prompt is selected.");
    return;
  }

  if (!window.confirm(`Delete the saved prompt "${saved.name}"?`)) return;

  try {
    const response = await api.fetchApi(
      `${PROMPTS_ROUTE}/${encodeURIComponent(saved.id)}`,
      { method: "DELETE" }
    );

    let data = {};
    try {
      data = await response.json();
    } catch (error) {
      // keep data = {}
    }

    if (!response.ok || data.error) {
      throw new Error(data.error || `HTTP ${response.status} ${response.statusText}`);
    }

    await refreshAllPromptLists({ silent: false });
    notify("success", "Prompt deleted", saved.name);
  } catch (error) {
    notify("error", "Delete prompt failed", String(error));
  }
}

async function deleteAllPrompts() {
  const node = this;
  const count = savedPromptsOf(node).size;

  if (!count) {
    notify("warn", "Delete all prompts", "There is no saved prompt.");
    return;
  }

  const message =
    `Delete all ${count} saved prompt(s)?\n\n` +
    "This cannot be undone.";
  if (!window.confirm(message)) return;

  try {
    const response = await api.fetchApi(PROMPTS_ROUTE, { method: "DELETE" });

    let data = {};
    try {
      data = await response.json();
    } catch (error) {
      // keep data = {}
    }

    if (!response.ok || data.error) {
      throw new Error(data.error || `HTTP ${response.status} ${response.statusText}`);
    }

    await refreshAllPromptLists({ silent: false });
    notify("success", "All prompts deleted", String(data.deleted ?? count) + " removed");
  } catch (error) {
    notify("error", "Delete all prompts failed", String(error));
  }
}

function createPromptManager(node) {
  createSaveNameWidget(node);
  createSavedPromptWidget(node);

  addWidgetButton(node, "Save Prompt", savePrompt);
  addWidgetButton(node, "Load Prompt", loadPrompt);
  addWidgetButton(node, "Delete Prompt", deletePrompt);
  addWidgetButton(node, "Delete All Prompts", deleteAllPrompts);
}

// ---------------------------------------------------------------------------
// Manual translation
// ---------------------------------------------------------------------------

async function manualTranslate() {
  const node = this;
  const textWidget = widgetByName(node, "text");
  if (!textWidget) {
    notify("error", "Manual Translate", "Text widget not found on this node.");
    return;
  }

  const text = String(textWidget.value ?? "");
  if (!text.trim()) {
    notify("warn", "Manual Translate", "The text field is empty.");
    return;
  }

  const button = widgetByName(node, BUTTON_LABEL);
  const previousLabel = button?.label;
  if (button) {
    button.label = "Translating...";
    redraw(node);
  }

  try {
    const response = await api.fetchApi(ROUTE, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        source_language: widgetByName(node, "source_language")?.value,
        target_language: widgetByName(node, "target_language")?.value,
      }),
    });

    let data = {};
    try {
      data = await response.json();
    } catch (error) {
      // keep data = {}
    }

    if (!response.ok || data.error) {
      notify(
        "error",
        "Translation failed",
        data.error || `HTTP ${response.status} ${response.statusText}`
      );
      return;
    }

    const translated = data.translated_text ?? "";
    // Keep the user's original text untouched in the "text" field: the
    // translation is only shown in the read-only preview box below.
    setPreview(node, translated);

    const preview = String(translated).replace(/\s+/g, " ").slice(0, 90);
    const engine = data.provider === "cache" ? "cache" : `Google Translate (${data.provider})`;
    notify("success", "Translated with " + engine, preview);
  } catch (error) {
    notify("error", "Translation failed", String(error));
  } finally {
    if (button) {
      button.label = previousLabel ?? BUTTON_LABEL;
      redraw(node);
    }
  }
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------

app.registerExtension({
  name: "verolelb.GoogleTranslateSimple",

  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!NODE_TYPES.has(nodeData.name)) return;

    const onNodeCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const result = onNodeCreated?.apply(this, arguments);

      // Appended after the existing widgets on purpose: this keeps the input
      // widget indexes stable, so saved workflows keep their values.
      const button = this.addWidget(
        "button",
        BUTTON_LABEL,
        null,
        manualTranslate.bind(this)
      );
      button.serializeValue = () => undefined;

      createPreviewWidget(this);
      createPromptManager(this);
      fitNode(this);

      // DOM widgets are measured once they are mounted: run a second fit so
      // the bottom buttons are never clipped, then load the saved prompts.
      setTimeout(() => fitNode(this), 100);
      refreshPromptList(this);

      return result;
    };

    // Show what the node produced when the workflow runs.
    const onExecuted = nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted = function (message) {
      onExecuted?.apply(this, arguments);

      const payload = message?.translated_text;
      if (payload === undefined || payload === null) return;

      setPreview(this, Array.isArray(payload) ? payload.join("\n") : String(payload));
    };

    // Workflows saved before this version do not include the extra widgets in
    // the saved node size: make sure everything stays visible, and refresh the
    // prompt library in case it changed since the last session.
    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      const result = onConfigure?.apply(this, arguments);
      setTimeout(() => {
        fitNode(this);
        refreshPromptList(this);
      }, 100);
      return result;
    };
  },
});
