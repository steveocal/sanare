#!/usr/bin/env python3
"""Build the Sanare website (BioLab Holdings design clone) on sanare.systecgroup.info.

Recreates biolabholdings.com's layout/look (navy #2b5672 + orange #f98025,
Montserrat) with Sanare (SynergenGL Thailand) wound-care content.

Idempotent: pages are created once, then their backing views are updated on re-run.
"""
import os
import xmlrpc.client
import ssl

URL = "https://sanare.systecgroup.info"
DB = "gxcgtpype1.cloudpepper.site"
USER = os.environ.get("SANARE_ODOO_USER", "admin")
PW = os.environ.get("SANARE_ODOO_PASSWORD", "")
WID = 1  # website_id

if not PW:
    raise SystemExit(
        "Set SANARE_ODOO_PASSWORD before running "
        "(e.g. `export SANARE_ODOO_PASSWORD=...`)."
    )

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
obj = xmlrpc.client.ServerProxy(f"{URL}/xmlrpc/2/object", context=ctx)


def call(model, method, *args):
    return obj.execute_kw(DB, 2, PW, model, method, *args)


# ---------------------------------------------------------------- design tokens
CSS = """
@import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;500;600;700');
.sanare{font-family:'Montserrat','Segoe UI',Arial,sans-serif;color:#5a5a5a;line-height:1.65;}
.sanare *{box-sizing:border-box;}
.sanare h1,.sanare h2,.sanare h3,.sanare h4,.sanare h5,.sanare h6{font-family:'Montserrat',sans-serif;color:#2b5672;font-weight:700;line-height:1.25;margin:0 0 .5em;}
.sanare p{margin:0 0 1em;}
.sanare .wrap{max-width:1140px;margin:0 auto;padding:0 24px;}
.sanare .sec{padding:72px 0;}
.sanare .eyebrow{display:inline-block;font-size:13px;font-weight:600;letter-spacing:2px;text-transform:uppercase;color:#f98025;margin-bottom:12px;}
.sanare .btn{display:inline-block;background:#f98025;color:#fff!important;padding:13px 34px;border-radius:4px;text-decoration:none!important;font-weight:600;font-size:14px;letter-spacing:.5px;transition:background .2s;}
.sanare .btn:hover{background:#d96a10;color:#fff!important;}
.sanare .btn-outline{background:transparent;border:2px solid #fff;color:#fff!important;}
.sanare .btn-outline:hover{background:#fff;color:#2b5672!important;}
.sanare-hero{position:relative;display:flex;align-items:center;min-height:78vh;text-align:center;background:linear-gradient(135deg,#1c3a4f 0%,#2b5672 55%,#3859a8 100%);color:#fff;overflow:hidden;}
.sanare-hero .inner{max-width:900px;margin:0 auto;padding:90px 24px;position:relative;z-index:2;}
.sanare-hero h1{color:#fff;font-size:clamp(28px,5vw,52px);font-weight:700;}
.sanare-hero .lead{color:#e8eef4;font-size:18px;max-width:680px;margin:0 auto 28px;}
.sanare-hero .eyebrow{color:#f8ab61;}
.sanare-hero::after{content:'';position:absolute;inset:0;background:radial-gradient(circle at 82% 18%,rgba(255,255,255,.09),transparent 52%);}
.sanare .sec-head{text-align:center;max-width:720px;margin:0 auto 48px;}
.sanare .sec-head h2{font-size:clamp(26px,4vw,40px);}
.sanare .sec-head p{color:#737373;}
.sanare-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:28px;}
.sanare-card{background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 6px 24px rgba(43,86,114,.10);text-decoration:none!important;color:inherit;display:flex;flex-direction:column;transition:transform .2s,box-shadow .2s;}
.sanare-card:hover{transform:translateY(-6px);box-shadow:0 14px 40px rgba(43,86,114,.18);}
.sanare-card .img{height:190px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;}
.sanare-card .img .wm{color:#fff;font-weight:700;font-size:26px;letter-spacing:3px;}
.sanare-card .body{padding:22px 24px 26px;}
.sanare-card h3{font-size:20px;margin-bottom:6px;}
.sanare-card .sub{color:#f98025;font-size:12px;font-weight:600;letter-spacing:1px;text-transform:uppercase;margin-bottom:8px;}
.sanare-card .txt{color:#737373;font-size:14px;}
.sanare-strip{background:#f4f7fa;text-align:center;}
.sanare-strip .logos{display:flex;flex-wrap:wrap;gap:24px 56px;align-items:center;justify-content:center;color:#9aa7b1;font-weight:700;font-size:24px;letter-spacing:2px;}
.sanare-strip .logos span{opacity:.85;}
.sanare-split{display:grid;grid-template-columns:1fr 1fr;gap:56px;align-items:center;}
.sanare-split .media{height:320px;border-radius:10px;display:flex;align-items:center;justify-content:center;color:rgba(255,255,255,.85);}
.sanare .lead-cta{text-align:center;padding:16px 0 40px;}
.sanare ul{color:#5a5a5a;padding-left:20px;}
.sanare ul li{margin-bottom:8px;}
@media(max-width:860px){.sanare-grid{grid-template-columns:1fr;}.sanare-split{grid-template-columns:1fr;}}
"""

