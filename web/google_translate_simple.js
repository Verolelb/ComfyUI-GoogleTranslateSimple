/**
 * Simple Google Translate - frontend extension.
 *
 * Adds one "Manual Translate" button per node. It asks the backend to translate
 * the current text and writes the result directly into the node's text field.
 *
 * Deliberately tiny: it only touches the two node types of this pack and
 * overrides nothing else (no onExecuted hook, no global patching), so it cannot
 * interfere with image preview/save nodes.
 */

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const NODE_TYPES = new Set([
  "SimpleGoogleTranslateTextNode",
  "SimpleGoogleTranslateCLIPTextEncodeNode",
]);

const ROUTE = "/google_translate_simple/translate";
const BUTTON_LABEL = "Manual Translate";

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

function setWidgetValue(node, widget, value) {
  widget.value = value;

  // Multiline string widgets are backed by a real <textarea>.
  const element = widget.inputEl ?? widget.element;
  if (element && "value" in element && element.value !== value) {
    element.value = value;
  }

  try {
    widget.callback?.(value);
  } catch (error) {
    // ignore
  }

  node.setDirtyCanvas?.(true, true);
  app.canvas?.setDirty?.(true, true);
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
    node.setDirtyCanvas?.(true, true);
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

    setWidgetValue(node, textWidget, data.translated_text ?? "");

    const preview = String(data.translated_text ?? "").replace(/\s+/g, " ").slice(0, 90);
    const engine = data.provider === "cache" ? "cache" : `Google Translate (${data.provider})`;
    notify("success", "Translated with " + engine, preview);
  } catch (error) {
    notify("error", "Translation failed", String(error));
  } finally {
    if (button) {
      button.label = previousLabel ?? BUTTON_LABEL;
      node.setDirtyCanvas?.(true, true);
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

      return result;
    };
  },
});
