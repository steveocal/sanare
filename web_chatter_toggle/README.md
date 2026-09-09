# Web Chatter Toggle

Collapse / expand the chatter on any form view.

## What it does

- Adds a small `»` handle to the left of the chatter top bar on every form view.
- Click it: the chatter collapses to a thin strip, only the handle stays
  visible (now a `comments` icon), and the form sheet reclaims the space.
- Click again: the chatter comes back.
- The state is saved in the browser's `localStorage`, keyed by model
  (`web_chatter_toggle:<model>`), so each model remembers its own preference
  and it survives page reloads. It is per-browser, not stored on the server.

## How it works

Pure frontend. `chatter_toggle.js` patches the `mail` **Chatter** component to
carry a reactive `hidden` flag; `chatter_toggle.xml` adds the button to the
existing `.o-mail-Chatter-topbar`; `chatter_toggle.scss` does the collapsing
via a `:has([data-chatter-hidden="true"])` rule, so no Chatter markup outside
the top bar is touched.

## Version notes

Written for **Odoo 19**. The only version-sensitive line is the Chatter import
in `chatter_toggle.js`:

```js
import { Chatter } from "@mail/chatter/web/chatter";   // Odoo 19
// import { Chatter } from "@mail/core/web/chatter";   // Odoo 17 / 18
```

Everything else (`mail.Chatter` template name, `o-mail-Chatter-topbar` /
`o-mail-Form-chatter` class names) has been stable since Odoo 16.
