/** @odoo-module **/

import { Plugin } from "@html_editor/plugin"
import { emailSendEmbedding } from "./email_send"

// Registration only. This makes the editor mount EmbeddedEmailSendComponent
// on any <div data-embedded="sanareEmailSend"> it finds in a document.
//
// There is deliberately NO "/" command to insert one: an email is a
// *template document* (is_template=True) that already contains the block,
// and you get a working copy through "New from Template" - never by
// dropping a block into an arbitrary page. The same pattern carries the
// template blocks that follow (child-article index, ...): each adds its
// embedding to this list.
export class EmailSendPlugin extends Plugin {
  static id = "sanareEmailSend"
  static dependencies = ["embeddedComponents"]

  resources = {
    embedded_components: [emailSendEmbedding],
  }
}
