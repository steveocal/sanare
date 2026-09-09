/** @odoo-module **/

import { registry } from "@web/core/registry"
import { HtmlField, htmlField } from "@html_editor/fields/html_field"
import { useState } from "@odoo/owl"
import { parseHTML } from "@html_editor/utils/html"
import { SectionHeadingPlugin } from "./section_heading_plugin"
import { EmbeddedDocRefPlugin } from "./embedded_doc_ref/embedded_doc_ref_plugin"
import { EmailSendPlugin } from "./email_send/email_send_plugin"
import { EmbeddedViewPlugin } from "./embedded_view/embedded_view_plugin"
import { PageBreakPlugin } from "./page_break_plugin"
import { TemplateInsertPlugin } from "./template_insert_plugin"
import { SnippetPanel } from "./snippet_panel/snippet_panel"
import { SNIPPET_BLOCKS } from "./snippet_panel/snippet_blocks"

// Odoo's own widget="html" (html_editor's HtmlField) builds its Plugins list
// internally from MAIN_PLUGINS with no registry to hook into - the only way
// to add a custom "/" command is to extend the field and append to it here.
// See also markdown_field.js in this same directory for the sibling
// content_markdown widget.
//
// The snippet drag-and-drop panel is bolted on the same way, but at the
// *field* level rather than as an editor plugin: dragging a card in from
// the panel needs to reach across from outside the editor into it, and the
// field component already holds a direct reference to the live editor
// instance (`this.editor`, set by html_editor.HtmlField itself) with its
// shared dom/selection/history APIs - the same ones a Plugin would reach
// via `this.dependencies`, just addressed as `editor.shared.<name>` instead
// (confirmed by reading editor.js: `this.shared[P.id] = exports` is exactly
// what populates `this.dependencies` inside a Plugin too).
export class SanareHtmlField extends HtmlField {
  static template = "sanare_dms.SanareHtmlField"
  static components = { ...HtmlField.components, SnippetPanel }

  setup() {
    super.setup()
    this.snippetState = useState({ showPanel: false })
  }

  getConfig() {
    const config = super.getConfig()
    config.Plugins = [
      ...config.Plugins,
      SectionHeadingPlugin, EmbeddedDocRefPlugin, EmailSendPlugin, EmbeddedViewPlugin,
      PageBreakPlugin, TemplateInsertPlugin,
    ]
    return config
  }

  toggleSnippetPanel() {
    this.snippetState.showPanel = !this.snippetState.showPanel
  }

  // Only claims the drop when the dragged item is one of our own snippet
  // cards (identified by its custom mime type) - any other drag (an image,
  // a block being moved within the editor by MoveNodePlugin's own native
  // drag-and-drop, a browser file drop) passes through untouched.
  onDragOver(ev) {
    if (ev.dataTransfer && ev.dataTransfer.types.includes("text/sanare-snippet")) {
      ev.preventDefault()
      ev.dataTransfer.dropEffect = "copy"
    }
  }

  onDrop(ev) {
    if (!this.editor || !ev.dataTransfer) {
      return
    }
    const blockId = ev.dataTransfer.getData("text/sanare-snippet")
    const block = SNIPPET_BLOCKS.find((b) => b.id === blockId)
    if (!block) {
      return
    }
    ev.preventDefault()

    // editor.document is the editable's own ownerDocument (set by the
    // editor itself, not necessarily the outer `document`) - using it
    // rather than the global keeps this correct regardless of how the
    // editable is hosted.
    const doc = this.editor.document
    let range = null
    if (doc.caretRangeFromPoint) {
      range = doc.caretRangeFromPoint(ev.clientX, ev.clientY)
    } else if (doc.caretPositionFromPoint) {
      const pos = doc.caretPositionFromPoint(ev.clientX, ev.clientY)
      if (pos) {
        range = doc.createRange()
        range.setStart(pos.offsetNode, pos.offset)
      }
    }
    if (!range) {
      return
    }
    // dom.insert() (used below, same as every other plugin in this module)
    // always inserts at the *current selection* - it has no notion of "drop
    // position" itself, so the drop point has to become the selection
    // first. setSelection is the editor's own public API for that (same
    // shared-plugin-API pattern as dom/history below).
    this.editor.shared.selection.setSelection({
      anchorNode: range.startContainer,
      anchorOffset: range.startOffset,
    })

    const fragment = parseHTML(doc, block.html)
    this.editor.shared.dom.insert(fragment)
    this.editor.shared.history.addStep()
  }
}

export const sanareHtmlField = { ...htmlField, component: SanareHtmlField }

registry.category("fields").add("sanare_html", sanareHtmlField)
