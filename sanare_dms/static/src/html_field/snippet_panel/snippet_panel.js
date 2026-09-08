/** @odoo-module **/

import { Component } from "@odoo/owl";
import { SNIPPET_BLOCKS } from "./snippet_blocks";

// Purely a drag SOURCE: each card stashes its block id in dataTransfer on
// dragstart. The actual insertion happens where the drop lands - in
// SanareHtmlField's own dragover/drop handlers on the editable area, via
// the editor's shared dom/selection/history APIs (this component has no
// reference to the editor at all, deliberately - it doesn't need one).
export class SnippetPanel extends Component {
  static template = "sanare_dms.SnippetPanel";
  static props = {};

  get blocks() {
    return SNIPPET_BLOCKS;
  }

  onDragStart(blockId, ev) {
    ev.dataTransfer.effectAllowed = "copy";
    ev.dataTransfer.setData("text/sanare-snippet", blockId);
  }
}
