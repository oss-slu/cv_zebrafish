# themes.py
#
# Visual hierarchy (dark): panel_main (darkest) < panel_chrome < chrome_button ~ chrome_line
#                (light): panel_main (lightest) < panel_chrome (slightly darker) < edges/buttons
# Text/icons on a surface should read one step brighter (dark mode) / darker (light mode) than
# that surface. StandardPixmap-based icons ignore QSS color — use SVG/theme assets where contrast matters.

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
    # Generate Config: neutral grey selection on dark panels
    "generate_selection_bg": "#4a4a54",
    "generate_selection_fg": "#f2f2f8",
    # View Output graph viewer: dark tab chips, light text (dark app mode)
    "graph_viewer_tab_fg": "#b8bac8",
    "graph_viewer_tab_bg": "#18181c",
    "graph_viewer_tab_sel_bg": "#2a2a32",
    "graph_viewer_tab_sel_fg": "#f2f2f8",
    "graph_viewer_tab_hover_bg": "#32323c",
    "graph_viewer_tab_hover_fg": "#ececf0",
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
    gsel_bg = theme.get("generate_selection_bg", accent)
    gsel_fg = theme.get("generate_selection_fg", "#ffffff")
    gv_tab_fg = theme.get("graph_viewer_tab_fg", tx)
    gv_tab_bg = theme.get("graph_viewer_tab_bg", pc)
    gv_tab_sel_bg = theme.get("graph_viewer_tab_sel_bg", pm)
    gv_tab_sel_fg = theme.get("graph_viewer_tab_sel_fg", tx)
    gv_tab_hover_bg = theme.get("graph_viewer_tab_hover_bg", cb)
    gv_tab_hover_fg = theme.get("graph_viewer_tab_hover_fg", gv_tab_sel_fg)

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

        /* View Output / GraphViewer (embedded under WorkspaceMain) */
        QWidget#WorkspaceMain QWidget#GraphViewerContextBar {{
            background-color: transparent;
            border-bottom: 1px solid {line};
        }}
        QWidget#WorkspaceMain QLabel#GraphViewerContextText {{
            color: {tmenu};
            background-color: transparent;
        }}
        QWidget#WorkspaceMain QLabel#GraphViewerContextIcon {{
            background-color: transparent;
        }}
        QWidget#WorkspaceMain QListWidget#GraphViewerGraphList {{
            background-color: {pm};
            color: {tx};
            border: 1px solid {line};
            border-radius: 8px;
            outline: none;
        }}
        QWidget#WorkspaceMain QListWidget#GraphViewerGraphList::item:selected {{
            background-color: {cb};
            color: {tx};
        }}
        QWidget#WorkspaceMain QListWidget#GraphViewerGraphList::item:hover {{
            background-color: {cb};
        }}
        QWidget#WorkspaceMain QListWidget#GraphViewerGraphList:disabled {{
            color: {tmu};
        }}
        QWidget#WorkspaceMain QListWidget#GraphViewerGraphList:disabled::item {{
            color: {tmu};
        }}
        QWidget#WorkspaceMain QScrollArea#GraphViewerImageScroll {{
            background-color: {pm};
            border: 1px solid {line};
            border-radius: 8px;
        }}
        QWidget#WorkspaceMain QLabel#GraphViewerImageLabel {{
            background-color: {pm};
            color: {tmenu};
            border: none;
        }}
        QWidget#WorkspaceMain QComboBox#GraphViewerCsvCombo {{
            min-width: 0px;
        }}
        QWidget#WorkspaceMain QTabWidget#GraphViewerTabWidget::pane {{
            border: 1px solid {line};
            border-radius: 0 0 8px 8px;
            top: -1px;
            background-color: {pm};
        }}
        QWidget#WorkspaceMain QTabWidget#GraphViewerTabWidget QTabBar::tab {{
            background-color: {gv_tab_bg};
            color: {gv_tab_fg};
            padding: 6px 16px;
            margin-right: 2px;
            border: 1px solid {line};
            border-bottom: none;
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
            min-width: 4em;
        }}
        QWidget#WorkspaceMain QTabWidget#GraphViewerTabWidget QTabBar::tab:selected {{
            background-color: {gv_tab_sel_bg};
            color: {gv_tab_sel_fg};
            font-weight: bold;
        }}
        QWidget#WorkspaceMain QTabWidget#GraphViewerTabWidget QTabBar::tab:!selected:hover {{
            background-color: {gv_tab_hover_bg};
            color: {gv_tab_hover_fg};
        }}
        QWidget#WorkspaceMain QTabWidget#GraphViewerTabWidget QTabBar::tab:disabled {{
            background-color: {gv_tab_bg};
            color: {tmu};
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
        QWidget#GenerateConfigTabStrip {{
            background-color: transparent;
        }}
        QPushButton#GenerateConfigTabButton {{
            background-color: {pc};
            color: {tx};
            border: 1px solid {line};
            border-radius: 10px;
            padding: 10px 14px;
            text-align: left;
            font-weight: normal;
            min-height: 20px;
        }}
        QPushButton#GenerateConfigTabButton:checked {{
            background-color: {cb};
            color: {tx};
            font-weight: bold;
            border: 1px solid {accent};
        }}
        QPushButton#GenerateConfigTabButton:hover:!checked:!disabled {{
            background-color: {cb};
            border: 1px solid {line};
        }}
        QPushButton#GenerateConfigTabButton:disabled {{
            color: {tmu};
            background-color: {pm};
            border: 1px dashed {line};
            font-weight: normal;
        }}
        QPushButton#GenerateConfigTabButton:disabled:checked {{
            background-color: {pm};
        }}
        QDialog#GenerateConfigDialog QScrollArea {{
            background-color: transparent;
            border: none;
        }}
        QDialog#GenerateConfigDialog QScrollArea#GenerateConfigScrollBody {{
            background-color: transparent;
        }}
        QDialog#GenerateConfigDialog QComboBox {{
            min-width: 0px;
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

        QDialog#ConsoleViewerDialog {{
            background-color: {pm};
            color: {tx};
            border: 1px solid {line};
        }}
        QWidget#ConsoleViewerBody {{
            background-color: {pm};
        }}
        QPlainTextEdit#ConsoleViewerPlain {{
            font-family: Consolas, monospace;
            font-size: 12px;
            background-color: {vcbg};
            color: {vcfg};
            border: 1px solid {line};
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

        QPushButton#ConfigSelectionTestToggle {{
            min-width: 40px;
            max-width: 40px;
            min-height: 22px;
            max-height: 22px;
            border-radius: 11px;
            border: 1px solid {line};
            background-color: {pm};
            padding: 0;
        }}
        QPushButton#ConfigSelectionTestToggle:checked {{
            background-color: {accent};
            border: 1px solid {accent};
        }}
        QPushButton#ConfigSelectionTestToggle:hover:!checked {{
            background-color: {pc};
            border: 1px solid {line};
        }}
        QPushButton#ConfigSelectionTestToggle:hover:checked {{
            background-color: {accent};
            border: 1px solid {line};
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
        QToolButton#SidebarTool[activeTool="true"] {{
            background-color: {line};
            border: 1px solid {line};
            border-radius: 4px;
        }}
        QToolButton#SidebarTool[activeTool="true"]:hover {{
            background-color: {cb};
            border: 1px solid {line};
        }}
        QToolButton#SidebarTool[activeTool="true"]:disabled {{
            background-color: transparent;
            border: 1px solid transparent;
        }}

        QWidget#ErrorToast {{
            background-color: {pc};
            color: {tx};
            border: 1px solid {line};
            border-radius: 10px;
        }}
        QWidget#ErrorToast QLabel#ErrorToastTitle {{
            background-color: transparent;
            color: {tx};
            font-size: 14px;
            font-weight: bold;
        }}
        QWidget#ErrorToast QLabel#ErrorToastBody {{
            background-color: transparent;
            color: {tmenu};
            font-size: 13px;
        }}
        QWidget#ErrorToast QPushButton#ErrorToastConsoleBtn,
        QWidget#ErrorToast QPushButton#ErrorToastCloseBtn {{
            background-color: {cb};
            color: {btxt};
            border: 1px solid {line};
            border-radius: 6px;
            padding: 4px 10px;
            min-height: 28px;
        }}
        QWidget#ErrorToast QPushButton#ErrorToastCloseBtn {{
            font-size: 18px;
            font-weight: bold;
            padding: 2px 12px;
        }}
        QWidget#ErrorToast QPushButton#ErrorToastConsoleBtn:hover,
        QWidget#ErrorToast QPushButton#ErrorToastCloseBtn:hover {{
            border: 1px solid {accent};
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

        QLabel#SessionSelectStatus {{
            background-color: transparent;
            color: {tmu};
            font-size: 13px;
            padding: 4px 2px 2px 2px;
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


