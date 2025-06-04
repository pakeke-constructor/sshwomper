import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QListWidget, QStackedWidget, QLabel,
                             QListWidgetItem)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QFont # Optional: for consistent font

class CustomStyledNavBarDemo(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Navbar with Item Borders")
        self.setGeometry(100, 100, 600, 400)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(5, 5, 5, 5) # Add some margin around the whole layout

        # --- Navbar ---
        self.nav_bar = QListWidget()
        self.nav_bar.setObjectName("navBar") # Set object name for QSS styling
        self.nav_bar.setFixedWidth(130)
        # self.nav_bar.setViewMode(QListWidget.IconMode) # Keeping it as ListMode for clear text
        # self.nav_bar.setIconSize(QSize(32, 32))
        self.nav_bar.setMovement(QListWidget.Static)
        self.nav_bar.setSpacing(2) # Reduced spacing between items themselves

        # Navbar items
        nav_item_texts = ["Files", "Programs", "Favorites"]
        for text in nav_item_texts:
            item = QListWidgetItem(text)
            item.setTextAlignment(Qt.AlignCenter) # Center text within the item
            # item.setFont(QFont("Arial", 10)) # Optional: Set a font
            self.nav_bar.addItem(item)

        # --- Content Area (StackedWidget) ---
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.setObjectName("contentArea")

        self.files_widget = QLabel("Content for Files")
        self.files_widget.setAlignment(Qt.AlignCenter)
        self.files_widget.setFont(QFont("Arial", 14))

        self.programs_widget = QLabel("Content for Programs")
        self.programs_widget.setAlignment(Qt.AlignCenter)
        self.programs_widget.setFont(QFont("Arial", 14))

        self.favorites_widget = QLabel("Content for Favorites")
        self.favorites_widget.setAlignment(Qt.AlignCenter)
        self.favorites_widget.setFont(QFont("Arial", 14))

        self.stacked_widget.addWidget(self.files_widget)
        self.stacked_widget.addWidget(self.programs_widget)
        self.stacked_widget.addWidget(self.favorites_widget)

        main_layout.addWidget(self.nav_bar)
        main_layout.addWidget(self.stacked_widget, 1) # Content takes more space

        # --- Connections ---
        self.nav_bar.currentRowChanged.connect(self.stacked_widget.setCurrentIndex)

        # Apply custom QSS
        self.apply_stylesheet()

        # Select the first item by default
        if self.nav_bar.count() > 0:
            self.nav_bar.setCurrentRow(0)

    def apply_stylesheet(self):
        style = """
            QListWidget#navBar {{
                background-color: #f0f0f0; /* Light grey background for the navbar area */
                border: 1px solid #cccccc; /* Optional: border for the whole navbar */
                outline: 0; /* Remove focus outline around the QListWidget itself */
            }}

            QListWidget#navBar::item {{
                background-color: #ffffff; /* White background for items */
                color: #333333; /* Dark text color */
                padding: 8px 5px;     /* Reduced padding: 8px top/bottom, 5px left/right */
                margin: 1px 0px;      /* Small margin around items, primarily for visual separation if needed */
                border: 1px solid #c5c5c5; /* Rectangle (border) around each item */
                border-radius: 3px;   /* Optional: slightly rounded corners for the rectangle */
            }}

            QListWidget#navBar::item:hover {{
                background-color: #e9e9e9; /* Light grey background on hover */
                color: #000000;
            }}

            QListWidget#navBar::item:selected {{
                background-color: #0078d4; /* Blue background for selected item */
                color: white;               /* White text for selected item */
                border: 1px solid #005a9e;  /* Darker blue border for selected item */
            }}

            /* Basic styling for content area for contrast */
            QStackedWidget#contentArea > QLabel {{
                background-color: #ffffff;
                color: #333333;
            }}
        """
        self.setStyleSheet(style)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    demo = CustomStyledNavBarDemo()
    demo.show()
    sys.exit(app.exec_())