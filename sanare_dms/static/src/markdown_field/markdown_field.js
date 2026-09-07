/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onWillStart, markup } from "@odoo/owl";
import { CodeEditor } from "@web/core/code_editor/code_editor";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { useService } from "@web/core/utils/hooks";
import { useDebounced } from "@web/core/utils/timing";
import { _t } from "@web/core/l10n/translation";

export class SanareMarkdownField extends Component {
    static template = "sanare_dms.MarkdownField";
    static components = { CodeEditor };
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.state = useState({ preview: markup(""), view: "split" });
        this.renderPreview = useDebounced((text) => this._render(text), 400);
        onWillStart(() => this._render(this.value));
    }

    get value() {
        return this.props.record.data[this.props.name] || "";
    }

    async _render(text) {
        try {
            const html = await this.orm.call("sanare.document", "render_markdown_text", [
                text || "",
            ]);
            this.state.preview = markup(html);
        } catch {
            this.state.preview = markup("");
        }
    }

    onChange(value) {
        this.props.record.update({ [this.props.name]: value });
        this.renderPreview(value);
    }

    setView(view) {
        this.state.view = view;
    }
}

export const sanareMarkdownField = {
    component: SanareMarkdownField,
    displayName: _t("Markdown"),
    supportedTypes: ["text"],
};

registry.category("fields").add("sanare_markdown", sanareMarkdownField);