def apply_error_toast_theme(toast, theme: dict) -> None:
    """Top-level :class:`ErrorToast` does not inherit ``MainShellWindow`` QSS; mirror the ErrorToast rules here."""
    pc = theme["panel_chrome"]
    tx = theme["text"]
    line = theme["chrome_line"]
    cb = theme["chrome_button"]
    btxt = theme["button_text"]
    tmenu = theme["title_menu_text"]
    accent = theme["accent"]
    toast.setStyleSheet(
        f"""
        QWidget#ErrorToast {{
            background-color: {pc};
            color: {tx};
            border: 1px solid {line};
            border-radius: 10px;
        }}
        QWidget#ErrorToast QLabel#ErrorToastTitle {{
            background-color: transparent;
            color: {tx};
            font-size: 14px;
            font-weight: bold;
        }}
        QWidget#ErrorToast QLabel#ErrorToastBody {{
            background-color: transparent;
            color: {tmenu};
            font-size: 13px;
        }}
        QWidget#ErrorToast QPushButton#ErrorToastConsoleBtn,
        QWidget#ErrorToast QPushButton#ErrorToastCloseBtn {{
            background-color: {cb};
            color: {btxt};
            border: 1px solid {line};
            border-radius: 6px;
            padding: 4px 10px;
            min-height: 28px;
        }}
        QWidget#ErrorToast QPushButton#ErrorToastCloseBtn {{
            font-size: 18px;
            font-weight: bold;
            padding: 2px 12px;
        }}
        QWidget#ErrorToast QPushButton#ErrorToastConsoleBtn:hover,
        QWidget#ErrorToast QPushButton#ErrorToastCloseBtn:hover {{
            border: 1px solid {accent};
        }}
    """
    )
