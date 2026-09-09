/** @odoo-module **/

import { Plugin } from "@html_editor/plugin"
import { embeddedViewEmbedding } from "./embedded_view"

// Registration only: mounts EmbeddedViewComponent on any
// <div data-embedded="sanareView"> in a document. No "/" command - the
// block is created solely by the "Save as View Template" cog-menu action
// (static/src/view_to_template/), then reused via New from Template.
export class EmbeddedViewPlugin extends Plugin {
  static id = "sanareEmbeddedView"
  static dependencies = ["embeddedComponents"]

  resources = {
    embedded_components: [embeddedViewEmbedding],
  }
}
