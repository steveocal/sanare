/** @odoo-module **/

import { Plugin } from "@html_editor/plugin"
import { emailSendEmbedding } from "./email_send"

// Registration only: makes the editor mount EmbeddedEmailSendComponent on
// any <div data-embedded="sanareEmailSend"> in a document. There is no "/"
// command - the block only ever exists inside a template document
// (is_template=True) and reaches a working document through "New from
// Template". The same pattern carries the template blocks that follow.
export class EmailSendPlugin extends Plugin {
  static id = "sanareEmailSend"
  static dependencies = ["embeddedComponents"]

  resources = {
    embedded_components: [emailSendEmbedding],
  }
}
