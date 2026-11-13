"""Widgets réutilisables : jauge circulaire, boîtes de dialogue, barre de progression."""
import math

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

ACCENT = (0.21, 0.52, 0.89)
GREEN = (0.18, 0.76, 0.49)
YELLOW = (0.90, 0.65, 0.04)
RED = (0.88, 0.11, 0.14)


def level_color(percent):
    if percent < 70:
        return GREEN
    if percent < 90:
        return YELLOW
    return RED


class Gauge(Gtk.DrawingArea):
    """Jauge circulaire façon CleanMyMac : pourcentage au centre, légende dessous."""

    def __init__(self, title, size=150):
        super().__init__()
        self.title = title
        self.percent = 0.0
        self.caption = ""
        self.color = ACCENT
        self.set_content_width(size)
        self.set_content_height(size + 36)
        self.set_draw_func(self._draw, None)

    def update(self, percent, caption="", color=None):
        self.percent = max(0.0, min(100.0, percent))
        self.caption = caption
        self.color = color or level_color(self.percent)
        self.queue_draw()

    def _draw(self, area, cr, w, h, _data):
        size = min(w, h - 36)
        cx, cy, r = w / 2, size / 2 + 4, size / 2 - 10
        lw = 11
        fg = self.get_color()
        cr.set_line_width(lw)
        cr.set_line_cap(1)  # round
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.12)
        cr.arc(cx, cy, r, 0, 2 * math.pi)
        cr.stroke()
        if self.percent > 0:
            start = -math.pi / 2
            cr.set_source_rgb(*self.color)
            cr.arc(cx, cy, r, start, start + 2 * math.pi * self.percent / 100)
            cr.stroke()
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 1)
        cr.select_font_face("Sans", 0, 1)
        cr.set_font_size(r / 2.1)
        txt = f"{self.percent:.0f} %"
        ext = cr.text_extents(txt)
        cr.move_to(cx - ext.width / 2 - ext.x_bearing, cy + ext.height / 2)
        cr.show_text(txt)
        cr.select_font_face("Sans", 0, 0)
        cr.set_font_size(12)
        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.9)
        ext = cr.text_extents(self.title)
        cr.move_to(cx - ext.width / 2 - ext.x_bearing, size + 14)
        cr.show_text(self.title)
        if self.caption:
            cr.set_font_size(11)
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.6)
            ext = cr.text_extents(self.caption)
            cr.move_to(cx - ext.width / 2 - ext.x_bearing, size + 30)
            cr.show_text(self.caption)


def confirm(parent, heading, body, action_label, callback, destructive=True):
    """Boîte de dialogue de confirmation ; callback() n'est appelé que si l'action est validée."""
    dlg = Adw.AlertDialog(heading=heading, body=body)
    dlg.add_response("cancel", "Annuler")
    dlg.add_response("ok", action_label)
    if destructive:
        dlg.set_response_appearance("ok", Adw.ResponseAppearance.DESTRUCTIVE)
    else:
        dlg.set_response_appearance("ok", Adw.ResponseAppearance.SUGGESTED)
    dlg.set_default_response("cancel")
    dlg.set_close_response("cancel")

    def on_response(_d, resp):
        if resp == "ok":
            callback()
    dlg.connect("response", on_response)
    dlg.present(parent)


class ProgressRow(Gtk.Box):
    """Barre de progression indéterminée + message, affichée pendant les analyses."""

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_margin_top(6)
        self.set_margin_bottom(6)
        self.label = Gtk.Label(xalign=0)
        self.label.add_css_class("dim-label")
        self.bar = Gtk.ProgressBar()
        self.append(self.label)
        self.append(self.bar)
        self._timer = None
        self.set_visible(False)

    def start(self, msg="Analyse en cours…"):
        from gi.repository import GLib
        self.label.set_text(msg)
        self.set_visible(True)
        if not self._timer:
            self._timer = GLib.timeout_add(80, self._pulse)

    def message(self, msg):
        self.label.set_text(msg)

    def _pulse(self):
        self.bar.pulse()
        return True

    def stop(self):
        from gi.repository import GLib
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = None
        self.bar.set_fraction(0)
        self.set_visible(False)


def page_header(title, subtitle=None):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    t = Gtk.Label(label=title, xalign=0)
    t.add_css_class("title-1")
    box.append(t)
    if subtitle:
        s = Gtk.Label(label=subtitle, xalign=0, wrap=True)
        s.add_css_class("dim-label")
        box.append(s)
    box.set_margin_bottom(12)
    return box


def scrolled_clamp(child, max_width=900):
    clamp = Adw.Clamp(maximum_size=max_width, tightening_threshold=700)
    clamp.set_child(child)
    sw = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
    sw.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    sw.set_child(clamp)
    return sw


def content_box():
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
    for side in ("top", "bottom", "start", "end"):
        getattr(box, f"set_margin_{side}")(24)
    return box


def icon_button(icon, tooltip, css=None):
    b = Gtk.Button(icon_name=icon, tooltip_text=tooltip, valign=Gtk.Align.CENTER)
    if css:
        b.add_css_class(css)
    return b
