/** @odoo-module **/

import { registry } from "@web/core/registry"
import { HtmlField, htmlField } from "@html_editor/fields/html_field"
import { SectionHeadingPlugin } from "./section_heading_plugin"
import { EmbeddedDocRefPlugin } from "./embedded_doc_ref/embedded_doc_ref_plugin"
import { PageBreakPlugin } from "./page_break_plugin"

// Odoo's own widget="html" (html_editor's HtmlField) builds its Plugins list
// internally from MAIN_PLUGINS with no registry to hook into - the only way
// to add a custom "/" command is to extend the field and append to it here.
// See also markdown_field.js in this same directory for the sibling
// content_markdown widget.
export class SanareHtmlField extends HtmlField {
  getConfig() {
    const config = super.getConfig()
    config.Plugins = [...config.Plugins, SectionHeadingPlugin, EmbeddedDocRefPlugin, PageBreakPlugin]
    return config
  }
}

export const sanareHtmlField = { ...htmlField, component: SanareHtmlField }

registry.category("fields").add("sanare_html", sanareHtmlField)
