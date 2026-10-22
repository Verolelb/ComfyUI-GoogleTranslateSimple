/**
 * Simple Google Translate - frontend extension.
 *
 * Adds to each node:
 *   * a "Manual Translate" button, which translates the text field without
 *     modifying it,
 *   * a read-only "translation preview" box under the node, filled either by
 *     the button or by the workflow execution. The original text is always
 *     kept in the text field.
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
const BUTTON_LABEL = "Manual Translate";
const PREVIEW_NAME = "translation_preview";
const PREVIEW_PLACEHOLDER = "Translation preview...";

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
      fitNode(this);

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

    // Workflows saved before this version do not include the preview box in
    // the saved node size: make sure it stays visible.
    const onConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      const result = onConfigure?.apply(this, arguments);
      setTimeout(() => fitNode(this), 0);
      return result;
    };
  },
});