CROSS = ('<svg width="54" height="54" viewBox="0 0 24 24" fill="none" '
         'stroke="rgba(255,255,255,0.55)" stroke-width="1.6" stroke-linecap="round">'
         '<path d="M12 3v18M3 12h18"/></svg>')


def page_arch(tname, body):
    return (f'<t t-name="{tname}">\n'
            f'    <t t-call="website.layout">\n'
            f'        <div id="wrap" class="oe_structure">\n'
            f'            <style>{CSS}</style>\n'
            f'            <div class="sanare">{body}</div>\n'
            f'        </div>\n'
            f'    </t>\n'
            f'</t>')


def homepage_arch(body):
    return (f'<t t-name="website.homepage">\n'
            f'    <t t-call="website.layout" pageName.f="homepage">\n'
            f'        <div id="wrap" class="oe_structure">\n'
            f'            <style>{CSS}</style>\n'
            f'            <div class="sanare">{body}</div>\n'
            f'        </div>\n'
            f'    </t>\n'
            f'</t>')


def ensure_page(tname, url, name, arch, meta_title="", meta_desc=""):
    pages = call("website.page", "search_read",
                 [[("url", "=", url), ("website_id", "=", WID)]],
                 {"fields": ["id", "view_id"]})
    if pages:
        pid = pages[0]["id"]
        vid = pages[0]["view_id"][0]
        call("ir.ui.view", "write", [[vid], {"arch": arch}])
        call("website.page", "write", [[pid], {
            "name": name, "is_published": True,
            "website_meta_title": meta_title, "website_meta_description": meta_desc,
        }])
        print(f"UPDATED  {url:42s} page={pid} view={vid}")
        return pid
    vid = call("ir.ui.view", "create", [{"name": tname, "type": "qweb",
                                         "arch": arch, "website_id": WID}])
    pid = call("website.page", "create", [{
        "name": name, "url": url, "website_id": WID, "is_published": True,
        "view_id": vid, "header_visible": True, "footer_visible": True,
        "website_meta_title": meta_title, "website_meta_description": meta_desc,
    }])
    print(f"CREATED  {url:42s} page={pid} view={vid}")
    return pid


