from odoo import http
from odoo.exceptions import AccessError, MissingError, UserError
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class SanareDmsWebsite(http.Controller):

    _PAGE_SIZE = 20

    # ------------------------------------------------------------------
    # Public website
    # ------------------------------------------------------------------
    def _public_domain(self):
        return [
            ("is_published", "=", True),
            ("state", "=", "approved"),
            ("effective_visibility", "=", "public"),
        ]

    @http.route(
        ["/documents", "/documents/page/<int:page>"],
        type="http", auth="public", website=True, sitemap=True,
    )
    def documents_index(self, page=1, search="", category=None, **kw):
        Document = request.env["sanare.document"].sudo()
        domain = self._public_domain()
        if search:
            domain += ["|", ("name", "ilike", search), ("complete_name", "ilike", search)]
        if category and str(category).isdigit():
            domain += [("category_id", "child_of", int(category))]

        total = Document.search_count(domain)
        pager = portal_pager(
            url="/documents",
            url_args={"search": search, "category": category},
            total=total,
            page=page,
            step=self._PAGE_SIZE,
        )
        documents = Document.search(
            domain, limit=self._PAGE_SIZE, offset=pager["offset"], order="write_date desc"
        )
        categories = request.env["sanare.document.category"].sudo().search(
            [("id", "in", documents.mapped("category_id").ids)]
        ) if not category else request.env["sanare.document.category"].sudo().search([])
        values = {
            "documents": documents,
            "pager": pager,
            "search": search,
            "active_category": int(category) if category and str(category).isdigit() else None,
            "categories": categories,
        }
        return request.render("sanare_dms.documents_index", values)

    @http.route(
        "/documents/<int:document_id>",
        type="http", auth="public", website=True, sitemap=True,
    )
    def documents_page(self, document_id, **kw):
        document = request.env["sanare.document"].sudo().browse(document_id).exists()
        if not document or not self._is_public(document):
            return request.not_found()
        body = None
        if document.content_type in ("html", "knowledge_html"):
            raw = document.approved_version_id.content_html or document.content_html
            # public_only=True: this route runs sudo()'d for anonymous
            # visitors, so any document this one embeds must independently
            # clear the same public/approved/published bar - see
            # _resolve_embedded_refs's docstring for why that matters.
            body = document._resolve_embedded_refs(raw, public_only=True)
        elif document.content_type == "markdown":
            src = document.approved_version_id.content_markdown or document.content_markdown
            body = document._render_markdown(src)
        return request.render(
            "sanare_dms.documents_page",
            {"document": document, "body": body},
        )

    @http.route(
        "/documents/<int:document_id>/download",
        type="http", auth="public", website=True, sitemap=False,
    )
    def documents_download(self, document_id, **kw):
        document = request.env["sanare.document"].sudo().browse(document_id).exists()
        if not document or not self._is_public(document):
            return request.not_found()
        return document._download_response(use_approved=True)

    def _is_public(self, document):
        return document._is_publicly_visible()

    # ------------------------------------------------------------------
    # Backend/portal download - any document the requesting user can
    # already view (draft or not), not just published-public ones. Runs
    # unsudo'd deliberately: normal ir.rule access applies exactly as it
    # would opening the document itself, same pattern as
    # sanare.document.get_embedded_content.
    # ------------------------------------------------------------------
    @http.route(
        "/sanare_dms/document/<int:document_id>/download",
        type="http", auth="user", sitemap=False,
    )
    def documents_download_authenticated(self, document_id, **kw):
        document = request.env["sanare.document"].browse(document_id).exists()
        if not document:
            return request.not_found()
        try:
            return document._download_response(use_approved=False)
        except (AccessError, MissingError, UserError):
            # AccessError/MissingError: no read access, or the record
            # vanished under us. UserError: folder, or a document with no
            # content yet (e.g. onlyoffice type with no file uploaded).
            # 404 either way rather than leaking which case it was.
            return request.not_found()


class SanareDmsPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if "document_count" in counters:
            can_read = request.env["sanare.document"].has_access("read")
            values["document_count"] = (
                request.env["sanare.document"].search_count(
                    [("content_type", "!=", "folder")]
                )
                if can_read
                else 0
            )
        return values

    @http.route(
        ["/my/documents", "/my/documents/page/<int:page>"],
        type="http", auth="user", website=True,
    )
    def portal_my_documents(self, page=1, **kw):
        Document = request.env["sanare.document"]
        domain = [("content_type", "!=", "folder")]
        total = Document.search_count(domain)
        pager = portal_pager(
            url="/my/documents", total=total, page=page, step=self._items_per_page
        )
        documents = Document.search(
            domain, limit=self._items_per_page, offset=pager["offset"], order="write_date desc"
        )
        return request.render(
            "sanare_dms.portal_my_documents",
            {
                "documents": documents,
                "pager": pager,
                "page_name": "documents",
                "default_url": "/my/documents",
            },
        )
