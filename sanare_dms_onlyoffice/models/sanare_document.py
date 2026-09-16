import base64
import io
import json
import logging
import mimetypes
import os
import re
import subprocess
import tempfile
import time
import zipfile

import lxml.html

from odoo import fields, models
from odoo.exceptions import UserError

from odoo.addons.onlyoffice_odoo.controllers.controllers import onlyoffice_request
from odoo.addons.onlyoffice_odoo.utils import config_utils, file_utils, jwt_utils

_logger = logging.getLogger(__name__)

BLANK_EXT = {"docx", "xlsx", "pptx"}

OFFICE_KINDS = [
    ("docx", "Word Document"),
    ("xlsx", "Spreadsheet"),
    ("pptx", "Presentation"),
]

# ONLYOFFICE's own conversion API can turn Word into real HTML, but has no
# HTML output at all for Excel/PowerPoint (checked onlyoffice-docs-formats.
# json directly - their "convert" lists only have pdf/image/native
# formats). Those instead go through PDF, rasterized page-by-page into
# embedded images - a real preview either way, just a different mechanism.
_HTML_CONVERTIBLE_EXT = {"doc", "docx"}
_IMAGE_PREVIEW_EXT = {"xls", "xlsx", "csv", "ods", "ots", "ppt", "pptx", "odp", "otp"}


