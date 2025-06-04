import sys

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QTabWidget, QTextEdit, QInputDialog
)
from PyQt5.QtCore import Qt


class TabWidget(QTabWidget):
    def __init__(self):
        super().__init__()

        self.setTabsClosable(True)
        self.tabCloseRequested.connect(self.close_tab)
        self.tabBarDoubleClicked.connect(self.rename_tab)
        self.currentChanged.connect(self.check_plus_tab)

        # Add first real tab
        self.add_real_tab("Tab 1")

        # Add '+' tab
        self.addTab(QWidget(), "+")
        self.setTabEnabled(self.count() - 1, True)

    def add_real_tab(self, name):
        page = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(QTextEdit())
        page.setLayout(layout)
        self.insertTab(self.count() - 1, page, name)
        self.setCurrentWidget(page)

    def close_tab(self, index):
        # Prevent closing the "+" tab
        print(self.tabText(index))
        if self.tabText(index) == "+":
            return
        self.removeTab(index)

    def check_plus_tab(self, index):
        if self.tabText(index) == "+":
            self.add_real_tab(f"Tab {self.count()}")
    
    def rename_tab(self, index):
        if self.tabText(index) == "+":
            return
        current_name = self.tabText(index)
        new_name, ok = QInputDialog.getText(self, "Rename Tab", "New name:", text=current_name)
        if ok and new_name.strip():
            self.setTabText(index, new_name.strip())


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tab Demo")
        self.resize(500, 400)
        self.setCentralWidget(TabWidget())


app = QApplication(sys.argv)
window = MainWindow()
window.show()
sys.exit(app.exec())

