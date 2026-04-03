# themes.py
#
# Visual hierarchy (dark): panel_main (darkest) < panel_chrome < chrome_button ~ chrome_line
#                (light): panel_main (lightest) < panel_chrome (slightly darker) < edges/buttons
# Text/icons on a surface should read one step brighter (dark mode) / darker (light mode) than
# that surface — fine-tune icon tints in a later pass (see ui-rework/UI_Rework_Notes.md).

LIGHT_THEME = {
    # Main workspace (lightest)
    "panel_main": "#f7f7f9",
    # Top bar + sidebar (slightly darker than main)
    "panel_chrome": "#ececf0",
    # Buttons, hovers, title controls background on hover
    "chrome_button": "#e2e2e8",
    # Dividers / outer border (clearly separated from chrome)
    "chrome_line": "#c8c8d0",
    # Primary text on main panel
    "text": "#1a1a1e",
    # Text on chrome (title, menus, sidebar)
    "text_chrome": "#141418",
    # Muted / secondary
    "text_muted": "#5c5c64",
    # Window controls (− □ ×) on chrome bar — visible on panel_chrome
    "title_control": "#3a3a44",
    "title_control_hover": "#101014",
    # Inline File / Help strip (VS Code–style muted on chrome)
    "title_menu_text": "#5a5a62",
    "title_menu_hover": "#1a1a1e",
    "button_text": "#1a1a1e",
    "accent": "#1976D2",
    # Legacy keys (older scenes / fallbacks)
    "background": "#f7f7f9",
    "body": "#3B3B3B",
    "header": "#333333",
    "button": "#e2e2e8",
}

DARK_THEME = {
    "panel_main": "#0f0f10",
    # Step above panel_main (top bar + sidebar); must paint — see WA_StyledBackground on chrome widgets
    "panel_chrome": "#222226",
    "chrome_button": "#26262a",
    "chrome_line": "#38383e",
    "text": "#ececf0",
    "text_chrome": "#f4f4f8",
    "text_muted": "#9c9ca8",
    "title_control": "#c4c4d0",
    "title_control_hover": "#ffffff",
    "title_menu_text": "#9d9d9d",
    "title_menu_hover": "#ececf0",
    "button_text": "#f0f0f4",
    "accent": "#90CAF9",
    "background": "#0f0f10",
    "body": "#eee",
    "header": "#fff",
    "button": "#26262a",
}

THEMES = {
    "light": LIGHT_THEME,
    "dark": DARK_THEME,
}


def apply_theme(app, theme):
    pm = theme["panel_main"]
    pc = theme["panel_chrome"]
    cb = theme["chrome_button"]
    line = theme["chrome_line"]
    tx = theme["text"]
    tcx = theme["text_chrome"]
    tmu = theme["text_muted"]
    tctl = theme["title_control"]
    tctl_h = theme["title_control_hover"]
    tmenu = theme["title_menu_text"]
    tmenu_h = theme["title_menu_hover"]
    btxt = theme["button_text"]
    accent = theme["accent"]

    qss = f"""
        QWidget {{
            background-color: {pm};
            color: {tx};
        }}
        QLabel {{
            background-color: transparent;
            color: {tx};
        }}

        QPushButton {{
            background-color: {cb};
            color: {btxt};
            border: 1px solid {line};
            border-radius: 3px;
            padding: 4px 12px;
        }}
        QPushButton:hover {{
            border: 1px solid {accent};
        }}

        QLineEdit, QComboBox {{
            background-color: {pm};
            color: {tx};
            border: 1px solid {accent};
        }}

        QToolBar {{
            background-color: {cb};
        }}

        QWidget#WorkspaceMain,
        QStackedWidget#WorkspaceStack {{
            background-color: {pm};
        }}

        QWidget#ShellSidebar {{
            background-color: {pc};
            border: none;
            border-right: 1px solid {line};
        }}

        QWidget#SidebarToolsInner {{
            background-color: transparent;
        }}

        QWidget#AppTitleBar {{
            background-color: {pc};
        }}

        QToolButton#TitleMenuButton {{
            background-color: transparent;
            color: {tmenu};
            border: none;
            border-radius: 3px;
            padding: 8px 16px;
            font-size: 20px;
            font-weight: bold;
        }}
        QToolButton#TitleMenuButton:hover {{
            background-color: {cb};
            color: {tmenu_h};
        }}
        QToolButton#TitleMenuButton::menu-indicator {{
            image: none;
            width: 0px;
        }}

        QMenu {{
            background-color: {pc};
            color: {tcx};
            border: 1px solid {line};
        }}
        QMenu::item:selected {{
            background-color: {cb};
        }}

        QFrame#ChromeSeparator {{
            background-color: {line};
            border: none;
        }}

        QToolButton#TitleChromeButton,
        QToolButton#TitleChromeClose {{
            background-color: transparent;
            color: {tctl};
            border: none;
            border-radius: 3px;
            font-size: 26px;
            font-weight: 500;
            padding: 6px 12px;
            min-width: 50px;
            min-height: 40px;
        }}
        QToolButton#TitleChromeButton:hover {{
            background-color: {cb};
            color: {tctl_h};
        }}
        QToolButton#TitleChromeClose:hover {{
            background-color: #c42b1c;
            color: #ffffff;
        }}

        QToolButton#TitleChromeMaximize {{
            background-color: transparent;
            color: {tctl};
            border: none;
            border-radius: 3px;
            font-size: 26px;
            font-weight: 500;
            padding: 6px 12px;
            min-width: 50px;
            min-height: 40px;
        }}
        QToolButton#TitleChromeMaximize[maxGlyph="hollow"] {{
            font-size: 21px;
            font-weight: 500;
            font-family: "Segoe UI Symbol", "Segoe UI", "Arial Unicode MS", sans-serif;
        }}
        QToolButton#TitleChromeMaximize:hover {{
            background-color: {cb};
            color: {tctl_h};
        }}

        QToolButton#SidebarTool {{
            background-color: transparent;
            color: {tcx};
            border: 1px solid transparent;
            border-radius: 4px;
            padding: 6px;
        }}
        QToolButton#SidebarTool:hover {{
            background-color: {cb};
            border: 1px solid {line};
        }}
        QToolButton#SidebarTool:disabled {{
            color: {tmu};
            background-color: transparent;
            border: 1px solid transparent;
        }}

        #MainShellWindow {{
            border: 1px solid {line};
        }}

        QDialog {{
            background-color: {pm};
            color: {tx};
            border: 1px solid {line};
        }}
    """
    app.setStyleSheet(qss)
