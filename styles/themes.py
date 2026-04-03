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
    # VerifyScene validation console (light)
    "verify_console_bg": "#f9f9f9",
    "verify_console_fg": "#1a1a1e",
    "sidebar_select_run_bg": "transparent",
    # Generate Config: neutral grey selection (readable on light panels)
    "generate_selection_bg": "#d4d4dc",
    "generate_selection_fg": "#1a1a1e",
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
    # VerifyScene validation console (dark: terminal-style)
    "verify_console_bg": "#000000",
    "verify_console_fg": "#ffffff",
    # Sidebar: make Select & Run control readable on dark chrome
    "sidebar_select_run_bg": "rgba(255, 255, 255, 0.14)",
    # Generate Config: neutral grey selection on dark panels
    "generate_selection_bg": "#4a4a54",
    "generate_selection_fg": "#f2f2f8",
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
    vcbg = theme.get("verify_console_bg", pm)
    vcfg = theme.get("verify_console_fg", tx)
    srsb = theme.get("sidebar_select_run_bg", "transparent")
    gsel_bg = theme.get("generate_selection_bg", accent)
    gsel_fg = theme.get("generate_selection_fg", "#ffffff")

    qss = f"""
        QWidget {{
            background-color: {pm};
            color: {tx};
        }}
        QLabel {{
            background-color: transparent;
            color: {tx};
        }}

        QLabel#VerifyFieldLabel {{
            font-size: 16px;
            font-weight: bold;
            color: {tmenu};
        }}
        QLabel#VerifyConsoleLabel {{
            font-size: 16px;
            font-weight: bold;
            color: {tmenu};
        }}
        QTextEdit#VerifyFeedbackBox {{
            font-family: Consolas, monospace;
            font-size: 13px;
            background-color: {vcbg};
            color: {vcfg};
            border: 1px solid {line};
        }}

        QLabel#ConfigSelectionHeader {{
            font-size: 18pt;
            font-weight: bold;
            color: {tx};
            background-color: transparent;
        }}
        QLabel#ConfigSelectionStatus {{
            color: {tx};
            background-color: transparent;
        }}
        QLabel#ConfigSelectionHint {{
            color: {tmenu};
            font-size: 14px;
            background-color: transparent;
        }}
        QTreeWidget#ConfigSelectionTree {{
            background-color: {pm};
            color: {tx};
            border: 1px solid {line};
            border-radius: 8px;
        }}
        QTreeWidget#ConfigSelectionTree::item:selected {{
            background-color: {cb};
            color: {tx};
        }}
        QTreeWidget#ConfigSelectionTree::item:hover {{
            background-color: {cb};
        }}
        QTreeWidget#ConfigSelectionTree::branch:has-children:!has-siblings:closed,
        QTreeWidget#ConfigSelectionTree::branch:closed:has-children:has-siblings,
        QTreeWidget#ConfigSelectionTree::branch:open:has-children:has-siblings,
        QTreeWidget#ConfigSelectionTree::branch:open:has-children:!has-siblings {{
            background-color: {tmenu};
            border-radius: 2px;
        }}
        QTreeWidget#ConfigSelectionTree QHeaderView::section {{
            background-color: {pc};
            color: {tx};
            padding: 6px 8px;
            border: none;
            border-bottom: 1px solid {line};
            font-weight: bold;
        }}
        QPushButton#ConfigSelectionCalcButton:disabled {{
            background-color: {pc};
            color: {tmu};
        }}
        QProgressBar#ConfigSelectionProgress {{
            border: 1px solid {line};
            border-radius: 4px;
            background-color: {pc};
            color: {tx};
            text-align: center;
            min-height: 18px;
        }}
        QProgressBar#ConfigSelectionProgress::chunk {{
            background-color: {accent};
            border-radius: 3px;
        }}

        QDialog#GenerateConfigDialog {{
            background-color: {pm};
            color: {tx};
            border: 1px solid {line};
        }}
        QWidget#GenerateConfigBody {{
            background-color: {pm};
            color: {tx};
        }}
        QDialog#GenerateConfigDialog QTextEdit {{
            font-family: Consolas, monospace;
            font-size: 13px;
            background-color: {vcbg};
            color: {vcfg};
            border: 1px solid {line};
            selection-background-color: {gsel_bg};
            selection-color: {gsel_fg};
        }}
        QDialog#GenerateConfigDialog QListWidget {{
            background-color: {pm};
            color: {tx};
            border: 1px solid {line};
        }}
        QDialog#GenerateConfigDialog QListWidget::item:selected {{
            background-color: {gsel_bg};
            color: {gsel_fg};
        }}
        QDialog#GenerateConfigDialog QListWidget::item:selected:!active {{
            background-color: {gsel_bg};
            color: {gsel_fg};
        }}
        QDialog#GenerateConfigDialog QListWidget#GenerateConfigTabList {{
            background-color: {pc};
            border: none;
            border-right: 1px solid {line};
            outline: none;
        }}
        QDialog#GenerateConfigDialog QListWidget#GenerateConfigTabList::item {{
            padding: 8px 6px;
            border: none;
        }}
        QDialog#GenerateConfigDialog QListWidget#GenerateConfigTabList::item:selected {{
            background-color: {cb};
            color: {tx};
            font-weight: bold;
        }}
        QDialog#GenerateConfigDialog QListWidget#GenerateConfigTabList::item:hover:!selected {{
            background-color: {cb};
        }}
        QDialog#GenerateConfigDialog QScrollArea {{
            background-color: transparent;
            border: none;
        }}
        QDialog#GenerateConfigDialog QGroupBox {{
            border: 1px solid {line};
            margin-top: 10px;
            padding-top: 10px;
            font-weight: bold;
            color: {tx};
        }}
        QDialog#GenerateConfigDialog QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 4px;
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
        QToolButton#SidebarTool[toolKey="select_run"] {{
            background-color: {srsb};
            border-radius: 6px;
        }}
        QToolButton#SidebarTool[toolKey="select_run"]:hover {{
            background-color: {cb};
            border: 1px solid {line};
        }}
        QToolButton#SidebarTool[toolKey="select_run"]:disabled {{
            background-color: transparent;
        }}

        #MainShellWindow {{
            border: 1px solid {line};
        }}

        QDialog {{
            background-color: {pm};
            color: {tx};
            border: 1px solid {line};
        }}

        QDialog#SessionSelectDialog {{
            background-color: {pm};
            color: {tx};
            border: 1px solid {line};
        }}

        QLabel#DialogTitleLabel {{
            background-color: transparent;
            color: {tmenu};
            font-size: 18px;
            font-weight: bold;
        }}

        QWidget#SessionSelectBody {{
            background-color: {pm};
            color: {tx};
        }}

        QDialog#SessionSelectDialog QScrollBar:vertical {{
            background-color: {pm};
            width: 10px;
            margin: 0px;
            border: none;
        }}
        QDialog#SessionSelectDialog QScrollBar::handle:vertical {{
            background-color: {cb};
            border-radius: 4px;
            margin: 2px;
        }}
        QDialog#SessionSelectDialog QScrollBar::handle:vertical:hover {{
            background-color: {line};
        }}
        QDialog#SessionSelectDialog QScrollBar::groove:vertical {{
            background-color: {pm};
            border: none;
        }}
        QDialog#SessionSelectDialog QScrollBar::add-line:vertical,
        QDialog#SessionSelectDialog QScrollBar::sub-line:vertical {{
            height: 0px;
            subcontrol-position: center;
            subcontrol-origin: margin;
        }}
        QDialog#SessionSelectDialog QScrollBar::add-page:vertical,
        QDialog#SessionSelectDialog QScrollBar::sub-page:vertical {{
            background: none;
        }}

        QTableWidget#SessionSelectTable {{
            background-color: {pm};
            alternate-background-color: {pm};
            color: {tx};
            gridline-color: transparent;
            outline: none;
            border: none;
        }}
        QTableWidget#SessionSelectTable::item {{
            background-color: {pm};
            color: {tx};
            border-top: none;
            border-left: none;
            border-right: none;
            border-bottom: 1px solid {line};
            padding: 4px 0px;
        }}
        QTableWidget#SessionSelectTable QHeaderView::section {{
            background-color: {pc};
            color: {tx};
            padding: 8px 10px;
            border: none;
            border-bottom: 1px solid {line};
            font-weight: bold;
        }}
    """
    app.setStyleSheet(qss)