class SanareDocument(models.Model):
    _inherit = "sanare.document"

    office_kind = fields.Selection(
        OFFICE_KINDS, default="docx", string="Office Document Type",
        help="Which kind of blank file to create the first time this "
             "document is opened in ONLYOFFICE. Has no effect once a file "
             "already exists.",
    )

    def _office_ext(self):
        """The extension to use for this document's ONLYOFFICE file.

        Bug fixed here: this used to fall back to `file_extension`, which is
        computed from `file_name` (odoo/models/dms_document.py) - but that's
        always empty before the blank file is created, so every new Office
        Document silently fell through to the "docx" default regardless of
        what the user actually wanted. `file_extension` is still trusted
        first, for a document whose file was uploaded directly (not created
        blank) - only the *fallback* changes, from a hardcoded "docx" to the
        user's own office_kind choice.
        """
        self.ensure_one()
        ext = (self.file_extension or "").lower()
        if ext in BLANK_EXT:
            return ext
        return self.office_kind or "docx"

    def _ensure_office_attachment(self):
        self.ensure_one()
        if self.content_type != "onlyoffice":
            raise UserError(self.env._("This document is not an office document."))
        if self.attachment_id:
            return self.attachment_id
        ext = self._office_ext()
        try:
            data = file_utils.get_default_file_template(self.env.user.lang or "en_US", ext)
        except Exception as exc:  # noqa: BLE001 - surface any template issue to the user
            raise UserError(
                self.env._("Could not load a blank %(ext)s template: %(err)s", ext=ext, err=exc)
            )
        name = self.file_name or "%s.%s" % (self.name, ext)
        if not name.lower().endswith("." + ext):
            name = "%s.%s" % (name, ext)
        attachment = self.env["ir.attachment"].sudo().create({
            "name": name,
            "raw": data,
            "res_model": "sanare.document",
            "res_id": self.id,
            "mimetype": file_utils.get_mime_by_ext(ext),
        })
        self.with_context(dms_skip_version=True).write(
            {"attachment_id": attachment.id, "file_name": name}
        )
        self._sync_office_html()
        self._snapshot_version(
            changelog=self.env._("Blank %s document created", ext), trigger="upload"
        )
        return attachment

    def action_edit_onlyoffice(self):
        self.ensure_one()
        if not self._user_can_write():
            raise UserError(
                self.env._("You do not have edit rights on this document.")
            )
        attachment = self._ensure_office_attachment()
        return {
            "type": "ir.actions.act_url",
            "url": "/onlyoffice/editor/%s" % attachment.id,
            "target": "new",
        }

    def action_view_onlyoffice(self):
        self.ensure_one()
        if not self.attachment_id:
            raise UserError(self.env._("There is no office file to open yet."))
        return {
            "type": "ir.actions.act_url",
            "url": "/onlyoffice/editor/%s" % self.attachment_id.id,
            "target": "new",
        }

    def action_save_office_version(self):
        self.ensure_one()
        self._snapshot_version(
            changelog=self.env._("Manual version"), trigger="manual", author=self.env.user
        )
        return True

    # ==================================================================
    # Office -> HTML/image preview (for printing and embedding)
    # ==================================================================
    def action_sync_office_html(self):
        """Manual "Regenerate Preview" button - unlike _sync_office_html
        (called automatically on every save, which swallows its own
        errors so a preview problem never blocks saving the actual file),
        this one lets errors surface normally so a user retrying after a
        failure actually sees what went wrong."""
        self.ensure_one()
        if self.content_type != "onlyoffice" or not self.attachment_id:
            raise UserError(self.env._("Upload or create the office file first."))
        html = self._render_office_html()
        if html is None:
            raise UserError(
                self.env._("No print preview is available for .%s files.", self._office_ext())
            )
        self.with_context(dms_skip_version=True).write({"content_html": html})
        return True

    def _sync_office_html(self):
        """Regenerates content_html from the current attachment - called
        right before _snapshot_version (both here and in ir_attachment.py's
        write hook) so the fresh preview lands in the same version record
        as the file change it was rendered from. Best-effort: a conversion
        failure is logged, never raised - the file itself already saved
        successfully by the time this runs, and a missing preview just
        means report_document_body falls back to its old placeholder text,
        not a blocked save."""
        self.ensure_one()
        if self.content_type != "onlyoffice" or not self.attachment_id:
            return
        try:
            html = self._render_office_html()
        except Exception:  # noqa: BLE001 - never let a preview failure block a save
            _logger.exception("Office HTML preview failed for document %s", self.id)
            return
        if html is None:
            return
        self.with_context(dms_skip_version=True).write({"content_html": html})

    def _render_office_html(self):
        """Returns the HTML to store in content_html for this document's
        current file, or None if its extension has no preview support at
        all. Word converts to real HTML; Excel/PowerPoint (no HTML output
        in ONLYOFFICE's conversion API - see _IMAGE_PREVIEW_EXT) convert to
        PDF and get rendered page-by-page as embedded images instead."""
        self.ensure_one()
        ext = self._office_ext()
        if ext in _HTML_CONVERTIBLE_EXT:
            raw = self._oo_convert(ext, "html")
            return self._html_from_docx_export(raw)
        if ext in _IMAGE_PREVIEW_EXT:
            pdf_bytes = self._oo_convert(ext, "pdf")
            return self._pdf_to_page_images_html(pdf_bytes)
        return None

    def _oo_convert(self, ext, outputtype):
        """Calls the ONLYOFFICE Document Server's own /converter endpoint
        and returns the converted file's raw bytes. Same request shape as
        onlyoffice_odoo.utils.validation_utils.convert() (used there only
        to check connectivity during setup) - this is its "actually do the
        conversion and hand back the result" sibling, kept here rather
        than added to that vendored module."""
        self.ensure_one()
        env = self.env
        doc_server_url = config_utils.get_doc_server_public_url(env)
        jwt_secret = config_utils.get_jwt_secret(env)
        jwt_header = config_utils.get_jwt_header(env)
        odoo_url = config_utils.get_base_or_odoo_url(env)

        security_token = jwt_utils.encode_payload(
            env, {"id": env.uid}, config_utils.get_internal_jwt_secret(env)
        )
        if isinstance(security_token, bytes):
            security_token = security_token.decode("utf-8")
        key = str(int(time.time()))
        file_url = "%sonlyoffice/file/content/%s?oo_security_token=%s" % (
            odoo_url, self.attachment_id.id, security_token,
        )
        body = {"key": key, "url": file_url, "filetype": ext, "outputtype": outputtype}
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if jwt_secret:
            header_token = jwt_utils.encode_payload(env, {"payload": body}, jwt_secret)
            if isinstance(header_token, bytes):
                header_token = header_token.decode("utf-8")
            headers[jwt_header] = "Bearer " + header_token
            body_token = jwt_utils.encode_payload(env, dict(body), jwt_secret)
            body["token"] = body_token.decode("utf-8") if isinstance(body_token, bytes) else body_token

        result_url = None
        for _attempt in range(10):
            try:
                response = onlyoffice_request(
                    "%sconverter?shardkey=%s" % (doc_server_url, key), "post",
                    {"data": json.dumps(body), "headers": headers, "timeout": 60},
                )
            except Exception as exc:  # noqa: BLE001 - network/HTTP errors from onlyoffice_request
                raise UserError(
                    self.env._("Could not reach the ONLYOFFICE conversion service: %s", exc)
                ) from exc
            data = response.json()
            if data.get("error") is not None:
                raise UserError(
                    self.env._("ONLYOFFICE could not convert this file (error code %s).", data["error"])
                )
            if data.get("endConvert"):
                result_url = data.get("fileUrl")
                break
            time.sleep(1)
        if not result_url:
            raise UserError(self.env._("The ONLYOFFICE conversion timed out."))
        file_response = onlyoffice_request(result_url, "get", {"timeout": 60})
        return file_response.content

    def _html_from_docx_export(self, raw):
        """ONLYOFFICE's own HTML export is either a plain .html file, or -
        whenever the document has embedded images - a .zip of the HTML
        plus a media/ folder. Either way this returns one self-contained
        HTML fragment: images are inlined as base64 data URIs (an external
        reference to a doc-server temp file would go stale the moment the
        conversion job is cleaned up) and only <body>'s own content is
        kept - content_html is a fragment everywhere else in this module
        (html/knowledge_html pages have no <head> either), not a full
        document."""
        if raw[:2] == b"PK":
            zf = zipfile.ZipFile(io.BytesIO(raw))
            html_name = next(
                (n for n in zf.namelist() if n.lower().endswith((".html", ".htm"))), None
            )
            if not html_name:
                raise UserError(self.env._("ONLYOFFICE's HTML export didn't include an HTML file."))
            html = zf.read(html_name).decode("utf-8", errors="replace")
            media = {}
            for name in zf.namelist():
                if name == html_name:
                    continue
                mime, _enc = mimetypes.guess_type(name)
                if not mime or not mime.startswith("image/"):
                    continue
                data_uri = "data:%s;base64,%s" % (mime, base64.b64encode(zf.read(name)).decode())
                media[name] = data_uri
                media[os.path.basename(name)] = data_uri

            def _inline(match):
                src = match.group(1)
                return 'src="%s"' % media.get(src, media.get(os.path.basename(src), src))

            html = re.sub(r'src="([^"]+)"', _inline, html)
        else:
            html = raw.decode("utf-8", errors="replace")
        try:
            tree = lxml.html.fromstring(html)
            body = tree.find("body")
            if body is not None:
                inner = (body.text or "") + "".join(
                    lxml.html.tostring(child, encoding="unicode") for child in body
                )
                return inner
        except Exception:  # noqa: BLE001 - malformed export, fall back to the raw string
            pass
        return html

    def _pdf_to_page_images_html(self, pdf_bytes):
        """Rasterizes a PDF (already the result of an Excel/PowerPoint ->
        PDF conversion) into one PNG per page via pdftoppm (poppler-utils -
        already relied on elsewhere in this deployment for print
        verification, see project notes), embedded as base64 data URIs
        with a page-break between each so print paginates one image per
        physical page."""
        self.ensure_one()
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = os.path.join(tmp, "src.pdf")
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)
            prefix = os.path.join(tmp, "page")
            try:
                subprocess.run(
                    ["pdftoppm", "-png", "-r", "110", pdf_path, prefix],
                    check=True, capture_output=True, timeout=120,
                )
            except FileNotFoundError as exc:
                raise UserError(
                    self.env._(
                        "This server can't render Excel/PowerPoint previews - "
                        "poppler-utils (pdftoppm) isn't installed."
                    )
                ) from exc
            except subprocess.CalledProcessError as exc:
                raise UserError(
                    self.env._(
                        "Could not render a preview for this file: %s",
                        (exc.stderr or b"").decode("utf-8", errors="replace")[:300],
                    )
                ) from exc
            pages = sorted(
                f for f in os.listdir(tmp) if f.startswith("page") and f.endswith(".png")
            )
            if not pages:
                raise UserError(self.env._("No pages were rendered from this file."))
            parts = []
            for i, name in enumerate(pages):
                with open(os.path.join(tmp, name), "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                style = "max-width:100%;" + ("page-break-before:always;" if i else "")
                parts.append('<img src="data:image/png;base64,%s" style="%s"/>' % (b64, style))
            return "".join(parts)
