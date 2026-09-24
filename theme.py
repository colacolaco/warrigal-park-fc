"""Application theme constants — every colour and label used by the web layer.

Keeping presentation constants in one module means the branding of the club
(claret and gold) is changed in exactly one place, which is the same principle
the configuration module applies to settings.
"""

THEME = {
    "club_name": "Warrigal Park FC",
    "system_name": "Member Registration & Team Roster System",
    "season": "2026",
    "brand_primary": "#7A1F2B",     # club claret
    "brand_accent": "#C8A24A",      # club gold
    "brand_dark": "#2B2B2B",
    "surface": "#FFFFFF",
    "surface_alt": "#F6F2EE",
    "border": "#D9D2C8",
    "text": "#22201E",
    "text_muted": "#6E675E",
    "success": "#2F6B45",
    "warning": "#9A6A00",
    "danger": "#A32222",
}

STATUS_LABELS = {
    "started": "Started",
    "complete": "Complete",
    "withdrawn": "Withdrawn",
}

STATUS_COLOURS = {
    "started": THEME["warning"],
    "complete": THEME["success"],
    "withdrawn": THEME["text_muted"],
}