# ---------------------------------------------------------------- products
PRODUCTS = [
    {
        "slug": "dhacm-amniotic-membrane-allograft",
        "name": "Amniotic Membrane Allograft (dHACM)",
        "tagline": "Dehydrated Human Amnion/Chorion Membrane",
        "wordmark": "dHACM",
        "grad": "linear-gradient(135deg,#1c3a4f,#2b5672)",
        "desc": ("A bi-layer allograft of amnion and chorion, processed to retain the native "
                 "extracellular matrix, collagen, growth factors (EGF, TGF-\u03b2, FGF) and cytokines "
                 "while removing cellular components to reduce immunogenicity. It acts as a bioactive "
                 "scaffold that stimulates cell proliferation, migration and stem-cell recruitment, "
                 "and is dehydrated for up to five years of shelf life with no refrigeration required."),
        "features": [
            "Retains native extracellular matrix, collagen, growth factors and cytokines",
            "Bioactive scaffold promoting cell proliferation, migration and stem-cell recruitment",
            "Reduced immunogenicity through removal of cellular components",
            "Up to 5-year shelf life \u2014 no refrigeration or cryopreservation",
            "Sterile, ready-to-apply dehydrated sheet",
        ],
        "applications": [
            "Chronic wounds \u2014 diabetic foot ulcers, venous leg ulcers",
            "Acute and traumatic wounds",
            "Burns",
            "Orthopaedic tissue repair",
        ],
    },
    {
        "slug": "amniotic-membrane-allograft",
        "name": "Amniotic Membrane Allograft",
        "tagline": "Single-Layer Amnion Membrane",
        "wordmark": "AMNION",
        "grad": "linear-gradient(135deg,#2b5672,#3859a8)",
        "desc": ("A single-layer amnion membrane allograft that provides a protective, bioactive "
                 "covering to support the body\u2019s natural healing process across a range of wound "
                 "applications. It delivers a hydrated, conformable scaffold while minimising "
                 "immunogenic response."),
        "features": [
            "Protective bioactive covering",
            "Conformable single-layer scaffold",
            "Reduced immunogenicity",
            "Long shelf life without refrigeration",
        ],
        "applications": [
            "Chronic wounds",
            "Acute and surgical wounds",
            "Burns",
        ],
    },
    {
        "slug": "collagen-dressings",
        "name": "Collagen Dressings",
        "tagline": "Native Collagen Wound Care",
        "wordmark": "COLLAGEN",
        "grad": "linear-gradient(135deg,#3859a8,#4e6fae)",
        "desc": ("Collagen-based dressings engineered to provide a scaffold for cell migration and "
                 "support granulation tissue formation, helping chronic and hard-to-heal wounds "
                 "progress toward closure."),
        "features": [
            "Native collagen scaffold for cell migration",
            "Supports granulation tissue formation",
            "Maintains a moist wound environment",
            "Absorbs excess exudate",
        ],
        "applications": [
            "Diabetic foot ulcers",
            "Venous and pressure ulcers",
            "Surgical wounds",
        ],
    },
    {
        "slug": "antimicrobial-dressings",
        "name": "Antimicrobial Dressings",
        "tagline": "Infection Control",
        "wordmark": "ANTIMICROBIAL",
        "grad": "linear-gradient(135deg,#2b5672,#1c3a4f)",
        "desc": ("Antimicrobial dressings that help reduce bioburden and protect against infection "
                 "in chronic and acute wounds, supporting a clean wound environment for optimal "
                 "healing."),
        "features": [
            "Reduces bioburden at the wound site",
            "Broad-spectrum antimicrobial action",
            "Maintains moist healing environment",
            "Suitable for infected and at-risk wounds",
        ],
        "applications": [
            "Infected and at-risk wounds",
            "Chronic wounds",
            "Post-surgical sites",
        ],
    },
    {
        "slug": "foam-dressings",
        "name": "Foam Dressings",
        "tagline": "Exudate Management",
        "wordmark": "FOAM",
        "grad": "linear-gradient(135deg,#4e6fae,#6b8bc4)",
        "desc": ("Highly absorbent foam dressings for the management of moderate-to-heavy exudate "
                 "while maintaining a moist wound environment and protecting the surrounding skin."),
        "features": [
            "High absorbency for moderate-to-heavy exudate",
            "Maintains moist wound environment",
            "Protects peri-wound skin from maceration",
            "Conformable and comfortable",
        ],
        "applications": [
            "Moderately-to-heavily exuding wounds",
            "Chronic and acute wounds",
            "Pressure ulcers",
        ],
    },
    {
        "slug": "hydrogels-hydrocolloids",
        "name": "Hydrogels &amp; Hydrocolloids",
        "tagline": "Moisture Balance",
        "wordmark": "HYDROGEL",
        "grad": "linear-gradient(135deg,#3859a8,#2b5672)",
        "desc": ("Hydrogels and hydrocolloids that maintain a moist wound environment, support "
                 "autolytic debridement and protect the wound bed, helping low-exuding and necrotic "
                 "wounds progress."),
        "features": [
            "Maintains moist wound environment",
            "Supports autolytic debridement",
            "Protects the wound bed",
            "Ideal for low-exuding and necrotic wounds",
        ],
        "applications": [
            "Low-exuding chronic wounds",
            "Necrotic and sloughy wounds",
            "Minor burns and abrasions",
        ],
    },
]

