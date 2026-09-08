/** @odoo-module **/

import { Plugin } from "@html_editor/plugin"
import { _t } from "@web/core/l10n/translation"
import { renderToString } from "@web/core/utils/render"
import { parseHTML } from "@html_editor/utils/html"
import { fillEmpty } from "@html_editor/utils/dom"
import { SelectCreateDialog } from "@web/views/view_dialogs/select_create_dialog"
import { sanareDocRefEmbedding } from "./embedded_doc_ref"

export class EmbeddedDocRefPlugin extends Plugin {
  static id = "sanareEmbeddedDocRef"
  static dependencies = ["dom", "selection", "history", "embeddedComponents", "baseContainer", "dialog"]

  resources = {
    user_commands: [
      {
        id: "insertSanareDocRef",
        title: _t("Embed Document"),
        description: _t("Insert another document's content, kept live"),
        icon: "fa-link",
        run: this.openPicker.bind(this),
      },
    ],
    powerbox_items: [
      {
        categoryId: "structure",
        commandId: "insertSanareDocRef",
        keywords: [_t("embed"), _t("link"), _t("reference"), _t("include"), _t("transclude")],
      },
    ],
    // Merges additively with the base embedded_components list (file,
    // toggle block, etc.) - no need to touch or patch that list ourselves.
    embedded_components: [sanareDocRefEmbedding],
  }

  openPicker() {
    // Exclude the document currently being edited from its own picker,
    // where that's known - best-effort, not a hard requirement (embedding
    // a document into itself renders once, not recursively: the fetched
    // content is inserted as raw HTML via t-out, so it never re-hydrates
    // into a live embedded component of its own).
    const recordInfo = this.config.getRecordInfo?.()
    const domain = [["content_type", "in", ["html", "knowledge_html"]]]
    if (recordInfo?.resId) {
      domain.push(["id", "!=", recordInfo.resId])
    }

    this.dependencies.dialog.addDialog(SelectCreateDialog, {
      resModel: "sanare.document",
      title: _t("Embed a Document"),
      domain,
      multiSelect: false,
      noCreate: true,
      onSelected: (resIds) => {
        if (resIds?.length) {
          this.insertDocRef(resIds[0]);
        }
      },
    })
  }

  async insertDocRef(documentId) {
    // Look up the name once for the initial render pass (avoids a blank
    // header before the embedded component's own fetch resolves); the
    // component re-fetches everything itself on every mount regardless,
    // so a stale name here self-corrects the moment it mounts.
    let documentName = _t("Document")
    try {
      const [rec] = await this.services.orm.read("sanare.document", [documentId], ["name"])
      documentName = rec?.name || documentName
    } catch {
      // Picker already filtered to readable records; a failure here just
      // falls back to the placeholder name above.
    }

    const block = parseHTML(
      this.document,
      renderToString("sanare_dms.EmbeddedDocRefBlueprint", {
        embeddedProps: JSON.stringify({ documentId, documentName }),
      })
    )
    // parseHTML returns a DocumentFragment - it empties out (its children
    // get moved) the moment dom.insert() attaches them to the real
    // document, so grab a live reference to the host element first.
    const hostEl = block.querySelector('[data-embedded="sanareDocRef"]')
    this.dependencies.dom.insert(block)

    // Without this, a user landing right after the embed on insertion has
    // nowhere obvious to click to keep writing below the card - same fix
    // the built-in Separator command applies after its <hr>.
    const baseContainer = this.dependencies.baseContainer.createBaseContainer()
    fillEmpty(baseContainer)
    hostEl.after(baseContainer)
    this.dependencies.selection.setCursorStart(baseContainer)

    this.dependencies.history.addStep()
  }
}
