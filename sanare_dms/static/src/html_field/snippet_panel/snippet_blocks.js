/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";

// A curated starter set, not a port of website's snippet library - adding
// one later is adding one entry here, nothing else in the panel/drag
// infrastructure needs to change. "Page Break" shares the exact marker
// page_break_plugin.js's powerbox command inserts, so a block dragged in
// from here behaves identically to one typed via "/page break".
export const SNIPPET_BLOCKS = [
  {
    id: "two_columns",
    get label() { return _t("Two Columns"); },
    icon: "fa-columns",
    html: '<div class="row"><div class="col-6"><p>Column one text.</p></div>' +
      '<div class="col-6"><p>Column two text.</p></div></div>',
  },
  {
    id: "image_text",
    get label() { return _t("Image + Text"); },
    icon: "fa-picture-o",
    html: '<div class="row align-items-center">' +
      '<div class="col-4 text-center text-muted"><i class="fa fa-picture-o fa-3x" role="img"/></div>' +
      '<div class="col-8"><p>Replace this text and add your own image.</p></div></div>',
  },
  {
    id: "callout",
    get label() { return _t("Callout Box"); },
    icon: "fa-info-circle",
    html: '<div class="alert alert-info" role="alert"><p>Callout text goes here.</p></div>',
  },
  {
    id: "quote",
    get label() { return _t("Quote"); },
    icon: "fa-quote-left",
    html: '<blockquote class="blockquote"><p>Quotation text.</p>' +
      '<footer class="blockquote-footer">Attribution</footer></blockquote>',
  },
  {
    id: "divider",
    get label() { return _t("Divider"); },
    icon: "fa-minus",
    html: "<hr/>",
  },
  {
    id: "page_break",
    get label() { return _t("Page Break"); },
    icon: "fa-scissors",
    get html() {
      return '<div class="sanare_page_break" data-oe-protected="true" contenteditable="false" ' +
        'style="page-break-before: always; border-top: 2px dashed #999; margin: 16px 0; ' +
        'padding-top: 4px; font-size: 11px; color: #999; text-transform: uppercase; ' +
        'letter-spacing: .05em; user-select: none;">' + _t("Page Break") + "</div>";
    },
  },
];