FEATURED_SLUGS = [
    "dhacm-amniotic-membrane-allograft",
    "amniotic-membrane-allograft",
    "collagen-dressings",
]
_featured = [p for p in PRODUCTS if p["slug"] in FEATURED_SLUGS]


def product_card(p):
    return (
        f'<a class="sanare-card" href="/products/{p["slug"]}">'
        f'<div class="img" style="background:{p["grad"]};">{CROSS}'
        f'<div class="wm">{p["wordmark"]}</div></div>'
        f'<div class="body">'
        f'<div class="sub">{p["tagline"]}</div>'
        f'<h3>{p["name"]}</h3>'
        f'</div></a>'
    )


# ---------------------------------------------------------------- homepage
home_body = f'''
<section class="sanare-hero">
  <div class="inner">
    <span class="eyebrow">Sanare · SynergenGL Thailand</span>
    <h1>Optimizing the standard of wound care through innovations grounded in science, compassion, and collaboration.</h1>
    <p class="lead">Advanced wound care biologics for healthcare providers and patients across Thailand.</p>
    <a class="btn" href="/products">Explore Our Products</a>
  </div>
</section>

<section class="sec">
  <div class="wrap">
    <div style="display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:40px;flex-wrap:wrap;gap:16px;">
      <div>
        <span class="eyebrow">Our Products</span>
        <h2 style="margin:0;">Explore Our Products</h2>
      </div>
      <a class="btn" href="/products">View All Products</a>
    </div>
    <div class="sanare-grid">
      {product_card(_featured[0])}
      {product_card(_featured[1])}
      {product_card(_featured[2])}
    </div>
  </div>
</section>

<section class="sec sanare-strip">
  <div class="wrap">
    <p style="color:#2b5672;font-weight:600;margin-bottom:24px;">Trusted by professionals worldwide</p>
    <div class="logos"><span>Surgenex</span><span>SynergenGL</span></div>
  </div>
</section>

<section class="sec">
  <div class="wrap">
    <div class="sec-head">
      <span class="eyebrow">Latest News</span>
      <h2>Check Out Our Latest News</h2>
    </div>
    <div class="sanare-card" style="max-width:640px;margin:0 auto;">
      <div class="body">
        <div class="sub">August 2026</div>
        <h3>Sanare brings dHACM amniotic membrane allografts to Thailand</h3>
        <div class="txt">Expanding the wound care toolbox with an advanced biologic option for chronic and acute wounds.</div>
      </div>
    </div>
  </div>
</section>

<section class="sec" style="background:#f4f7fa;">
  <div class="wrap sanare-split">
    <div>
      <span class="eyebrow">For Patients</span>
      <h2>Wound care can be a challenging journey</h2>
      <p>Especially when dealing with chronic wounds that resist healing. We understand the
      complexity of these conditions and are committed to supporting your recovery with
      purpose-built products designed specifically for chronic wound care needs.</p>
      <a class="btn" href="/contactus">Learn More</a>
    </div>
    <div class="media" style="background:linear-gradient(135deg,#2b5672,#3859a8);">{CROSS}</div>
  </div>
</section>

<section class="sec">
  <div class="wrap sanare-split">
    <div class="media" style="background:linear-gradient(135deg,#3859a8,#2b5672);">{CROSS}</div>
    <div>
      <span class="eyebrow">About Us</span>
      <h2>About Sanare</h2>
      <p>Sanare is the exclusive distributor of SynergenGL advanced wound care biologics in
      Thailand. We develop, source and supply breakthrough products with patient care in mind,
      supporting healthcare providers and patients with dependable supply, comprehensive support
      and proven clinical performance.</p>
      <a class="btn" href="/contactus">Contact Us</a>
    </div>
  </div>
</section>
'''

