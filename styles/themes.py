# themes.py

LIGHT_THEME = {
    "background": "#FFFFFF",
    "body": "#3B3B3B",
    "text": "#222",
    "header": "#333333",
    "button": "#E0E0E0",
    "button_text": "#000000",
    "accent": "#1976D2",
}

DARK_THEME = {
    "background": "#121212",
    "body": "#eee",
    "text": "#fff",
    "header": "#ddd",
    "button": "#1E1E1E",
    "button_text": "#FFFFFF",
    "accent": "#90CAF9",
}

# Optionally group them
THEMES = {
    "light": LIGHT_THEME,
    "dark": DARK_THEME,
}

def apply_theme(app, theme):
    qss = f"""
        .header {{
            color: {theme['header']};
        }}
        QWidget {{
            background-color: {theme['background']};
            color: {theme['text']};
        }}
        QPushButton {{
            background-color: {theme['button']};
            color: {theme['button_text']};
        }}
    """
    app.setStyleSheet(qss)
