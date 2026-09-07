/** @odoo-module **/

import { Plugin } from "@html_editor/plugin";
import { _t } from "@web/core/l10n/translation";
import { withSequence } from "@html_editor/utils/resource";
import { closestBlock } from "@html_editor/utils/blocks";
import { fillEmpty } from "@html_editor/utils/dom";

// Gap above the separator (below the heading text) and below it (before
// whatever comes next), on the separator itself rather than the heading -
// keeps the heading element untouched so the editor's own cleanup/sanitize
// passes have nothing extra to fight with.
const SEPARATOR_STYLE = "border:none;border-top:2px solid #c0392b;margin:8px 0 24px;height:0;";

const LEVELS = [1, 2, 3];

export class SectionHeadingPlugin extends Plugin {
  static id = "sanareSectionHeading"
  static dependencies = ["dom", "selection", "history", "baseContainer"]

  resources = {
    user_commands: LEVELS.map((level) => ({
      id: `insertSanareSection${level}`,
      title: _t("Section Heading %(level)s + Separator", { level }),
      description: _t("Heading with a red separator underneath"),
      icon: "fa-header",
      run: this.insertSectionHeading.bind(this, level),
    })),
    powerbox_items: LEVELS.map((level) =>
      withSequence(15 + level, {
        categoryId: "structure",
        commandId: `insertSanareSection${level}`,
        keywords: [_t("heading"), _t("separator"), _t("section"), _t("title")],
      })
    ),
  }

  insertSectionHeading(level) {
    const tagName = `H${level}`
    this.dependencies.dom.setBlock({ tagName })

    const selection = this.dependencies.selection.getSelectionData().deepEditableSelection
    const headingEl = closestBlock(selection.startContainer)

    const hr = this.document.createElement("hr")
    hr.setAttribute("style", SEPARATOR_STYLE)
    ;(headingEl || closestBlock(selection.startContainer)).after(hr)

    const baseContainer = this.dependencies.baseContainer.createBaseContainer()
    fillEmpty(baseContainer)
    hr.after(baseContainer)
    this.dependencies.selection.setCursorStart(baseContainer)

    this.dependencies.history.addStep()
  }
}
