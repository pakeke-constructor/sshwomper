
import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QStackedWidget, QLabel, QListWidgetItem
from PyQt5.QtCore import Qt, QSize

class VerticalNavBarDemo(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Vertical Navbar Demo")
        self.setGeometry(100, 100, 600, 400) # x, y, width, height

        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget) # Horizontal layout for navbar and content

        # --- Navbar ---
        self.nav_bar = QListWidget()
        self.nav_bar.setFixedWidth(120) # Set a fixed width for the navbar
        self.nav_bar.setViewMode(QListWidget.IconMode) # Optional: if you want icons
        self.nav_bar.setIconSize(QSize(32, 32)) # Optional: icon size
        self.nav_bar.setMovement(QListWidget.Static) # Prevent item dragging
        self.nav_bar.setMaximumWidth(130) # Max width
        self.nav_bar.setSpacing(10) # Spacing between items

        # Navbar items
        self.nav_files_item = QListWidgetItem("Files")
        self.nav_programs_item = QListWidgetItem("Programs")
        self.nav_favorites_item = QListWidgetItem("Favorites")

        # Add items to navbar
        self.nav_bar.addItem(self.nav_files_item)
        self.nav_bar.addItem(self.nav_programs_item)
        self.nav_bar.addItem(self.nav_favorites_item)

        # --- Content Area (StackedWidget) ---
        self.stacked_widget = QStackedWidget()

        # Create content widgets for each tab
        self.files_widget = QWidget()
        files_layout = QVBoxLayout(self.files_widget)
        files_layout.addWidget(QLabel("This is the Files Tab"))
        files_layout.setAlignment(Qt.AlignCenter)

        self.programs_widget = QWidget()
        programs_layout = QVBoxLayout(self.programs_widget)
        programs_layout.addWidget(QLabel("This is the Programs Tab"))
        programs_layout.setAlignment(Qt.AlignCenter)

        self.favorites_widget = QWidget()
        favorites_layout = QVBoxLayout(self.favorites_widget)
        favorites_layout.addWidget(QLabel("This is the Favorites Tab"))
        favorites_layout.setAlignment(Qt.AlignCenter)

        # Add content widgets to StackedWidget
        self.stacked_widget.addWidget(self.files_widget)
        self.stacked_widget.addWidget(self.programs_widget)
        self.stacked_widget.addWidget(self.favorites_widget)

        # Add navbar and content area to main layout
        main_layout.addWidget(self.nav_bar)
        main_layout.addWidget(self.stacked_widget)

        # --- Connections ---
        self.nav_bar.currentRowChanged.connect(self.stacked_widget.setCurrentIndex)

        # Select the first item by default
        self.nav_bar.setCurrentRow(0)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    demo = VerticalNavBarDemo()
    demo.show()
    sys.exit(app.exec_())