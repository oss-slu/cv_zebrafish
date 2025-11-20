# themes.py

LIGHT_THEME = {
    "background": "#efefef",
    "body": "#3B3B3B",
    "text": "#222",
    "header": "#333333",
    "button": "#E0E0E0",
    "button_text": "#000000",
    "accent": "#1976D2",
}

DARK_THEME = {
    "background": "#333",
    "body": "#eee",
    "text": "#fff",
    "header": "#fff",
    "button": "#777",
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
        QWidget, QLabel {{
            background-color: {theme['background']};
            color: {theme['text']};
        }}
        QPushButton {{
            background-color: {theme['button']};
            color: {theme['button_text']};
        }}

        QLineEdit, QComboBox {{
            background-color: {theme['background']};
            color: {theme['text']};
            border: 1px solid {theme['accent']};
        }}

        QToolBar {{
            background-color: {theme['button']};
        }}
    """
    app.setStyleSheet(qss)