# ---------------------------------------------------------------- products index
products_index_body = f'''
<section class="sanare-hero" style="min-height:44vh;">
  <div class="inner">
    <span class="eyebrow">Sanare · SynergenGL Thailand</span>
    <h1>Our Products</h1>
    <p class="lead">Advanced wound care biologics grounded in science, compassion and collaboration.</p>
  </div>
</section>

<section class="sec">
  <div class="wrap">
    <div class="sanare-grid">
      {"".join(product_card(p) for p in PRODUCTS)}
    </div>
    <div class="lead-cta">
      <a class="btn" href="/contactus">Request a Consultation</a>
    </div>
  </div>
</section>
'''


def product_detail_body(p):
    feats = "".join(f"<li>{f}</li>" for f in p["features"])
    apps = "".join(f"<li>{a}</li>" for a in p["applications"])
    return f'''
<section class="sanare-hero" style="min-height:46vh;">
  <div class="inner">
    <span class="eyebrow">Product</span>
    <h1>{p["name"]}</h1>
    <p class="lead">{p["tagline"]}</p>
    <a class="btn btn-outline" href="/products">← All Products</a>
  </div>
</section>

<section class="sec">
  <div class="wrap">
    <div class="sanare-split">
      <div class="media" style="background:{p["grad"]};">{CROSS}<div style="margin-left:14px;color:#fff;font-weight:700;font-size:24px;letter-spacing:3px;">{p["wordmark"]}</div></div>
      <div>
        <span class="eyebrow">About this product</span>
        <h2>{p["name"]}</h2>
        <p>{p["desc"]}</p>
      </div>
    </div>
    <h3 style="margin-top:44px;">Key Features</h3>
    <ul>{feats}</ul>
    <h3 style="margin-top:28px;">Applications</h3>
    <ul>{apps}</ul>
    <div class="lead-cta" style="text-align:left;">
      <a class="btn" href="/contactus">Request a Consultation</a>
    </div>
  </div>
</section>
'''


# ---------------------------------------------------------------- run
def main():
    # homepage -> update existing view 1425 / page 4
    call("ir.ui.view", "write", [[1425], {"arch": homepage_arch(home_body)}])
    call("website.page", "write", [[4], {
        "website_meta_title": "Sanare | Advanced Wound Care | SynergenGL Thailand",
        "website_meta_description":
            "Sanare is the exclusive Thai distributor of SynergenGL advanced wound care biologics "
            "\u2014 amniotic membrane allografts (dHACM), collagen, antimicrobial and foam dressings.",
    }])
    print("UPDATED  / (homepage)  view=1425 page=4")

    # products index
    ensure_page(
        "sanare.products", "/products", "Products", page_arch("sanare.products", products_index_body),
        "Sanare Products | Advanced Wound Care", "Explore Sanare's advanced wound care product range.",
    )

    # product detail pages
    for p in PRODUCTS:
        ensure_page(
            f"sanare.product.{p['slug']}", f"/products/{p['slug']}", p["name"],
            page_arch(f"sanare.product.{p['slug']}", product_detail_body(p)),
            f"{p['name']} | Sanare", p["desc"][:150],
        )

    # website name -> Sanare
    call("website", "write", [[WID], {"name": "Sanare"}])
    print("UPDATED  website name -> Sanare")
    print("DONE")


if __name__ == "__main__":
    main()
