from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTabBar
)

from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SSHWOMPER")
        self.resize(500, 300)

        self.setWindowIcon(QIcon("nerd.ico"))

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)

        self.setCentralWidget(self.tabs)

        self.add_plus_tab()

    def add_plus_tab(self):
        plus_tab = QWidget()
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)

        self.host_input = QLineEdit()
        self.user_input = QLineEdit()
        self.pass_input = QLineEdit()
        self.port_input = QLineEdit()

        self.host_input.setPlaceholderText("host (ip or hostname)")
        self.user_input.setPlaceholderText("user (eg. root)")
        self.pass_input.setPlaceholderText("password (optional)")
        self.port_input.setPlaceholderText("port")
        self.port_input.setText("22")

        for widget in [self.host_input, self.user_input, self.pass_input, self.port_input]:
            widget.setFixedWidth(250)
            layout.addWidget(widget)

        plus_tab.setLayout(layout)

        if self.tabs.count() == 0 or self.tabs.tabText(self.tabs.count() - 1) != '+':
            self.tabs.addTab(plus_tab, '+')
        else:
            self.tabs.removeTab(self.tabs.count() - 1)
            self.tabs.addTab(plus_tab, '+')

        self.tabs.setCurrentIndex(self.tabs.count() - 1)
        self.tabs.tabBar().setTabButton(self.tabs.count() - 1, QTabBar.RightSide, None)

        # Connect Enter key from any field
        self.host_input.returnPressed.connect(self.try_create_tab)
        self.user_input.returnPressed.connect(self.try_create_tab)
        self.pass_input.returnPressed.connect(self.try_create_tab)
        self.port_input.returnPressed.connect(self.try_create_tab)

    def try_create_tab(self):
        host = self.host_input.text().strip()
        user = self.user_input.text().strip() or "root"
        password = self.pass_input.text()
        port = self.port_input.text().strip() or "port"

        if not host:
            return

        # Create display content
        new_tab = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(QLabel(f"Host: {host}"))
        layout.addWidget(QLabel(f"User: {user}"))
        layout.addWidget(QLabel(f"Password: {'(empty)' if password == '' else '******'}"))
        layout.addWidget(QLabel(f"Port: {port}"))
        new_tab.setLayout(layout)

        # Insert tab before "+"
        insert_index = self.tabs.count() - 1
        self.tabs.insertTab(insert_index, new_tab, host)
        self.tabs.setCurrentIndex(insert_index)

        # Clear inputs
        self.host_input.clear()
        self.user_input.clear()
        self.pass_input.clear()
        self.port_input.setText("22")

    def close_tab(self, index):
        if self.tabs.tabText(index) != '+':
            self.tabs.removeTab(index)


if __name__ == '__main__':
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec_()

